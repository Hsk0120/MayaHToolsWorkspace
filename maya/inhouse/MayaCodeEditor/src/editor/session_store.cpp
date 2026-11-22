/** @file session_store.cpp
 * @brief 不変の本文・世代による、クラッシュと同時起動に備えた復元。
 */
#include "editor/session_store.h"
#include <QCryptographicHash>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLockFile>
#include <QSaveFile>
#include <QSet>

namespace mce {
namespace {

/** @brief 一時ファイルを確定する。既存ファイルへの直接書込は許可しない。
 * @param path 保存先。 @param bytes 内容。 @param error 失敗理由。 @return 確定できたらtrue。
 */
bool writeFile(const QString& path, const QByteArray& bytes, QString* error) {
    QSaveFile file(path);
    file.setDirectWriteFallback(false);
    const bool written = file.open(QIODevice::WriteOnly) && file.write(bytes) == bytes.size() && file.commit();
    if (!written && error) {
        *error = file.errorString();
    }
    return written;
}

/** @brief 内容の識別子を返す。 @param bytes UTF-8本文。 @return SHA256の16進表現。 */
QString digest(const QByteArray& bytes) {
    return QString::fromLatin1(QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex());
}

/** @brief 本文の識別子を検証する。 @param hash 識別子。 @return 小文字16進64桁ならtrue。 */
bool validHash(const QString& hash) {
    if (hash.size() != 64) { return false; }
    for (const QChar c : hash) {
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) { return false; }
    }
    return true;
}

/** @brief 確定世代のメタデータだけを読む。 @param path パス。 @return 不正なら空オブジェクト。 */
QJsonObject readManifest(const QString& path) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) { return {}; }
    const QJsonObject root = QJsonDocument::fromJson(file.readAll()).object();
    SessionData data;
    if (root.value("recoveryVersion").toInt() != 1 || !root.value("parents").isArray()
        || !sessionFromObject(root, &data)) { return {}; }
    QSet<QString> ids;
    const auto bodies = root.value("bodies").toObject();
    for (const TabState& tab : data.tabs) {
        if (ids.contains(tab.id) || !validHash(bodies.value(tab.id).toString())) { return {}; }
        ids.insert(tab.id);
    }
    for (const QJsonValue& parent : root.value("parents").toArray()) {
        if (!isValidTabId(parent.toString())) { return {}; }
    }
    return root;
}

/** @brief 圧縮本文を検証して読む。 @param path ファイル。 @param hash 期待するSHA256。
 * @param bytes 復元本文。 @return 一致すればtrue。
 */
bool readBody(const QString& path, const QString& hash, QByteArray* bytes) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) { return false; }
    const QByteArray compressed = file.readAll();
    if (compressed.size() < 4) { return false; }
    *bytes = qUncompress(compressed);
    return digest(*bytes) == hash;
}

}  // namespace

SessionStore::SessionStore(const QString& path) : path_(path) {}

QString SessionStore::textPath(const QString& id) const {
    if (bodies_.contains(id)) { return recoveryPath() + "/bodies/" + bodies_.value(id) + ".qz"; }
    return QFileInfo(path_).absolutePath() + "/tabs/" + id + ".txt";
}

bool SessionStore::readSnapshot(const QString& id, SessionData* data) const {
    *data = SessionData();
    if (!isValidTabId(id)) { return false; }
    const QJsonObject root = readManifest(recoveryPath() + "/snapshots/" + id + ".json");
    SessionData loaded;
    if (root.isEmpty() || !sessionFromObject(root, &loaded)) { return false; }
    const QString activeId = loaded.tabs.value(loaded.activeTab).id;
    QList<TabState> readable;
    const auto bodies = root.value("bodies").toObject();
    for (TabState tab : loaded.tabs) {
        const QString hash = bodies.value(tab.id).toString();
        QByteArray bytes;
        if (readBody(recoveryPath() + "/bodies/" + hash + ".qz", hash, &bytes)) {
            tab.text = QString::fromUtf8(bytes);
            tab.textLoaded = true;
            if (tab.id == activeId) { loaded.activeTab = readable.size(); }
            readable.append(tab);
        }
    }
    const bool complete = readable.size() == loaded.tabs.size();
    loaded.tabs = readable;
    *data = loaded;
    return complete;
}

