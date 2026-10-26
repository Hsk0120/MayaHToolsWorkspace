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
        || !sessionFromJson(QJsonDocument(root).toJson(), &data)) { return {}; }
    QSet<QString> ids;
    for (const TabState& tab : data.tabs) {
        if (ids.contains(tab.id) || !validHash(root.value("bodies").toObject().value(tab.id).toString())) { return {}; }
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
    if (root.isEmpty() || !sessionFromJson(QJsonDocument(root).toJson(), &loaded)) { return false; }
    const QString activeId = loaded.tabs.value(loaded.activeTab).id;
    QList<TabState> readable;
    for (TabState tab : loaded.tabs) {
        const QString hash = root.value("bodies").toObject().value(tab.id).toString();
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
    legacy_.clear();
    lastSaved_.clear();
    notice_.clear();
    if (path_.isEmpty()) { return OpenResult::Disabled; }
    if (!QDir().mkpath(recoveryPath() + "/snapshots") || !QDir().mkpath(recoveryPath() + "/bodies")) {
        return OpenResult::CannotCreateDirectory;
    }
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
            merged.tabs.append(tab);
        }
    }
    if (concurrent) { notice_ = "Recovered concurrent Maya sessions. Different edits are kept as separate tabs."; }
    if (damaged) {
        notice_ += " Some recovery files could not be read; available tabs and earlier versions were recovered. Original files are preserved.";
    }
    if (!merged.tabs.isEmpty()) { *data = merged; return OpenResult::Loaded; }
    // 旧形式は読込専用。他の旧版Mayaが利用中でも変更・削除・ロック取得をしない。
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
            legacy_.insert(tab.id, tab.text);
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

bool SessionStore::save(const SessionData& data, QString* error) {
    if (!enabled_ || data.tabs.isEmpty()) {
        if (error) { *error = "Recovery is unavailable or has no tabs."; }
        return false;
    }
    QHash<QString, QString> bodies;
    QJsonObject references;
    for (const TabState& tab : data.tabs) {
        if (!isValidTabId(tab.id) || bodies.contains(tab.id)) {
            if (error) { *error = "Invalid or duplicate recovery tab ID."; }
            return false;
        }
        QString hash = bodies_.value(tab.id);
        if (tab.textLoaded || (hash.isEmpty() && legacy_.contains(tab.id))) {
            const QByteArray bytes = (tab.textLoaded ? tab.text : legacy_.value(tab.id)).toUtf8();
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
    if (state == lastSaved_) { return true; }
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
    legacy_.clear();
    lastSaved_ = state;
    ++jsonWrites_;
    return true;
}

}  // namespace mce
