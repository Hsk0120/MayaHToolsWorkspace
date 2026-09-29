/** @file session_store.cpp
 * @brief SessionStoreの実装。
 */
#include "editor/session_store.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QLockFile>
#include <QSaveFile>

namespace hedit {

SessionStore::SessionStore(const QString& path) : path_(path) {}

// unique_ptr<QLockFile>の破棄にはQLockFileの完全な定義が必要なので、デストラクターは.cppに置く。
// QLockFileは破棄時にロックを外す。
SessionStore::~SessionStore() = default;

SessionStore::OpenResult SessionStore::open(SessionData* data) {
    if (path_.isEmpty()) {
        return OpenResult::Disabled;
    }
    if (!QDir().mkpath(QFileInfo(path_).absolutePath())) {
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
    const bool readable = file.open(QIODevice::ReadOnly);
    if (!readable || !sessionFromJson(file.readAll(), data)) {
        // 壊れたファイルを上書きしないよう、ロックを外して以後は保存しない。
        lock_->unlock();
        return OpenResult::Unreadable;
    }
    return OpenResult::Loaded;
}

bool SessionStore::canSave() const {
    return lock_ && lock_->isLocked();
}

bool SessionStore::save(const SessionData& data, QString* error) {
    if (!canSave()) {
        return false;
    }
    const QByteArray bytes = sessionToJson(data);
    if (bytes == lastSaved_) {
        return true;
    }
    QSaveFile file(path_);
    const bool written = file.open(QIODevice::WriteOnly) && file.write(bytes) == bytes.size() && file.commit();
    if (!written) {
        if (error) {
            *error = file.errorString();
        }
        return false;
    }
    lastSaved_ = bytes;
    return true;
}

}  // namespace hedit