SessionStore::OpenResult SessionStore::open(SessionData* data) {
    enabled_ = false;
    parents_.clear();
    bodies_.clear();
    cachedText_.clear();
    bodyStamps_.clear();
    lastSaved_.clear();
    notice_.clear();
    if (path_.isEmpty()) { return OpenResult::Disabled; }
    if (!QDir().mkpath(recoveryPath() + "/snapshots") || !QDir().mkpath(recoveryPath() + "/bodies")) {
        return OpenResult::CannotCreateDirectory;
    }
    // 読込と保存・整理を同じ短命ロックで直列化し、整理途中の世代を読まない。
    QLockFile lock(recoveryPath() + "/store.lock");
    lock.setStaleLockTime(0);
    if (!lock.tryLock(1000)) { return OpenResult::Unreadable; }
    enabled_ = true;
    ++listings_;
    const QDir snapshots(recoveryPath() + "/snapshots");
    const QStringList names = snapshots.entryList({"*.json"}, QDir::Files, QDir::Name | QDir::Reversed);
    QHash<QString, QJsonObject> manifests;
    QSet<QString> referenced;
    bool damaged = false;
    for (const QString& name : names) {
        const QString id = QFileInfo(name).completeBaseName();
        const QJsonObject root = readManifest(snapshots.filePath(name));
        if (!isValidTabId(id) || root.isEmpty()) { damaged = true; continue; }
        manifests.insert(id, root);
        for (const QJsonValue& parent : root.value("parents").toArray()) { referenced.insert(parent.toString()); }
    }
    QStringList queue;
    for (const QString& name : names) {
        const QString id = QFileInfo(name).completeBaseName();
        if (manifests.contains(id) && !referenced.contains(id)) { queue.append(id); }
    }
    const bool concurrent = queue.size() > 1;
    SessionData merged;
    QSet<QString> visited;
    QSet<QString> identities;
    QSet<QString> usedIds;
    // 破損した先端は読めるタブを保護し、親世代にも戻る。世代の順番に時計だけを使わない。
    for (int index = 0; index < queue.size(); ++index) {
        const QString id = queue[index];
        if (visited.contains(id) || !manifests.contains(id)) { continue; }
        visited.insert(id);
        SessionData loaded;
        const bool complete = readSnapshot(id, &loaded);
        if (complete) {
            parents_.append(id);
        } else {
            damaged = true;
            for (const QJsonValue& parent : manifests.value(id).value("parents").toArray()) { queue.append(parent.toString()); }
        }
        if (merged.tabs.isEmpty()) {
            merged.activeTab = loaded.activeTab;
            merged.explorerVisible = loaded.explorerVisible;
        }
        for (const QString& folder : loaded.folders) {
            if (!merged.folders.contains(folder)) { merged.folders.append(folder); }
        }
        for (TabState tab : loaded.tabs) {
            const QString hash = digest(tab.text.toUtf8());
            const QString identity = tab.id + ":" + hash + ":" + tab.path + ":" + tab.language;
            if (identities.contains(identity)) { continue; }
            identities.insert(identity);
            // 同じIDの異なる本文はどちらも残す。復元し直しても識別子が安定するよう内容から作る。
            if (usedIds.contains(tab.id)) { tab.id = digest(identity.toUtf8()); tab.modified = true; }
            while (usedIds.contains(tab.id)) { tab.id = digest(tab.id.toUtf8()); }
            usedIds.insert(tab.id);
            bodies_.insert(tab.id, hash);
            cachedText_.insert(tab.id, tab.text);
            merged.tabs.append(tab);
        }
    }
    if (concurrent) { notice_ = "Recovered concurrent Maya sessions. Different edits are kept as separate tabs."; }
    if (damaged) {
        notice_ += " Some recovery files could not be read; available tabs and earlier versions were recovered. Original files are preserved.";
    }
    if (!merged.tabs.isEmpty()) { *data = merged; return OpenResult::Loaded; }
    // 移行中は旧形式を読み取るだけ。最新状態を確定できるまで削除しない。
    QFile file(path_);
    SessionData loaded;
    if (file.exists() && file.open(QIODevice::ReadOnly) && sessionFromJson(file.readAll(), &loaded)) {
        QList<TabState> readable;
        for (TabState tab : loaded.tabs) {
            if (!tab.textLoaded) {
                QFile text(textPath(tab.id));
                if (!text.open(QIODevice::ReadOnly)) { continue; }
                tab.text = QString::fromUtf8(text.readAll());
                tab.textLoaded = true;
            }
            cachedText_.insert(tab.id, tab.text);
            readable.append(tab);
        }
        if (readable.size() != loaded.tabs.size()) {
            notice_ += " Some legacy tab bodies are missing. Available tabs were recovered; the original files are preserved.";
        }
        loaded.tabs = readable;
        if (!readable.isEmpty()) { *data = loaded; return OpenResult::Loaded; }
    }
    return file.exists() || !names.isEmpty() ? OpenResult::Unreadable : OpenResult::NoFile;
}

