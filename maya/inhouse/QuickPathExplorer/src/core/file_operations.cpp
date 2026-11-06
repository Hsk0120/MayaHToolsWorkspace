/** @file file_operations.cpp @brief 原本を保持する転送・永続履歴・直列ワーカー。 */
#include "file_operations.h"
#include "settings_store.h"
#include "shell_recycle.h"
#include "file_queries.h"
#include "archive.h"
#include "media_query.h"
#include "legacy_history.h"
#include <QCryptographicHash>
#include <QDebug>
#include <QDateTime>
#include <QElapsedTimer>
#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QMap>
#include <QLockFile>
#include <QRegularExpression>
#include <QSet>
#include <QRunnable>
#include <QThreadPool>
#include <QThread>
#include <QUuid>
#include <stdexcept>
#include <algorithm>
#include <iterator>
#define NOMINMAX
#include <windows.h>
namespace qpe {
namespace {
std::atomic_int workers{0};
QThreadPool* filePool = nullptr;
thread_local CancelFlag threadPause;
/** @brief 利用者向けエラーを投げる。 @param text 説明。 */
[[noreturn]] void fail(const QString& text) { throw std::runtime_error(text.toStdString()); }
/** @brief Windowsの失敗理由と対象を保持する。 @param action 操作。 @param path 対象。 @param code OSエラー。 @return 説明。 */
QString windowsFailure(const QString& action, const QString& path, DWORD code) {
    wchar_t* buffer = nullptr;
    FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
                   nullptr, code, 0, reinterpret_cast<LPWSTR>(&buffer), 0, nullptr);
    const auto reason = buffer ? QString::fromWCharArray(buffer).trimmed() : QString("Windows error");
    if (buffer) LocalFree(buffer);
    return QString("%1: %2\nWindows %3: %4").arg(action, path).arg(code).arg(reason);
}
/** @brief 作成失敗をパスとOSの理由付きで通知する。 @param path 未作成フォルダー。 */
void makeDirectory(const QString& path) {
    if (!CreateDirectoryW(reinterpret_cast<LPCWSTR>(QDir::toNativeSeparators(path).utf16()), nullptr)) {
        const auto error = GetLastError();
        fail(windowsFailure("Cannot create folder", path, error));
    }
}
/** @brief 中断の専用型。 */
struct Cancelled : std::runtime_error { /** @brief 中断理由を作る。 */ Cancelled() : std::runtime_error("Cancelled") {} };
/** @brief コミット前の取消し点。 @param cancel 共有フラグ。 */
void check(const CancelFlag& cancel) { while (threadPause && threadPause->load() && !(cancel && cancel->load())) QThread::msleep(25); if (cancel && cancel->load()) throw Cancelled(); }
/** @brief 絶対表記へ統一する。 @param path パス。 @return 正規化値。 */
QString normalized(const QString& path) { return QDir::cleanPath(QFileInfo(path).absoluteFilePath()); }
/** @brief 大小文字を無視した同一/配下判定。 @param path 対象。 @param root 境界。 @return 配下か。 */
bool within(const QString& path, const QString& root) { return path.compare(root, Qt::CaseInsensitive) == 0 || path.startsWith(root.endsWith('/') ? root : root + '/', Qt::CaseInsensitive); }
/** @brief Windowsの属性を読み、取得失敗の理由を保持する。 @param path 対象。 @return 属性。 */
DWORD pathAttributes(const QString& path) {
    const DWORD flags = GetFileAttributesW(reinterpret_cast<LPCWSTR>(QDir::toNativeSeparators(path).utf16()));
    if (flags == INVALID_FILE_ATTRIBUTES) {
        const auto error = GetLastError();
        fail(windowsFailure("Cannot inspect path", path, error));
    }
    return flags;
}
constexpr DWORD offlineAttributes = FILE_ATTRIBUTE_OFFLINE | 0x40000 | 0x400000;
/** @brief リンクそのものと未取得のクラウド項目を転送から保護する。 @param path 対象。 */
[[noreturn]] void refuseLink(const QString& path) {
    fail("Links, junctions and online-only items are not modified: " + path);
}
/** @brief リパースポイントとクラウドの暗黙ダウンロードを拒否する。 @param path 対象。 */
void ordinary(const QString& path) {
    if (pathAttributes(path) & (FILE_ATTRIBUTE_REPARSE_POINT | offlineAttributes)) refuseLink(path);
}
/** @brief ソースからルートまで親リンクも検証する。 @param path 対象。 */
void ordinaryParents(QString path) {
    for (const auto& ancestor : detail::operationAncestors(path)) ordinary(ancestor);
}
/** @brief 明示した転送先または転送元の親を実パスへ固定する。
 * @param path 既存フォルダーの表示パス。 @return 転送・履歴に使う実パス。
 * @note フォルダーのシンボリックリンクとジャンクションだけを辿る。列挙中のリンクは対象外。
 */
QString transferDirectory(const QString& path) {
    const auto ancestors = detail::operationAncestors(path);
    QString resolved;
    for (auto it = ancestors.crbegin(); it != ancestors.crend(); ++it) {
        resolved = resolved.isEmpty() ? *it : QDir(resolved).filePath(QFileInfo(*it).fileName());
        const auto flags = pathAttributes(resolved);
        if (flags & offlineAttributes) refuseLink(resolved);
        if (!(flags & FILE_ATTRIBUTE_DIRECTORY)) fail("Choose an existing destination outside the source");
        if (!(flags & FILE_ATTRIBUTE_REPARSE_POINT)) continue;

        const auto native = QDir::toNativeSeparators(resolved);
        const auto* name = reinterpret_cast<LPCWSTR>(native.utf16());
        WIN32_FIND_DATAW data{};
        const auto found = FindFirstFileW(name, &data);
        if (found == INVALID_HANDLE_VALUE) {
            const auto error = GetLastError();
            fail(windowsFailure("Cannot inspect folder link", resolved, error));
        }
        FindClose(found);
        if (data.dwReserved0 != IO_REPARSE_TAG_SYMLINK && data.dwReserved0 != IO_REPARSE_TAG_MOUNT_POINT)
            refuseLink(resolved);

        const auto handle = CreateFileW(name, 0, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                                        nullptr, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, nullptr);
        if (handle == INVALID_HANDLE_VALUE) {
            const auto error = GetLastError();
            fail(windowsFailure("Cannot open folder link", resolved, error));
        }
        wchar_t buffer[32768];
        const auto length = GetFinalPathNameByHandleW(handle, buffer, DWORD(std::size(buffer)), FILE_NAME_NORMALIZED);
        const auto error = GetLastError();
        CloseHandle(handle);
        if (!length) fail(windowsFailure("Cannot resolve folder link", resolved, error));
        if (length >= std::size(buffer)) fail("Folder link target path is too long: " + resolved);
        auto target = QString::fromWCharArray(buffer, int(length)).replace(QChar(0x5c), '/');
        if (target.startsWith("//?/UNC/", Qt::CaseInsensitive)) target = "//" + target.mid(8);
        else if (target.startsWith("//?/") && target.size() >= 7 && target.mid(5, 2) == ":/") target = target.mid(4);
        else fail("Unsupported folder link target: " + resolved);
        resolved = normalized(target);
        ordinaryParents(resolved);
        if (!QFileInfo(resolved).isDir()) fail("Folder link target is not a folder: " + target);
    }
    return resolved;
}
/** @brief 転送項目の親だけを解決し、リンク本体は操作対象にしない。 @param path 表示パス。 @return 実パス。 */
QString transferSource(const QString& path) {
    const QFileInfo info(path);
    if (info.isRoot() || (path.startsWith("//") && detail::operationAncestors(path).size() == 1))
        return path;
    return QDir(transferDirectory(info.absolutePath())).filePath(info.fileName());
}
/** @brief リンク先が同じ間だけ、画面内のパス更新に表示パスを使う。
 * @param physical 履歴に固定した実パス。 @param shown 操作時の表示パス。 @return 現在有効なパス。
 */
QString currentDisplayPath(const QString& physical, const QString& shown) {
    if (shown.isEmpty()) return physical;
    try { if (transferSource(shown).compare(physical, Qt::CaseInsensitive) == 0) return shown; }
    catch (const std::exception&) { /* 操作自体は確定済み。画面には実パスを返す。 */ }
    return physical;
}
/** @brief 移動や改名を画面へ反映する。 @param result 完了結果。 @param entry 履歴。 @param undo 逆方向か。 */
void addPathChange(FileResult& result, const QJsonObject& entry, bool undo) {
    const auto source = currentDisplayPath(entry["source"].toString(), entry["shownSource"].toString());
    const auto target = currentDisplayPath(entry["target"].toString(), entry["shownTarget"].toString());
    auto changes = result.extra["pathChanges"].toArray();
    changes.append(QJsonObject{{"from", undo ? target : source}, {"to", undo ? source : target}});
    result.extra["pathChanges"] = changes;
}
/** @brief リンクを辿らない順序付き子一覧。 @param path 親。 @return 子。 */
QFileInfoList children(const QString& path) { return checkedChildren(path); }
/** @brief 元を残してコピーする。 @param from 元。 @param to 未作成先。 @param cancel 中断。 @param progress 進捗。 */
void copyEntry(const QString& from, const QString& to, const CancelFlag& cancel, const FileProgress& progress) {
    check(cancel); ordinary(from);
    if (QFileInfo::exists(to)) fail("Destination exists: " + to);
    if (QFileInfo(from).isDir()) {
        makeDirectory(to);
        for (const auto& child : children(from)) copyEntry(child.absoluteFilePath(), QDir(to).filePath(child.fileName()), cancel, progress);
    } else {
        QFile input(from), output(to);
        if (!input.open(QIODevice::ReadOnly)) fail("Cannot read: " + from + "\n" + input.errorString());
        if (!output.open(QIODevice::WriteOnly | QIODevice::NewOnly)) fail("Cannot write: " + to + "\n" + output.errorString());
        qint64 size = 0;
        while (!input.atEnd()) {
            check(cancel); const auto bytes = input.read(1024 * 1024);
            if (bytes.isEmpty() && input.error() != QFileDevice::NoError) fail(input.errorString());
            if (output.write(bytes) != bytes.size()) fail(output.errorString());
            size += bytes.size(); if (progress) progress(from, size);
        }
        if (!output.flush()) fail(output.errorString());
        output.setFileTime(input.fileTime(QFileDevice::FileModificationTime), QFileDevice::FileModificationTime);
    }
}
/** @brief 生成した作業コピーだけを消す。 @param path 作業項目。 */
void removeOwned(const QString& path) {
    ordinary(path);
    if (QFileInfo(path).isDir()) { for (const auto& child : children(path)) removeOwned(child.absoluteFilePath()); if (!QDir().rmdir(path)) fail("Cannot remove temporary directory: " + path); }
    else if (!QFile::remove(path)) fail("Cannot remove temporary file: " + path);
}
/** @brief 上書きなしのOSリネーム。一時的な共有/アクセス拒否だけ最大900ms待つ。
 * @param from 元。 @param to 未作成先。
 * @note ワーカー内で使用する。異なるvolumeへコピーせず、持続する失敗は原本を保持して通知する。
 */
void renameExact(const QString& from, const QString& to) {
    const auto source = QDir::toNativeSeparators(from), target = QDir::toNativeSeparators(to);
    DWORD error = ERROR_SUCCESS;
    for (int attempt = 0; attempt < 8; ++attempt) {
        if (MoveFileExW(reinterpret_cast<LPCWSTR>(source.utf16()), reinterpret_cast<LPCWSTR>(target.utf16()), MOVEFILE_WRITE_THROUGH)) return;
        error = GetLastError();
        const bool temporary = error == ERROR_SHARING_VIOLATION || error == ERROR_LOCK_VIOLATION || error == ERROR_ACCESS_DENIED;
        if (!temporary || attempt == 7 || !QFileInfo::exists(from) ||
            (from.compare(to, Qt::CaseInsensitive) && QFileInfo::exists(to))) break;
        QThread::msleep(qMin(200, 20 << attempt));
    }
    fail(windowsFailure("Cannot rename", from + " → " + to, error));
}
/** @brief 旧版の別ドライブ退避も、検証済みコピー確定後にだけ移す。
 * @param from 元。 @param to 未作成先。 @param cancel 取消し。 @param progress 進捗。
 */
void relocateLegacy(const QString& from, const QString& to, const CancelFlag& cancel, const FileProgress& progress) {
    ordinaryParents(from); ordinaryParents(QFileInfo(to).absolutePath());
    if (QFileInfo::exists(to) && from.compare(to, Qt::CaseInsensitive)) fail("Restore destination exists: " + to);
    if (MoveFileExW(reinterpret_cast<LPCWSTR>(QDir::toNativeSeparators(from).utf16()), reinterpret_cast<LPCWSTR>(QDir::toNativeSeparators(to).utf16()), MOVEFILE_WRITE_THROUGH)) return;
    if (GetLastError() != ERROR_NOT_SAME_DEVICE) fail("Legacy restore rename failed");
    const auto temporary = QDir(QFileInfo(to).absolutePath()).filePath(".qpe-legacy-" + QUuid::createUuid().toString(QUuid::WithoutBraces));
    try {
        const auto stamp = fileFingerprint(from, cancel); copyEntry(from, temporary, cancel, progress);
        if (fileFingerprint(temporary, cancel) != stamp || fileFingerprint(from, cancel) != stamp) fail("Legacy backup changed while restoring");
        check(cancel); renameExact(temporary, to); removeOwned(from);
    } catch (...) { if (QFileInfo::exists(temporary)) removeOwned(temporary); throw; }
}
/** @brief 保持用ファイル名。 @param parent 所在。 @return 未作成パス。 */
QString holding(const QString& parent) { return QDir(parent).filePath(".qpe-undo-" + QUuid::createUuid().toString(QUuid::WithoutBraces)); }
/** @brief 自分の通常バックアップの実データ量を算出する。 @param path 所在。 @param cancel 取消し。 @return バイト数。 */
qint64 backupBytes(const QString& path, const CancelFlag& cancel) {
    check(cancel); ordinaryParents(path); if (!QFileInfo(path).isDir()) return QFileInfo(path).size();
    qint64 bytes = 0; for (const auto& child : children(path)) bytes += backupBytes(child.absoluteFilePath(), cancel); return bytes;
}
/** @brief 履歴が所有する退避物を検証する。利用者の現在ファイルは返さない。
 * @param entry 履歴。 @param cancel 取消し。 @return 存在して検証できた退避パス。
 */
QStringList retainedBackups(const QJsonObject& entry, const CancelFlag& cancel) {
    QStringList result;
    for (const auto& key : {"backup", "sourceBackup", "undoHold"}) {
        const auto path = entry[key].toString(); if (path.isEmpty() || !QFileInfo::exists(path)) continue;
        const auto parent = QFileInfo(entry[QString(key) == "sourceBackup" ? "source" : "target"].toString()).absolutePath();
        const bool legacy = entry["legacy"].toBool();
        const bool oldBackup = legacy && QString(key) == "backup" && QFileInfo(path).absolutePath().compare(entry["legacyDirectory"].toString(), Qt::CaseInsensitive) == 0
            && QRegularExpression("^[0-9a-fA-F]{32}$").match(QFileInfo(path).fileName()).hasMatch();
        const bool sameParent = QFileInfo(path).absolutePath().compare(parent, Qt::CaseInsensitive) == 0;
        const bool ownName = QRegularExpression(legacy ? "^\\.qpe-undo-(?:[0-9a-fA-F]{32}|[0-9a-fA-F-]{36})$" : "^\\.qpe-undo-[0-9a-fA-F-]{36}$").match(QFileInfo(path).fileName()).hasMatch();
        if (!oldBackup && !(sameParent && ownName)) fail("Unexpected backup location; cleanup refused: " + path);
        ordinaryParents(path);
        const bool oldHash = legacy && !entry["legacyUpgraded"].toBool();
        const auto stamp = entry[QString(key) == "backup" ? "backupStamp" : QString(key) == "sourceBackup" ? "sourceStamp" : "stamp"].toString(oldHash ? entry["stamp"].toString() : QString());
        if (stamp.isEmpty() || (oldHash ? legacyFingerprint(path, cancel) : fileFingerprint(path, cancel)) != stamp) fail("Backup changed; cleanup refused: " + path);
        result.append(path);
    }
    return result;
}
/** @brief 衝突時の連番。 @param path 希望パス。 @return 空いているパス。 */
QString available(QString path) {
    const QFileInfo info(path); const QString suffix = info.isDir() || info.suffix().isEmpty() ? QString() : "." + info.suffix();
    const QString stem = suffix.isEmpty() ? info.fileName() : info.completeBaseName(); int number = 2;
    while (QFileInfo::exists(path)) path = info.dir().filePath(stem + QString(" (%1)").arg(number++) + suffix);
    return path;
}
/** @brief 未公開の作業コピーへ重ね、行先にだけある項目を保持する。
 * @param source 元項目。 @param target 作業コピー。 @param choices 個別の衝突選択。
 * @param cancel 中断。 @param progress コピー進捗。 @param relative ルートからの相対名。
 * @param reviewSource 衝突確認に表示したパス。
 */
void overlayEntry(const QString& source, const QString& target, const QJsonObject& choices,
                  const CancelFlag& cancel, const FileProgress& progress, const QString& relative = {},
                  const QString& reviewSource = {}) {
    check(cancel); ordinary(source);
    if (QFileInfo::exists(target)) {
        ordinary(target);
        if (QFileInfo(source).isDir() && QFileInfo(target).isDir()) {
            for (const auto& child : children(source)) overlayEntry(child.absoluteFilePath(), QDir(target).filePath(child.fileName()), choices,
                cancel, progress, relative.isEmpty() ? child.fileName() : relative + '/' + child.fileName(),
                reviewSource.isEmpty() ? QString() : QDir(reviewSource).filePath(child.fileName()));
            return;
        }
        const auto& choicePath = reviewSource.isEmpty() ? source : reviewSource;
        if (choices["_requireReviewed"].toBool() && !choices.contains(choicePath)) fail("A new merge conflict appeared; review the destination again: " + choicePath);
        const auto decision = choices.value(choicePath).toString(choices.value(relative).toString("replace"));
        if (!QStringList{"replace", "rename", "skip"}.contains(decision)) fail("Invalid per-item conflict choice: " + relative);
        if (decision == "skip") return;
        if (decision == "rename") { copyEntry(source, available(target), cancel, progress); return; }
        removeOwned(target);
    }
    copyEntry(source, target, cancel, progress);
}
/** @brief ハッシュへ構造と内容を流す。 @param path 元。 @param hash 集約。 @param cancel 取消し。 */
void hashEntry(const QString& path, QCryptographicHash& hash, const CancelFlag& cancel) {
    check(cancel); ordinary(path);
    if (QFileInfo(path).isDir()) {
        hash.addData("D", 1);
        for (const auto& child : children(path)) {
            const QByteArray name = child.fileName().toUtf8(); hash.addData(QByteArray::number(name.size()) + ":" + name);
            hashEntry(child.absoluteFilePath(), hash, cancel);
        }
    } else {
        hash.addData("F", 1); QFile file(path); if (!file.open(QIODevice::ReadOnly)) fail(file.errorString());
        while (!file.atEnd()) { check(cancel); const auto data = file.read(1024 * 1024); if (data.isEmpty() && file.error() != QFileDevice::NoError) fail(file.errorString()); hash.addData(data); }
    }
}
}
namespace detail {
/** @brief UNCは共有ルートで止め、ファイルシステムではないサーバー名へ問い合わせない。
 * @param input 絶対パス。 @return 対象からドライブまたは共有ルートまでの検査対象。
 * @note 共有内の親のリンク検証は維持し、Windowsの認証・ACLは変更しない。
 */
QStringList operationAncestors(const QString& input) {
    if (input.trimmed().isEmpty() || !QFileInfo(input).isAbsolute()) throw std::invalid_argument("Absolute path required");
    static const QRegularExpression shareRoot("^//[^/?]+/[^/]+/?$");
    QStringList result;
    auto path = normalized(input);
    while (!path.isEmpty()) {
        result.append(path);
        if (shareRoot.match(path).hasMatch()) break;
        const auto parent = normalized(QFileInfo(path).absolutePath());
        if (parent == path) break;
        path = parent;
    }
    return result;
}
}
void validateFileName(const QString& name) {
    static const QRegularExpression reserved("^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\\.|$)", QRegularExpression::CaseInsensitiveOption);
    if (name.isEmpty() || name == "." || name == ".." || name.endsWith(' ') || name.endsWith('.') || name.contains(QRegularExpression("[<>:\"/\\\\|?*\\x00-\\x1f]")) || reserved.match(name).hasMatch())
        throw std::invalid_argument("Enter a valid Windows file name (without a path)");
}
QString fileFingerprint(const QString& path, const CancelFlag& cancel) { QCryptographicHash hash(QCryptographicHash::Sha256); hashEntry(path, hash, cancel); return QString::fromLatin1(hash.result().toHex()); }
QString operationsDirectory() { return QFileInfo(settingsPath()).absolutePath() + "/native-file-history"; }
FileOperations::FileOperations(QString directory) : directory_(normalized(directory)) {}
FileResult FileOperations::run(const FileRequest& request, const CancelFlag& cancel, const FileProgress& progress, const FilePartial& partial) try {
    if (request.action == "syncFile") {
        const auto target = normalized(request.destination); QString parent = QFileInfo(target).absolutePath(); QStringList missing;
        while (!QFileInfo::exists(parent)) { missing.prepend(parent); const auto next = QFileInfo(parent).absolutePath(); if (next == parent) fail("Destination volume unavailable"); parent = next; }
        ordinaryParents(parent);
        for (const auto& folder : missing) { const auto created = run({"newFolder", {}, folder}, cancel, progress); if (!created.errors.isEmpty() || created.cancelled) return created; }
        auto copy = request; copy.action = "copy"; copy.destination = QFileInfo(target).absolutePath(); return run(copy, cancel, progress);
    }
    if (request.action == "mergeConflicts") {
        FileResult result; QJsonArray rows;
        if (request.paths.isEmpty() || request.destination.isEmpty() || !QFileInfo(request.destination).isAbsolute()) throw std::invalid_argument("Merge preview requires absolute source and destination paths");
        for (const auto& raw : request.paths) if (raw.isEmpty() || !QFileInfo(raw).isAbsolute()) throw std::invalid_argument("Merge source must be absolute");
        const auto destination = transferDirectory(request.destination);
        std::function<void(const QString&, const QString&, const QString&, const QString&, const QString&)> inspect;
        inspect = [&](const QString& source, const QString& target, const QString& shownSource, const QString& shownTarget, const QString& relative) {
            check(cancel); ordinary(source); if (!QFileInfo::exists(target)) return; ordinary(target);
            if (QFileInfo(source).isDir() && QFileInfo(target).isDir()) {
                for (const auto& child : children(source)) inspect(child.absoluteFilePath(), QDir(target).filePath(child.fileName()),
                    QDir(shownSource).filePath(child.fileName()), QDir(shownTarget).filePath(child.fileName()), relative + '/' + child.fileName());
                return;
            }
            if (rows.size() >= 10000) fail("Too many merge conflicts. Select fewer folders before merging.");
            const QFileInfo from(source), to(target);
            rows.append(QJsonObject{{"source", shownSource}, {"target", shownTarget}, {"resolvedSource", source}, {"resolvedTarget", target},
                {"relative", relative}, {"sourceSize", double(from.size())}, {"targetSize", double(to.size())},
                {"sourceModified", from.lastModified().toString(Qt::ISODate)}, {"targetModified", to.lastModified().toString(Qt::ISODate)},
                {"sourceFolder", from.isDir()}, {"targetFolder", to.isDir()}, {"sourceState", legacyMetadataFingerprint(source, cancel)}, {"targetState", legacyMetadataFingerprint(target, cancel)}});
        };
        for (const auto& raw : request.paths) {
            const auto source = normalized(raw), name = QFileInfo(source).fileName();
            inspect(transferSource(source), QDir(destination).filePath(name), source,
                    QDir(normalized(request.destination)).filePath(name), name);
        }
        result.extra = {{"query", "mergeConflicts"}, {"rows", rows}}; return result;
    }
    if (request.action == "media") return queryMedia(request, cancel);
    if (QStringList{"search", "listRecursive", "hash", "size", "duplicates", "compare", "diagnose", "drives"}.contains(request.action)) return runFileQuery(request, cancel, progress, partial);
    FileResult result;
    if (request.action == "browseZip") {
        if (request.paths.size() != 1) fail("Choose one ZIP");
        result.extra = {{"query", "browseZip"}, {"archive", request.paths[0]}, {"rows", inspectArchive(request.paths[0], cancel)}}; return result;
    }
    if (!QDir().mkpath(directory_)) fail("Cannot create operation history");
    QLockFile lock(directory_ + "/operation.lock"); lock.setStaleLockTime(0);
    if (!lock.tryLock()) fail("Another file operation is running");
    const QString journalPath = directory_ + "/journal.json";
    auto journal = loadJson(journalPath);
    const auto legacyDirectory = QFileInfo(directory_).absolutePath() + "/undo";
    LegacyHistoryLease legacyLease(legacyDirectory);
    const auto migrated = migrateLegacyHistory(legacyDirectory, journal);
    if (migrated != journal) { saveJson(journalPath, migrated); journal = migrated; }

    if (request.action == "historyReview") {
        const auto pending = journal["pending"].toObject(); if (pending.isEmpty()) return result;
        const auto digest = QString::fromLatin1(QCryptographicHash::hash(QJsonDocument(journal).toJson(QJsonDocument::Compact), QCryptographicHash::Sha256).toHex());
        if (!request.options["acknowledge"].toBool() || request.options["journalDigest"].toString() != digest) fail("History changed; inspect it again before acknowledging");
        auto reviewed = journal["reviewed"].toArray(); auto entry = pending; entry["reviewedAt"] = QDateTime::currentDateTimeUtc().toString(Qt::ISODate); reviewed.append(entry);
        // 部分適用の可能性がある元履歴はUndo対象から外すが、データも記録も一切削除しない。
        for (const auto& key : {"undo", "redo"}) { QJsonArray safe; for (const auto& value : journal[key].toArray()) { const auto item = value.toObject(); if (item["source"] == pending["source"] && item["target"] == pending["target"] && item["action"] == pending["action"]) reviewed.append(item); else safe.append(item); } journal[key] = safe; }
        journal["reviewed"] = reviewed; journal.remove("pending"); saveJson(journalPath, journal); result.extra["historyUpdated"] = true; return result;
    }
    if (!journal.value("pending").toObject().isEmpty()) fail("An interrupted file operation needs inspection. Originals/backups are retained in: " + directory_);
    if (request.action == "historyCleanup") {
        const int days = request.options["days"].toInt(30); const qint64 budget = qint64(request.options["budget"].toDouble(1024.0 * 1024 * 1024));
        if (days < 1 || days > 3650 || budget < 1024 * 1024) fail("Invalid history retention settings");
        /** @brief 削除前に検証を済ませた履歴候補。 */
        struct Candidate { QString stack; int index; QJsonObject entry; QStringList paths; qint64 bytes; QDateTime time; };
        QList<Candidate> candidates; qint64 total = 0; QSet<QString> protectedPaths;
        for (const auto& key : {"redo", "reviewed"}) for (const auto& value : journal[key].toArray()) for (const auto& field : {"backup", "sourceBackup", "undoHold"}) { const auto path = value.toObject()[field].toString(); if (!path.isEmpty()) protectedPaths.insert(normalized(path).toLower()); }
        for (const auto& key : {"undo", "retained"}) { const auto values = journal[key].toArray(); for (int i = 0; i < values.size(); ++i) {
            const auto entry = values[i].toObject(); const auto paths = retainedBackups(entry, cancel); qint64 bytes = 0;
            for (const auto& path : paths) { if (protectedPaths.contains(normalized(path).toLower())) fail("Backup is still referenced by recovery/Redo; cleanup refused"); bytes += backupBytes(path, cancel); }
            candidates.append({key, i, entry, paths, bytes, QDateTime::fromString(entry["time"].toString(), Qt::ISODate)}); total += bytes;
        } }
        std::stable_sort(candidates.begin(), candidates.end(), [](const Candidate& a, const Candidate& b) { return a.time < b.time; });
        QMap<QString, QSet<int>> removed; const auto originalJournal = journal;
        for (const auto& candidate : candidates) {
            check(cancel); if (total <= budget && candidate.time.isValid() && candidate.time.daysTo(QDateTime::currentDateTimeUtc()) < days) continue;
            // 永久削除が途中で失敗した場合も、削除対象をpendingとして残し次の変更を止める。
            auto intent = candidate.entry; intent["operationPhase"] = "cleanup"; journal["pending"] = intent; saveJson(journalPath, journal);
            for (const auto& path : candidate.paths) { if (progress) progress(path, total); removeOwned(path); }
            removed[candidate.stack].insert(candidate.index); total -= candidate.bytes; result.completed.append(candidate.entry["target"].toString(candidate.entry["source"].toString()));
            // 元配列の番号を維持して各確定点を書き出す。
            auto next = journal; for (auto it = removed.begin(); it != removed.end(); ++it) { QJsonArray keep; const auto original = originalJournal[it.key()].toArray(); for (int i = 0; i < original.size(); ++i) if (!it.value().contains(i)) keep.append(original[i]); next[it.key()] = keep; }
            next.remove("pending"); saveJson(journalPath, next); journal = next;
        }
        result.extra["historyUpdated"] = true; return result;
    }
    auto history = journal.value("undo").toArray(); auto redo = journal.value("redo").toArray();
    const auto save = [&] { journal["undo"] = history; journal["redo"] = redo; saveJson(journalPath, journal); };
    const auto intent = [&](const QJsonObject& entry) { journal["pending"] = entry; save(); };
    const auto commit = [&](const QJsonObject& entry) {
        if (!redo.isEmpty()) { auto retained = journal["retained"].toArray(); for (const auto& value : redo) retained.append(value); journal["retained"] = retained; redo = {}; }
        history.append(entry); journal.remove("pending"); save();
    };
    if (request.action == "undo" || request.action == "redo") {
        if (request.action == "redo" && !redo.isEmpty() && redo.last().toObject()["action"] == "legacyRedo") {
            const auto record = redo.last().toObject()["record"].toObject();
            const auto expected = record["expected"].toObject(); if (expected.isEmpty()) fail("Legacy Redo has no validation state");
            for (auto it = expected.begin(); it != expected.end(); ++it) {
                if (it.value().isNull()) { if (QFileInfo::exists(it.key())) fail("Legacy Redo destination changed"); }
                else if ((record["expectedKind"] == "metadata" ? legacyMetadataFingerprint(it.key(), cancel) : legacyFingerprint(it.key(), cancel)) != it.value().toString()) fail("Legacy Redo file changed");
            }
            const auto oldAction = record["action"].toString();
            if (!QStringList{"copy", "move", "duplicate", "rename", "create", "trash"}.contains(oldAction)) fail("Unknown legacy Redo operation");
            QJsonArray prepared, holds; const auto batch = "legacy-redo-" + record["id"].toString();
            for (const auto& raw : record["entries"].toArray()) {
                const auto old = raw.toObject(); const auto source = old["source"].toString(), target = old["target"].toString();
                if (!QFileInfo(source).isAbsolute() || (!target.isEmpty() && !QFileInfo(target).isAbsolute())) fail("Legacy Redo requires absolute paths");
                QJsonObject entry{{"action", oldAction == "create" ? "newFile" : oldAction}, {"source", source}, {"target", target}, {"batch", batch}, {"time", QDateTime::currentDateTimeUtc().toString(Qt::ISODate)}};
                if (oldAction == "trash") entry["restoredStamp"] = fileFingerprint(source, cancel);
                else if (oldAction == "rename") entry["stamp"] = fileFingerprint(source, cancel);
                else {
                    ordinaryParents(QFileInfo(target).absolutePath()); const auto hold = holding(QFileInfo(target).absolutePath());
                    holds.append(hold); intent({{"action", "legacyRedoPreparation"}, {"record", record}, {"holds", holds}});
                    const auto input = oldAction == "create" ? old["redoCopy"].toString() : source;
                    ordinaryParents(input);
                    if (record["conflict"] == "merge" && QFileInfo(target).isDir() && QFileInfo(source).isDir()) {
                        QJsonObject choices; const auto oldChoices = record["choices"].toObject(); for (auto it = oldChoices.begin(); it != oldChoices.end(); ++it) choices[QDir::fromNativeSeparators(it.key())] = it.value();
                        copyEntry(target, hold, cancel, progress); overlayEntry(source, hold, choices, cancel, progress);
                    }
                    else copyEntry(input, hold, cancel, progress);
                    if (old["stamp"].toString().isEmpty() || legacyFingerprint(hold, cancel) != old["stamp"].toString()) fail("Legacy Redo output differs from the original transaction");
                    entry["undoHold"] = hold; entry["stamp"] = fileFingerprint(hold, cancel);
                    if (QFileInfo::exists(target)) { entry["backup"] = holding(QFileInfo(target).absolutePath()); entry["backupStamp"] = fileFingerprint(target, cancel); }
                    if (oldAction == "move") { entry["sourceBackup"] = holding(QFileInfo(source).absolutePath()); entry["sourceStamp"] = fileFingerprint(source, cancel); }
                }
                prepared.prepend(entry);
            }
            // 全件の準備が確定するまで、元ファイルや旧履歴へは触れない。
            redo.removeLast(); for (const auto& entry : prepared) redo.append(entry); journal.remove("pending"); save();
        }
        auto& stack = request.action == "undo" ? history : redo;
        if (stack.isEmpty()) return result;
        const auto batch = stack.last().toObject()["batch"].toString();
        // 既知の競合で一括Undoを半分だけ適用しないよう、最新バッチ全体を先に検証する。
        const bool restoring = request.action == "undo";
        // 古い履歴はそのバッチがUndo先頭に来た時点で照合する。後続操作で変わった現在値を初回起動で信用しない。
        if (restoring) for (int i = stack.size() - 1; i >= 0; --i) {
            auto entry = stack[i].toObject(); if (i != stack.size() - 1 && (batch.isEmpty() || entry["batch"].toString() != batch)) break;
            if (!entry["legacy"].toBool() || entry["legacyUpgraded"].toBool()) continue;
            const auto target = entry["target"].toString(), backup = entry["backup"].toString(), sourceBackup = entry["sourceBackup"].toString();
            const auto oldStamp = entry["stamp"].toString();
            if (!target.isEmpty()) {
                if (oldStamp.isEmpty() || legacyFingerprint(target, cancel) != oldStamp) fail("Legacy Undo target changed; no files were changed");
                entry["stamp"] = fileFingerprint(target, cancel);
            }
            if (!backup.isEmpty()) {
                const auto expected = entry["backupStamp"].toString(entry["action"] == "trash" ? oldStamp : QString());
                if (expected.isEmpty() || legacyFingerprint(backup, cancel) != expected) fail("Legacy backup changed or has no verifiable fingerprint");
                entry["backupStamp"] = fileFingerprint(backup, cancel);
            }
            if (!sourceBackup.isEmpty()) {
                if (legacyFingerprint(sourceBackup, cancel) != oldStamp) fail("Legacy moved source changed");
                entry["sourceStamp"] = fileFingerprint(sourceBackup, cancel);
            }
            const auto action = entry["action"].toString();
            if (action == "move" && !entry["moved"].toBool()) entry["action"] = "copy";
            else if (action == "move" && sourceBackup.isEmpty()) entry["action"] = "legacyMove";
            else if (action == "create") entry["action"] = "newFile";
            else if (action == "trash") {
                if (entry["recycle"].isObject()) entry["receipt"] = entry.value("recycle");  // 挿入で無効になるQJsonValueRefを同じobject内で使い回さない。
                else if (!backup.isEmpty()) entry["action"] = "legacyTrash";
                else fail("Legacy trash receipt is unavailable; original history retained");
            }
            entry["legacyUpgraded"] = true; stack[i] = entry;
        }

        for (int i = stack.size() - 1; i >= 0; --i) {
            const auto entry = stack[i].toObject(); if (i != stack.size() - 1 && (batch.isEmpty() || entry["batch"].toString() != batch)) break;
            const auto action = entry["action"].toString(), source = entry["source"].toString(), target = entry["target"].toString();
            if ((action == "copy" || action == "move") && (entry.contains("shownSource") || entry.contains("shownTarget"))) {
                ordinaryParents(QFileInfo(source).absolutePath());
                ordinaryParents(QFileInfo(target).absolutePath());
            }
            if (action == "legacyTrash") {
                if (restoring ? QFileInfo::exists(source) || fileFingerprint(entry["backup"].toString(), cancel) != entry["backupStamp"].toString() : QFileInfo::exists(entry["backup"].toString()) || fileFingerprint(source, cancel) != entry["backupStamp"].toString()) fail("Legacy trash restore conflict");
                continue;
            }
            if (action == "trash") { if (restoring) validateRecycled(entry["receipt"].toObject(), source); else if (fileFingerprint(source, cancel) != entry["restoredStamp"].toString()) fail("Restored file changed; Redo refused"); continue; }
            const auto current = restoring ? target : (action == "rename" || action == "legacyMove") ? source : entry["undoHold"].toString();
            if (current.isEmpty() || fileFingerprint(current, cancel) != entry["stamp"].toString()) fail("Files changed outside QPE; Undo/Redo refused before changing the batch");
            const auto backup = entry["backup"].toString();
            if (action == "legacyMove" && !backup.isEmpty() && fileFingerprint(restoring ? backup : target, cancel) != entry["backupStamp"].toString()) fail("Legacy replacement changed before batch Undo/Redo");
            if (action == "rename" || action == "legacyMove") { if (QFileInfo::exists(restoring ? source : target) && !(action == "legacyMove" && !restoring && !backup.isEmpty()) && source.compare(target, Qt::CaseInsensitive)) fail("Undo/Redo destination exists"); }
            else if (restoring) {
                if (action == "move" && (QFileInfo::exists(source) || fileFingerprint(entry["sourceBackup"].toString(), cancel) != entry["sourceStamp"].toString())) fail("Move source changed; Undo refused");
                if (!backup.isEmpty() && fileFingerprint(backup, cancel) != entry["backupStamp"].toString()) fail("Replacement backup changed");
            } else {
                if (backup.isEmpty() ? QFileInfo::exists(target) : fileFingerprint(target, cancel) != entry["backupStamp"].toString()) fail("Redo destination changed");
                if (action == "move" && fileFingerprint(source, cancel) != entry["sourceStamp"].toString()) fail("Redo source changed");
            }
        }
        do {
        auto entry = stack.last().toObject(); const bool undo = request.action == "undo";
        const QString action = entry["action"].toString(), source = entry["source"].toString(), target = entry["target"].toString();
        const QString backup = entry["backup"].toString(), sourceBackup = entry["sourceBackup"].toString();
        check(cancel);
        const auto relocate = [&](const QString& from, const QString& to) { if (entry["legacy"].toBool()) relocateLegacy(from, to, cancel, progress); else renameExact(from, to); };
        if (action == "legacyTrash") {
            intent(entry); relocate(undo ? backup : source, undo ? source : backup);
        } else if (action == "legacyMove") {
            if (QFileInfo::exists(undo ? source : target) && (undo || backup.isEmpty())) fail("Legacy move destination exists");
            if (!backup.isEmpty() && fileFingerprint(undo ? backup : target, cancel) != entry["backupStamp"].toString()) fail("Legacy move replacement changed");
            intent(entry);
            if (undo) { relocate(target, source); if (!backup.isEmpty()) relocate(backup, target); }
            else { if (!backup.isEmpty()) relocate(target, backup); relocate(source, target); }
        } else if (action == "trash") {
            if (undo && QFileInfo::exists(source)) fail("Restore destination already exists");
            if (!undo && fileFingerprint(source, cancel) != entry["restoredStamp"].toString()) fail("Restored file changed; Redo refused");
            intent(entry);
            if (undo) { restoreRecycled(entry["receipt"].toObject(), source); entry["restoredStamp"] = fileFingerprint(source); }
            else entry["receipt"] = recyclePath(source, {});
        } else {
            const QString current = undo ? target : ((action == "rename" || action == "legacyMove") ? source : entry["undoHold"].toString());
            if (current.isEmpty() || fileFingerprint(current, cancel) != entry["stamp"].toString()) fail("Files changed outside QPE; Undo/Redo refused");
            if (action == "rename") {
                if (QFileInfo::exists(undo ? source : target) && source.compare(target, Qt::CaseInsensitive)) fail("Undo/Redo destination exists");
                intent(entry); relocate(current, undo ? source : target);
            } else if (undo) {
                if (action == "move" && (QFileInfo::exists(source) || fileFingerprint(sourceBackup, cancel) != entry["sourceStamp"].toString())) fail("Move source changed; Undo refused");
                if (!backup.isEmpty() && fileFingerprint(backup, cancel) != entry["backupStamp"].toString()) fail("Replacement backup changed");
                entry["undoHold"] = holding(QFileInfo(target).absolutePath()); intent(entry);
                renameExact(target, entry["undoHold"].toString());
                if (!backup.isEmpty()) relocate(backup, target);
                if (action == "move") relocate(sourceBackup, source);
            } else {
                if (backup.isEmpty() ? QFileInfo::exists(target) : fileFingerprint(target, cancel) != entry["backupStamp"].toString()) fail("Redo destination changed");
                if (action == "move" && fileFingerprint(source, cancel) != entry["sourceStamp"].toString()) fail("Redo source changed");
                intent(entry);
                if (!backup.isEmpty()) relocate(target, backup);
                renameExact(current, target);
                if (action == "move") relocate(source, sourceBackup);
            }
        }
        stack.removeLast(); (undo ? redo : history).append(entry); journal.remove("pending"); save();
        result.completed.append(undo ? currentDisplayPath(source, entry["shownSource"].toString())
                                     : currentDisplayPath(target, entry["shownTarget"].toString()));
        if (action == "rename" || action == "move" || action == "legacyMove") addPathChange(result, entry, undo);
        } while (!batch.isEmpty() && !stack.isEmpty() && stack.last().toObject()["batch"].toString() == batch);
        return result;
    }
    if (request.action == "createZip" || request.action == "extractZip") {
        const auto target = normalized(request.destination); ordinaryParents(QFileInfo(target).absolutePath());
        if (QFileInfo::exists(target)) fail("Archive destination already exists");
        for (const auto& source : request.paths) {
            ordinaryParents(source);
            if (within(target, normalized(source))) fail("Choose archive output outside the source");
        }
        const auto temporary = QDir(QFileInfo(target).absolutePath()).filePath(".qpe-archive-" + QUuid::createUuid().toString(QUuid::WithoutBraces));
        try {
            writeArchive(request, temporary, cancel, progress); check(cancel);
            QJsonObject entry{{"action", request.action}, {"source", target}, {"target", target}, {"stamp", fileFingerprint(temporary, cancel)}, {"time", QDateTime::currentDateTimeUtc().toString(Qt::ISODate)}};
            intent(entry); renameExact(temporary, target); commit(entry); result.completed.append(target);
        } catch (...) { if (QFileInfo::exists(temporary)) removeOwned(temporary); throw; }
        return result;
    }
    if (!QStringList{"copy", "move", "duplicate", "trash", "rename", "batchRename", "newFolder", "newFile"}.contains(request.action)) fail("Unknown file operation");
    if (!QStringList{"rename", "skip", "replace", "merge"}.contains(request.conflict)) fail("Unknown conflict policy");
    if (request.conflict == "merge" && request.action != "copy") fail("Folder merge is available for Copy only");
    for (const auto& path : request.paths) if (path.trimmed().isEmpty() || !QFileInfo(path).isAbsolute()) fail("File operations require non-empty absolute paths");
    const bool transfer = request.action == "copy" || request.action == "move";
    if ((transfer || request.action.startsWith("new")) && (request.destination.isEmpty() || !QFileInfo(request.destination).isAbsolute())) fail("Destination must be an absolute path");
    const auto shownDestination = transfer ? normalized(request.destination) : QString();
    const auto resolvedDestination = transfer ? transferDirectory(shownDestination) : QString();
    if (transfer && within(resolvedDestination, directory_)) fail("Root and QPE history directories are protected");
    QStringList paths = request.paths; paths.removeDuplicates();
    const auto batch = request.id.isEmpty() ? QUuid::createUuid().toString(QUuid::WithoutBraces) : request.id;
    if (request.options["legacyTransfer"].isObject()) {
        const auto legacy = request.options["legacyTransfer"].toObject();
        const auto id = legacy["id"].toString(); if (!QRegularExpression("^[a-fA-F0-9]{32}$").match(id).hasMatch()) fail("Invalid legacy transfer ID");
        const auto latest = loadJson(QFileInfo(directory_).absolutePath() + "/jobs/" + id + ".json");
        if (latest != legacy) fail("Legacy transfer record changed; close the old QPE and inspect it before retrying");
        if (legacy["prepared"].toBool()) {
            paths.clear();
            for (const auto& raw : legacy["items"].toArray()) {
                const auto item = raw.toObject(); const auto source = normalized(item["source"].toString());
                bool nativeDone = false; for (const auto& value : history) {
                    const auto entry = value.toObject();
                    if (entry["job"] == request.id && entry["shownSource"].toString(entry["source"].toString()) == source) nativeDone = true;
                }
                if (nativeDone) { paths.append(source); continue; }
                const auto state = item["state"].toString();
                if (state == "Completed") {
                    const auto output = item["output"].toString();
                    if (!output.isEmpty() && legacyFingerprint(output, cancel) != item["outputStamp"].toString()) fail("Previously completed legacy transfer changed");
                    continue;
                }
                if (state == "Running") {
                    bool found = false;
                    for (const auto& value : history) { const auto entry = value.toObject();
                        if (!entry["legacyTransactions"].toArray().contains(item["transaction"]) || entry["source"].toString() != source) continue;
                        if (request.action == "move" && !entry["moved"].toBool()) fail("Legacy move commit is incomplete; inspect Undo history before resuming");
                        const auto stamp = entry["stamp"].toString();
                        if ((entry["legacyUpgraded"].toBool() ? fileFingerprint(entry["target"].toString(), cancel) : legacyFingerprint(entry["target"].toString(), cancel)) != stamp) fail("Legacy committed destination changed");
                        found = true; break;
                    }
                    if (!found) fail("Legacy interrupted commit requires review; automatic replay refused");
                    continue;
                }
                if (state != "Pending" || legacyFingerprint(source, cancel) != item["stamp"].toString()) fail("Legacy prepared source changed");
                const auto target = request.action == "duplicate" ? source : QDir(request.destination).filePath(QFileInfo(source).fileName());
                if (item["targetStamp"].isNull() ? QFileInfo::exists(target) : legacyFingerprint(target, cancel) != item["targetStamp"].toString()) fail("Legacy prepared destination changed");
                paths.append(source);
            }
        }
    }
    if (request.action == "batchRename") {
        QSet<QString> targets;
        for (const auto& raw : paths) {
            const auto name = request.options["names"].toObject()[raw].toString(); validateFileName(name);
            const auto target = QFileInfo(raw).dir().absoluteFilePath(name).toLower();
            if (targets.contains(target) || (QFileInfo::exists(target) && normalized(raw).compare(target, Qt::CaseInsensitive))) fail("Batch rename has a duplicate or existing destination: " + target);
            targets.insert(target);
        }
    }
    if (request.action.startsWith("new")) paths = QStringList{request.destination};
    QJsonObject resolvedSources;
    QHash<QString, QString> sourceErrors;
    if (transfer) {
        QSet<QString> seen;
        QStringList unique;
        for (const auto& raw : paths) {
            try {
                check(cancel);
                const auto source = transferSource(normalized(raw));
                resolvedSources[raw] = source;
                const auto key = source.toCaseFolded();
                if (seen.contains(key)) continue;
                seen.insert(key);
            } catch (const Cancelled&) { result.cancelled = true; return result; }
            catch (const std::exception& error) {
                if (!request.id.isEmpty()) throw;
                sourceErrors.insert(raw, QString::fromUtf8(error.what()));
            }
            unique.append(raw);
        }
        paths = unique;
    }
    for (const auto& raw : request.options["mergeReviewed"].toArray()) {
        const auto row = raw.toObject();
        const auto shownSource = row["source"].toString(), shownTarget = row["target"].toString();
        const auto shownRoot = std::find_if(paths.cbegin(), paths.cend(), [&](const QString& path) {
            return resolvedSources.contains(path) && within(shownSource, normalized(path));
        });
        if (shownRoot == paths.cend() || !within(shownTarget, shownDestination))
            fail("Merge source/destination changed after preview. Review the conflicts again.");
        // 同じ解決済みルートから検査とコピーを行い、確認中のリンク差し替えで別の項目を上書きしない。
        const auto root = normalized(*shownRoot);
        const auto source = resolvedSources.value(*shownRoot).toString() + shownSource.mid(root.size());
        const auto target = QDir(resolvedDestination).filePath(QDir(shownDestination).relativeFilePath(shownTarget));
        if (source.compare(row["resolvedSource"].toString(source), Qt::CaseInsensitive)
            || target.compare(row["resolvedTarget"].toString(target), Qt::CaseInsensitive)
            || legacyMetadataFingerprint(source, cancel) != row["sourceState"].toString()
            || legacyMetadataFingerprint(target, cancel) != row["targetState"].toString())
            fail("Merge source/destination changed after preview. Review the conflicts again.");
    }
    QJsonObject prepared;
    QString recordPath;
    if (!request.id.isEmpty() && QStringList{"copy", "move", "duplicate"}.contains(request.action)) {
        recordPath = directory_ + "/jobs/" + request.id + ".json";
        auto record = loadJson(recordPath); prepared = record["prepared"].toObject();
        if (transfer) {
            const auto recorded = record["resolvedSources"].toObject();
            if (resolvedDestination.compare(record["resolvedDestination"].toString(resolvedDestination), Qt::CaseInsensitive))
                fail("The destination folder link changed; start a new transfer: " + shownDestination);
            for (auto it = resolvedSources.constBegin(); it != resolvedSources.constEnd(); ++it)
                if (recorded.contains(it.key()) && it.value().toString().compare(recorded[it.key()].toString(), Qt::CaseInsensitive))
                    fail("A source folder link changed; start a new transfer: " + it.key());
            record["resolvedDestination"] = resolvedDestination;
            record["resolvedSources"] = resolvedSources;
        }
        for (const auto& raw : paths) {
            const auto shownSource = normalized(raw);
            const auto source = resolvedSources.value(raw).toString(shownSource);
            bool committed = false;
            for (const auto& value : history) {
                const auto entry = value.toObject();
                if (entry["job"].toString() == request.id && entry["shownSource"].toString(entry["source"].toString()) == shownSource) committed = true;
            }
            if (!committed && !prepared.contains(raw)) prepared[raw] = fileFingerprint(source, cancel);
        }
        record["prepared"] = prepared; record["state"] = "running"; saveJson(recordPath, record);
    }
    for (const QString& raw : paths) {
        try {
            check(cancel);
            if (sourceErrors.contains(raw)) fail(sourceErrors[raw]);
            const auto shownSource = normalized(raw), source = resolvedSources.value(raw).toString(shownSource);
            const QFileInfo info(source);
            bool committed = false;
            for (const auto& value : history) {
                const auto done = value.toObject();
                if (!request.id.isEmpty() && done["job"].toString() == request.id && done["shownSource"].toString(done["source"].toString()) == shownSource) {
                    if (done["source"].toString().compare(source, Qt::CaseInsensitive)) fail("A source folder link changed; start a new transfer: " + shownSource);
                    if (fileFingerprint(done["target"].toString(), cancel) != done["stamp"].toString()) fail("Completed transfer changed; resume refused");
                    if (request.action == "move" && (QFileInfo::exists(source) || fileFingerprint(done["sourceBackup"].toString(), cancel) != done["sourceStamp"].toString())) fail("Move original changed; resume refused");
                    committed = true;
                }
            }
            for (const auto& value : redo) if (!request.id.isEmpty() && value.toObject()["job"].toString() == request.id) fail("Transfer was undone; inspect history before resuming");
            if (committed) continue;
            if (prepared.contains(raw) && fileFingerprint(raw, cancel) != prepared[raw].toString()) fail("Prepared source changed; resume refused");
            const bool shareRoot = source.startsWith("//") && detail::operationAncestors(source).size() == 1;
            if (info.isRoot() || shareRoot || within(source, directory_) || within(directory_, source)) fail("Root and QPE history directories are protected");
            bool nested = false;
            for (const auto& other : paths) {
                const auto parent = resolvedSources.value(other).toString(normalized(other));
                if (source.compare(parent, Qt::CaseInsensitive) && within(source, parent)) nested = true;
            }
            if (nested) continue;
            if (request.action.startsWith("new")) ordinaryParents(info.absolutePath()); else ordinaryParents(source);
            QJsonObject entry{{"action", request.action == "batchRename" ? "rename" : request.action}, {"source", source}, {"batch", batch}, {"job", request.id}, {"time", QDateTime::currentDateTimeUtc().toString(Qt::ISODate)}};
            if (request.action == "trash") {
                intent(entry); entry["receipt"] = recyclePath(source, cancel);
            } else if (request.action == "rename" || request.action == "batchRename") {
                const auto newName = request.action == "batchRename" ? request.options["names"].toObject()[raw].toString() : request.options["name"].toString(); validateFileName(newName);
                const auto target = info.dir().filePath(newName);
                if (QFileInfo::exists(target) && source.compare(target, Qt::CaseInsensitive)) fail("Destination already exists: " + target);
                entry["target"] = target; entry["stamp"] = fileFingerprint(source, cancel); intent(entry); renameExact(source, target);
            } else if (request.action.startsWith("new")) {
                validateFileName(info.fileName()); if (info.exists()) fail("Destination already exists");
                entry["target"] = source; intent(entry);
                if (request.action == "newFolder") makeDirectory(source);
                else { QFile file(source); if (!file.open(QIODevice::WriteOnly | QIODevice::NewOnly)) fail("Cannot create file: " + source + "\n" + file.errorString()); }
                entry["stamp"] = fileFingerprint(source);
            } else {
                const QString destination = transfer ? resolvedDestination : info.absolutePath();
                ordinaryParents(destination);
                if (!QFileInfo(destination).isDir() || within(destination, source)) fail("Choose an existing destination outside the source");
                QString target = QDir(destination).filePath(info.fileName());
                bool merge = false;
                if (request.action == "move" && target.compare(source, Qt::CaseInsensitive) == 0) continue;
                if (QFileInfo::exists(target) || QFileInfo(target).isSymLink()) {
                    auto policy = request.conflict;
                    if (policy == "merge" && !(info.isDir() && QFileInfo(target).isDir())) {
                        const auto choices = request.options["choices"].toObject();
                        if (choices["_requireReviewed"].toBool() && !choices.contains(shownSource)) fail("A new merge conflict appeared; review the destination again: " + shownSource);
                        policy = choices[shownSource].toString("replace");
                    }
                    if (!QStringList{"skip", "rename", "replace", "merge"}.contains(policy)) fail("Invalid conflict policy");
                    if (policy == "skip") continue;
                    if (policy == "rename" || target.compare(source, Qt::CaseInsensitive) == 0) target = available(target);
                    else {
                        merge = policy == "merge" && info.isDir() && QFileInfo(target).isDir();
                        entry["backup"] = holding(destination); entry["backupStamp"] = fileFingerprint(target, cancel);
                    }
                }
                entry["target"] = target; entry["stamp"] = fileFingerprint(source, cancel); entry["sourceStamp"] = entry.value("stamp");
                if (transfer && source != shownSource) entry["shownSource"] = shownSource;
                if (transfer && destination != shownDestination) entry["shownTarget"] = QDir(shownDestination).filePath(QFileInfo(target).fileName());
                const QString temporary = QDir(destination).filePath(".qpe-copy-" + QUuid::createUuid().toString(QUuid::WithoutBraces));
                try {
                    if (merge) {
                        copyEntry(target, temporary, cancel, progress);
                        overlayEntry(source, temporary, request.options["choices"].toObject(), cancel, progress, {}, shownSource);
                        entry["stamp"] = fileFingerprint(temporary, cancel);
                    } else copyEntry(source, temporary, cancel, progress);
                    if (fileFingerprint(temporary, cancel) != entry["stamp"].toString() || fileFingerprint(source, cancel) != entry["sourceStamp"].toString()) fail("Source changed during copy");
                    if (entry.contains("backup") && fileFingerprint(target, cancel) != entry["backupStamp"].toString()) fail("Destination changed during copy");
                    if (request.action == "move") entry["sourceBackup"] = holding(info.absolutePath());
                    if (entry.contains("shownSource") || entry.contains("shownTarget")) {
                        ordinaryParents(source);
                        ordinaryParents(destination);
                    }
                    check(cancel); intent(entry);
                    if (entry.contains("backup")) renameExact(target, entry["backup"].toString());
                    renameExact(temporary, target);
                    if (request.action == "move") renameExact(source, entry["sourceBackup"].toString());
                } catch (...) {
                    if (QFileInfo::exists(temporary)) { try { removeOwned(temporary); } catch (...) {} }
                    throw;
                }
            }
            // 古いRedoの原本は削除せず記録を保全。自動pruneは行わない。
            if (!redo.isEmpty()) { auto retained = journal["retained"].toArray(); for (const auto& value : redo) retained.append(value); journal["retained"] = retained; redo = {}; }
            commit(entry); result.completed.append(entry["shownTarget"].toString(entry["target"].toString(source)));
            if (entry["action"] == "rename" || entry["action"] == "move") addPathChange(result, entry, false);
        } catch (const Cancelled&) { result.cancelled = true; break; }
          catch (const std::exception& error) { result.errors.append(QString::fromUtf8(error.what())); if (!journal["pending"].toObject().isEmpty()) { result.warnings.append("Interrupted operation recorded; inspect retained originals before retrying."); break; } }
    }
    return result;
} catch (const std::exception& error) { qWarning().noquote() << "QPE file operation" << request.action << request.destination << QString::fromUtf8(error.what()); throw; }
namespace {
/** @brief 自己破棄のワーカー。UIへはqueued signalのみ。 */
class FileJob final : public QObject, public QRunnable {
    Q_OBJECT
public:
    /** @brief 値を所有する。 @param request 要求。 @param flag 取消し。 */
    FileJob(FileRequest request, CancelFlag flag, CancelFlag pause) : request_(std::move(request)), flag_(std::move(flag)), pause_(std::move(pause)) { ++workers; }
    /** @brief DLL生存数を戻す。 */
    ~FileJob() override { --workers; }
    /** @brief Qt UI/Mayaに触れず実行する。 */
    void run() override {
        FileResult result;
        threadPause = pause_;
        QElapsedTimer notification; notification.start();
        QString previousPath; qint64 previousBytes = 0, transferred = 0;
        const bool transfer = QStringList{"copy", "move", "duplicate"}.contains(request_.action);
        // 高速SSDで毎MBのqueued signalがUIへ滞留しないよう、描画通知だけを間引く。
        try { result = FileOperations(operationsDirectory()).run(request_, flag_, [&](const QString& p, qint64 n) {
            if (transfer) { transferred += p == previousPath && n >= previousBytes ? n - previousBytes : n; previousPath = p; previousBytes = n; }
            if (notification.elapsed() >= 100) { notification.restart(); emit progress(p, transfer ? transferred : n); }
        }, [this](const QJsonObject& value) { emit partial(value); }); }
        catch (const std::exception& e) { result.errors.append(QString::fromUtf8(e.what())); }
        // 例外/取消しでも要求世代を配送する。UIが古い失敗を現在の選択へ混ぜないため。
        if (request_.options.contains("token")) { result.extra["token"] = request_.options["token"]; result.extra["path"] = request_.paths.value(0); }
        if (flag_ && flag_->load()) result.cancelled = true;
        threadPause.reset();
        if (transfer) { emit progress(previousPath, transferred); result.extra["transferredBytes"] = double(transferred); }
        if (!request_.id.isEmpty()) {
            try {
                const auto path = operationsDirectory() + "/jobs/" + request_.id + ".json"; auto record = loadJson(path);
                record["state"] = result.cancelled || (flag_ && flag_->load()) ? "cancelled" : result.errors.isEmpty() ? "completed" : "failed";
                record["errors"] = QJsonArray::fromStringList(result.errors); saveJson(path, record);
            } catch (const std::exception& e) { result.warnings.append(QString::fromUtf8(e.what())); }
        }
        emit completed({{"completed", QJsonArray::fromStringList(result.completed)}, {"errors", QJsonArray::fromStringList(result.errors)},
            {"warnings", QJsonArray::fromStringList(result.warnings)}, {"extra", result.extra}, {"cancelled", result.cancelled}});
    }
signals:
    /** @brief 途中結果配送。 @param value 世代と行データ。 */
    void partial(QJsonObject value);
    /** @brief 結果配送。 @param result 値。 */
    void completed(QJsonObject result);
    /** @brief 進捗配送。 @param path 対象。 @param bytes 量。 */
    void progress(QString path, qint64 bytes);
private:
    FileRequest request_; CancelFlag flag_; CancelFlag pause_;
};
}
FileResult fileResultFromJson(const QJsonObject& value) {
    FileResult result;
    for (const auto& item : value["completed"].toArray()) result.completed.append(item.toString());
    for (const auto& item : value["errors"].toArray()) result.errors.append(item.toString());
    for (const auto& item : value["warnings"].toArray()) result.warnings.append(item.toString());
    result.extra = value["extra"].toObject(); result.cancelled = value["cancelled"].toBool(); return result;
}
FileJobs::FileJobs(QObject* parent) : QObject(parent) {}
FileJobs::~FileJobs() { cancel(); }
void FileJobs::enqueue(const FileRequest& request) {
    auto value = request;
    if (QStringList{"copy", "move", "duplicate"}.contains(value.action) && value.id.isEmpty()) {
        value.id = QUuid::createUuid().toString(QUuid::WithoutBraces);
        const auto directory = operationsDirectory() + "/jobs"; if (!QDir().mkpath(directory)) throw std::runtime_error("Cannot persist file job");
        saveJson(directory + '/' + value.id + ".json", {{"id", value.id}, {"action", value.action}, {"paths", QJsonArray::fromStringList(value.paths)},
            {"destination", value.destination}, {"conflict", value.conflict}, {"options", value.options}, {"state", "queued"}});
    }
    queue_.enqueue(value); next();
}
void FileJobs::cancel() { cancelQueued(); cancelActive(); }
void FileJobs::cancelActive() { if (cancel_) cancel_->store(true); if (pause_) pause_->store(false); }
void FileJobs::cancelQueued() {
    while (!queue_.isEmpty()) { const auto request = queue_.dequeue(); if (request.id.isEmpty()) continue;
        try { const auto path = operationsDirectory() + "/jobs/" + request.id + ".json"; auto record = loadJson(path); record["state"] = "cancelled"; saveJson(path, record); }
        catch (const std::exception& e) { qWarning().noquote() << "QPE cancelled job record retained:" << e.what(); }
    }
}
void FileJobs::pauseActive(bool value) { if (pause_) pause_->store(value); }
void FileJobs::pauseQueue(bool value) { queuePaused_ = value; if (!value) next(); }
void FileJobs::moveQueued(int index, int delta) { const int next = index + delta; if (index >= 0 && index < queue_.size() && next >= 0 && next < queue_.size()) queue_.swapItemsAt(index, next); }
QJsonArray FileJobs::records() const {
    QJsonArray rows;
    if (running_) rows.append(QJsonObject{{"action", active_.action}, {"id", active_.id}, {"state", pause_ && pause_->load() ? "paused" : "running"}, {"destination", active_.destination}, {"bytes", double(transferred_)}, {"bytesPerSecond", elapsed_.isValid() ? transferred_ * 1000. / qMax(qint64(1), elapsed_.elapsed()) : 0.}, {"path", progressPath_}});
    for (int i = 0; i < queue_.size(); ++i) { const auto& v = queue_[i]; rows.append(QJsonObject{{"action", v.action}, {"id", v.id}, {"state", "queued"}, {"index", i}, {"destination", v.destination}}); }
    return rows;
}
void FileJobs::discard(const QString& id) {
    const bool legacy = id.startsWith("legacy:"); const auto key = legacy ? legacyTransferId(id.mid(7)) : id;
    if (!QRegularExpression("^[a-fA-F0-9-]{36}$").match(key).hasMatch()) throw std::invalid_argument("Invalid job id");
    if (running_ && active_.id == key) throw std::runtime_error("Cancel the active transfer before discarding");
    for (const auto& item : queue_) if (item.id == key) throw std::runtime_error("Cancel queued transfers before discarding");
    if (!QDir().mkpath(operationsDirectory())) throw std::runtime_error("Cannot create operation history");
    QLockFile lock(operationsDirectory() + "/operation.lock"); lock.setStaleLockTime(0); if (!lock.tryLock()) throw std::runtime_error("Another file operation is running");
    auto record = legacy ? loadJson(QFileInfo(operationsDirectory()).absolutePath() + "/jobs/" + id.mid(7) + ".json") : loadJson(operationsDirectory() + "/jobs/" + key + ".json");
    if (record.isEmpty()) throw std::runtime_error("Job record missing");
    record["id"] = key; record["state"] = "discarded"; saveJson(operationsDirectory() + "/jobs/" + key + ".json", record);
}
void FileJobs::resume(const QString& id) {
    if (id.startsWith("legacy:")) {
        const auto oldId = id.mid(7); if (!QRegularExpression("^[a-fA-F0-9]{32}$").match(oldId).hasMatch()) throw std::invalid_argument("Invalid legacy job id");
        const auto old = loadJson(QFileInfo(operationsDirectory()).absolutePath() + "/jobs/" + oldId + ".json");
        if (old["version"].toInt() != 1 || !QStringList{"copy", "move", "duplicate"}.contains(old["action"].toString()) || QStringList{"Completed", "Discarded"}.contains(old["state"].toString())) throw std::runtime_error("Legacy job cannot be resumed");
        if (!old["paths"].isArray() || old["paths"].toArray().isEmpty()) throw std::invalid_argument("Legacy transfer has no sources");
        for (const auto& path : old["paths"].toArray()) if (!path.isString() || path.toString().isEmpty() || !QFileInfo(path.toString()).isAbsolute()) throw std::invalid_argument("Legacy transfer source must be absolute");
        const auto nativeId = legacyTransferId(oldId);
        QJsonObject choices; const auto oldChoices = old["choices"].toObject();
        for (auto it = oldChoices.begin(); it != oldChoices.end(); ++it) choices[QDir::fromNativeSeparators(it.key())] = it.value();
        const auto destination = operationsDirectory() + "/jobs/" + nativeId + ".json";
        if (!QFileInfo::exists(destination)) saveJson(destination, {{"id", nativeId}, {"action", old["action"]}, {"paths", old["paths"]}, {"destination", old["destination"]},
            {"conflict", old["conflict"]}, {"state", "queued"}, {"options", QJsonObject{{"legacyTransfer", old}, {"choices", choices}}}});
        resume(nativeId); return;
    }
    if (!QRegularExpression("^[a-fA-F0-9-]{36}$").match(id).hasMatch()) throw std::invalid_argument("Invalid job id");
    if (running_ && active_.id == id) throw std::runtime_error("Job already running");
    for (const auto& queued : queue_) if (queued.id == id) throw std::runtime_error("Job already queued");
    const auto record = loadJson(operationsDirectory() + "/jobs/" + id + ".json");
    if (record.isEmpty() || QStringList{"completed", "discarded"}.contains(record["state"].toString())) throw std::runtime_error("Job is not resumable");
    FileRequest request; request.id = id; request.action = record["action"].toString(); request.destination = record["destination"].toString();
    request.conflict = record["conflict"].toString("rename"); request.options = record["options"].toObject();
    for (const auto& value : record["paths"].toArray()) request.paths.append(value.toString());
    enqueue(request);
}
bool FileJobs::busy() const { return running_ || !queue_.isEmpty(); }
int FileJobs::liveWorkers() { return workers.load(); }
bool FileJobs::releaseWorkers(bool wait) {
    if (!wait && (workers.load() || (filePool && filePool->activeThreadCount()))) return false;
    if (filePool) { filePool->waitForDone(); delete filePool; filePool = nullptr; }
    return true;
}
void FileJobs::next() {
    if (running_ || queue_.isEmpty() || queuePaused_) return;
    running_ = true; cancel_ = std::make_shared<std::atomic_bool>(false); pause_ = std::make_shared<std::atomic_bool>(false);
    const auto request = queue_.dequeue(); active_ = request; transferred_ = 0; progressPath_.clear(); elapsed_.start(); auto* job = new FileJob(request, cancel_, pause_);
    connect(job, &FileJob::progress, this, [this](const QString& path, qint64 bytes) { transferred_ = bytes; progressPath_ = path; emit progress(path, bytes); }, Qt::QueuedConnection);
    connect(job, &FileJob::partial, this, &FileJobs::partial, Qt::QueuedConnection);
    connect(job, &FileJob::completed, this, [this](const QJsonObject& result) { running_ = false; emit finished(result); next(); }, Qt::QueuedConnection);
    emit started(request.action); if (!filePool) filePool = new QThreadPool; filePool->start(job);
}
}
#include "file_operations.moc"
