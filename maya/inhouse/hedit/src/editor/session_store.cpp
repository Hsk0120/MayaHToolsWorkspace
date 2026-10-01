/** @file session_store.cpp
 * @brief SessionStoreの実装。
 */
#include "editor/session_store.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QLockFile>
#include <QSaveFile>
#include <QSet>

namespace hedit {
namespace {

/** @brief ファイルへ一時ファイル経由で書く。 @param path パス。 @param bytes 内容。 @param error 理由を入れる。
 * @return 書けたらtrue。
 */
bool writeFile(const QString& path, const QByteArray& bytes, QString* error) {
    QSaveFile file(path);
    const bool written = file.open(QIODevice::WriteOnly) && file.write(bytes) == bytes.size() && file.commit();
    if (!written && error) {
        *error = file.errorString();
    }
    return written;
}

}  // namespace

SessionStore::SessionStore(const QString& path) : path_(path) {}

// unique_ptr<QLockFile>の破棄にはQLockFileの完全な定義が必要なので、デストラクターは.cppに置く。
// QLockFileは破棄時にロックを外す。
SessionStore::~SessionStore() = default;

QString SessionStore::textPath(const QString& id) const {
    return QFileInfo(path_).absolutePath() + "/tabs/" + id + ".txt";
}

SessionStore::OpenResult SessionStore::open(SessionData* data) {
    if (path_.isEmpty()) {
        return OpenResult::Disabled;
    }
    if (!QDir().mkpath(QFileInfo(path_).absolutePath() + "/tabs")) {
        return OpenResult::CannotCreateDirectory;
    }
    // tryLock(0)は、待たずにすぐロックを試す。別のMayaが持っていれば失敗する。
    lock_ = std::make_unique<QLockFile>(path_ + ".lock");
    if (!lock_->tryLock(0)) {
        return OpenResult::Locked;
    }
    QFile file(path_);
    if (!file.exists()) {
        return OpenResult::NoFile;
    }
    SessionData loaded;
    const bool readable = file.open(QIODevice::ReadOnly) && sessionFromJson(file.readAll(), &loaded);
    bool textsReadable = readable;
    for (TabState& tab : loaded.tabs) {
        if (!textsReadable || tab.textLoaded) {
            continue;
        }
        QFile text(textPath(tab.id));
        textsReadable = text.open(QIODevice::ReadOnly);
        tab.text = textsReadable ? QString::fromUtf8(text.readAll()) : QString();
        tab.textLoaded = textsReadable;
    }
    if (!textsReadable) {
        // 壊れたファイル(本文のファイルが欠けている場合を含む)を上書きしないよう、ロックを外して以後は保存しない。
        lock_->unlock();
        return OpenResult::Unreadable;
    }
    *data = loaded;
    return OpenResult::Loaded;
}

bool SessionStore::canSave() const {
    return lock_ && lock_->isLocked();
}

bool SessionStore::save(const SessionData& data, QString* error) {
    if (!canSave()) {
        return false;
    }
    // 1. 本文が変わったタブの本文を書く。
    QSet<QString> ids;
    for (const TabState& tab : data.tabs) {
        ids.insert(tab.id + ".txt");
        if (tab.textLoaded && !writeFile(textPath(tab.id), tab.text.toUtf8(), error)) {
            return false;
        }
    }
    // 2. タブの並びなどの小さな情報を書く(前回と同じなら書かない)。
    const QByteArray bytes = sessionToJson(data);
    if (bytes != lastSaved_) {
        if (!writeFile(path_, bytes, error)) {
            return false;
        }
        lastSaved_ = bytes;
    }
    // 3. 閉じたタブの本文のファイルを消す(tabs.jsonを書いた後なので、消しても参照されない)。
    QDir texts(QFileInfo(path_).absolutePath() + "/tabs");
    for (const QString& name : texts.entryList({"*.txt"}, QDir::Files)) {
        if (!ids.contains(name)) {
            texts.remove(name);
        }
    }
    return true;
}

}  // namespace hedit