bool SessionStore::save(const SessionData& data, QString* error, bool prune) {
    if (!enabled_ || data.tabs.isEmpty()) {
        if (error) { *error = "Recovery is unavailable or has no tabs."; }
        return false;
    }
    QLockFile lock(recoveryPath() + "/store.lock");
    lock.setStaleLockTime(0);
    if (!lock.tryLock(1000)) {
        if (error) { *error = "Another Maya is saving recovery data. Please retry."; }
        return false;
    }
    QHash<QString, QString> bodies;
    QHash<QString, QString> texts;
    QHash<QString, QPair<qint64, qint64>> stamps;
    QSet<QString> verifiedBodies;
    QJsonObject references;
    for (const TabState& tab : data.tabs) {
        if (!isValidTabId(tab.id) || bodies.contains(tab.id)) {
            if (error) { *error = "Invalid or duplicate recovery tab ID."; }
            return false;
        }
        QString hash = bodies_.value(tab.id);
        const QFileInfo savedBody(recoveryPath() + "/bodies/" + hash + ".qz");
        const auto stamp = qMakePair(savedBody.size(), savedBody.lastModified().toMSecsSinceEpoch());
        if (!tab.textLoaded && cachedText_.contains(tab.id) && bodyStamps_.contains(hash)
            && savedBody.isFile() && bodyStamps_.value(hash) == stamp) {
            // 書込側は本文を上書きしない。変更のない検証済み本文を入力ごとに展開・ハッシュ化しない。
            // 別Mayaの整理で消えた場合やファイルの更新を検出した場合は、下で再検証・再確定する。
            texts.insert(tab.id, cachedText_.value(tab.id));
            bodies.insert(tab.id, hash);
            references.insert(tab.id, hash);
            stamps.insert(hash, stamp);
            verifiedBodies.insert(hash);
            continue;
        }
        if (tab.textLoaded || cachedText_.contains(tab.id)) {
            const QString text = tab.textLoaded ? tab.text : cachedText_.value(tab.id);
            texts.insert(tab.id, text);
            const QByteArray bytes = text.toUtf8();
            hash = digest(bytes);
            const QString target = recoveryPath() + "/bodies/" + hash + ".qz";
            QByteArray existing;
            if (!readBody(target, hash, &existing)) {
                if (QFile::exists(target)) {
                    // 別プロセスが直前に同じ本文を確定した場合は再検証する。破損ファイルは変更しない。
                    if (!readBody(target, hash, &existing)) {
                        if (error) { *error = "A recovery body is damaged. Original data is preserved; use Save as."; }
                        return false;
                    }
                } else {
                    if (!writeFile(target, qCompress(bytes, 1), error)) { return false; }
                    ++textWrites_;
                }
            }
            verifiedBodies.insert(hash);
            const QFileInfo verified(target);
            stamps.insert(hash, qMakePair(verified.size(), verified.lastModified().toMSecsSinceEpoch()));
        }
        if (hash.isEmpty()) {
            if (error) { *error = "No recovery body for an unchanged tab."; }
            return false;
        }
        bodies.insert(tab.id, hash);
        references.insert(tab.id, hash);
    }
    QJsonObject root = QJsonDocument::fromJson(sessionToJson(data)).object();
    root.insert("bodies", references);
    const QByteArray state = QJsonDocument(root).toJson(QJsonDocument::Compact);
    if (state == lastSaved_) {
        if (prune) { pruneHistory(verifiedBodies); }
        return true;
    }
    root.insert("recoveryVersion", 1);
    root.insert("parents", QJsonArray::fromStringList(parents_));
    root.insert("created", QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs));
    const QString id = QDateTime::currentDateTimeUtc().toString("yyyyMMddHHmmsszzz") + newTabId();
    if (!writeFile(recoveryPath() + "/snapshots/" + id + ".json", QJsonDocument(root).toJson(QJsonDocument::Compact), error)) {
        return false;
    }
    // メタデータの確定後にだけメモリ上の保存済み状態を更新する。失敗時はそのまま再試行できる。
    parents_ = QStringList{id};
    bodies_ = bodies;
    cachedText_ = texts;
    bodyStamps_ = stamps;
    lastSaved_ = state;
    ++jsonWrites_;
    if (prune) { pruneHistory(verifiedBodies); }
    return true;
}

bool SessionStore::discardHistory() {
    if (!enabled_) { return true; }
    QLockFile lock(recoveryPath() + "/store.lock");
    lock.setStaleLockTime(0);
    if (!lock.tryLock(0)) { return false; }
    pruneHistory({});
    return true;
}

void SessionStore::pruneHistory(const QSet<QString>& verifiedBodies) {
    const QDir snapshots(recoveryPath() + "/snapshots");
    const QDir bodies(recoveryPath() + "/bodies");
    // 管理フォルダーがリンクに置き換わっていたら、リンク先を整理対象にしない。
    if (QFileInfo(snapshots.path()).isSymLink() || QFileInfo(bodies.path()).isSymLink()) { return; }
    QHash<QString, QJsonObject> manifests;
    QSet<QString> referenced;
    for (const QString& name : snapshots.entryList({"*.json"}, QDir::Files)) {
        const QString id = QFileInfo(name).completeBaseName();
        if (!isValidTabId(id) || QFileInfo(snapshots.filePath(name)).isSymLink()) { return; }
        const auto root = readManifest(snapshots.filePath(name));
        // 破損・読込失敗があるときは復旧の材料を勝手に消さない。
        if (root.isEmpty()) { return; }
        manifests.insert(id, root);
        for (const auto& parent : root.value("parents").toArray()) { referenced.insert(parent.toString()); }
    }
    QSet<QString> keepBodies;
    int heads = 0;
    for (auto it = manifests.constBegin(); it != manifests.constEnd(); ++it) {
        if (referenced.contains(it.key())) { continue; }
        ++heads;
        const auto hashes = it->value("bodies").toObject();
        for (const auto& tab : it->value("tabs").toArray()) {
            const QString hash = hashes.value(tab.toObject().value("id").toString()).toString();
            // 同じロック内で検証済みの本文は再展開しない。他Mayaの本文は削除前に検証する。
            if (!verifiedBodies.contains(hash) && !keepBodies.contains(hash)) {
                QByteArray text;
                if (!readBody(bodies.filePath(hash + ".qz"), hash, &text)) { return; }
            }
            keepBodies.insert(hash);
        }
    }
    if (heads == 0) { return; }
    // 最古の祖先から順に消す。途中で終了しても、祖先が独立した最新状態として復活しない。
    QHash<QString, int> indegree;
    QHash<QString, QStringList> children;
    QStringList order;
    for (auto it = manifests.constBegin(); it != manifests.constEnd(); ++it) {
        QSet<QString> parents;
        for (const auto& parent : it->value("parents").toArray()) {
            if (manifests.contains(parent.toString())) { parents.insert(parent.toString()); }
        }
        indegree.insert(it.key(), parents.size());
        if (parents.isEmpty()) { order.append(it.key()); }
        for (const auto& parent : parents) { children[parent].append(it.key()); }
    }
    for (int index = 0; index < order.size(); ++index) {
        for (const auto& child : children.value(order[index])) {
            if (--indegree[child] == 0) { order.append(child); }
        }
    }
    if (order.size() != manifests.size()) { return; }
    for (const QString& id : order) {
        if (referenced.contains(id) && !QFile::remove(snapshots.filePath(id + ".json"))) { return; }
    }
    for (const QString& name : bodies.entryList({"*.qz"}, QDir::Files)) {
        const QString hash = QFileInfo(name).completeBaseName();
        if (validHash(hash) && !keepBodies.contains(hash) && !QFileInfo(bodies.filePath(name)).isSymLink()) {
            QFile::remove(bodies.filePath(name));
        }
    }
    // 旧版が使用中なら旧データには触らない。移行後は旧本文も履歴として残さない。
    const QDir legacyTabs(QFileInfo(path_).absolutePath() + "/tabs");
    const QStringList legacyNames = legacyTabs.entryList({"*.txt"}, QDir::Files);
    // 移行済みなら旧版用ロックのファイル作成・同期書込を入力ごとに繰り返さない。
    if (!QFile::exists(path_) && legacyNames.isEmpty()) { return; }
    QLockFile legacyLock(path_ + ".lock");
    legacyLock.setStaleLockTime(0);
    if (!legacyLock.tryLock(0)) { return; }
    if (QFileInfo(path_).isSymLink()) { return; }
    if (QFile::exists(path_) && !QFile::remove(path_)) { return; }
    if (QFileInfo(legacyTabs.path()).isSymLink()) { return; }
    for (const QString& name : legacyNames) {
        if (isValidTabId(QFileInfo(name).completeBaseName()) && !QFileInfo(legacyTabs.filePath(name)).isSymLink()) {
            QFile::remove(legacyTabs.filePath(name));
        }
    }
}

}  // namespace mce
