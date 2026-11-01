/** @file legacy_history.cpp @brief 旧履歴の精度と元ファイルを保持する読み込み境界。 */
#include "legacy_history.h"
#include <QCryptographicHash>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonArray>
#include <QRegularExpression>
#include <algorithm>
#include <stdexcept>
#define NOMINMAX
#include <windows.h>
namespace qpe {
namespace {
/** @brief 原本を保持したまま失敗を通知する。 @param message 理由。 */
void error(const QString& message) { throw std::runtime_error(message.toStdString()); }
/** @brief 大きすぎる/破損した履歴を空扱いしない。 @param path 履歴。 @return 元バイト。 */
QByteArray read(const QString& path) {
    QFile file(path); if (!file.exists()) return {};
    if (file.size() > 32 * 1024 * 1024 || !file.open(QIODevice::ReadOnly)) error("Cannot read legacy history: " + path);
    return file.readAll();
}
/** @brief 64bit file IDをdoubleへ丸める前に文字列化する。 @param bytes 旧JSON。 @return JSON文書。 */
QJsonDocument parse(const QByteArray& bytes) {
    QString text = QString::fromUtf8(bytes);
    const QRegularExpression ids("(\"(?:identity|metadataIdentity)\"\\s*:\\s*)\\[\\s*([0-9]+)\\s*,\\s*([0-9]+)\\s*\\]");
    auto matches = ids.globalMatch(text); QList<QRegularExpressionMatch> edits; while (matches.hasNext()) edits.append(matches.next());
    for (auto it = edits.crbegin(); it != edits.crend(); ++it) text.replace(it->capturedStart(), it->capturedLength(), it->captured(1) + '"' + it->captured(2) + ':' + it->captured(3) + '"');
    QJsonParseError issue; const auto doc = QJsonDocument::fromJson(text.toUtf8(), &issue);
    if (issue.error != QJsonParseError::NoError) error("Invalid legacy history; original retained");
    return doc;
}
}
LegacyHistoryLease::LegacyHistoryLease(const QString& directory) {
    if (!QFileInfo(directory).isDir()) return;
    const auto path = QDir::toNativeSeparators(directory + "/operation.lock");
    HANDLE handle = CreateFileW(reinterpret_cast<LPCWSTR>(path.utf16()), GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (handle == INVALID_HANDLE_VALUE) error("Legacy QPE history is unavailable");
    OVERLAPPED offset{};
    if (!LockFileEx(handle, LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, &offset)) { CloseHandle(handle); error("Another legacy QPE file operation is running"); }
    handle_ = handle;
}
LegacyHistoryLease::~LegacyHistoryLease() { if (handle_) CloseHandle(static_cast<HANDLE>(handle_)); }
QJsonObject migrateLegacyHistory(const QString& directory, QJsonObject journal) {
    auto candidates = QDir(directory).entryInfoList({"journal.json", "journal-recovery-*.json"}, QDir::Files, QDir::Time);
    const auto bytes = candidates.isEmpty() ? QByteArray() : read(candidates.first().absoluteFilePath());
    const auto redoBytes = read(directory + "/redo.json");
    const auto digest = QString::fromLatin1(QCryptographicHash::hash(bytes + '\0' + redoBytes, QCryptographicHash::Sha256).toHex());
    if (journal.contains("legacyDigest")) {
        if (journal["legacyDigest"].toString() != digest) error("Legacy QPE history changed after migration. Close the old QPE and review both histories; no files were changed.");
        return journal;
    }
    if (bytes.isEmpty() && redoBytes.isEmpty()) return journal;
    const bool hadNativeHistory = !journal["undo"].toArray().isEmpty() || !journal["redo"].toArray().isEmpty();
    QJsonArray imported;
    if (!bytes.isEmpty()) {
        const auto document = parse(bytes); if (!document.isArray()) error("Legacy Undo journal is not an array");
        for (const auto& value : document.array()) {
            if (!value.isObject()) error("Invalid legacy transaction"); const auto transaction = value.toObject();
            if (!transaction["entries"].isArray() || !QStringList{"copy", "move", "duplicate", "rename", "create", "trash"}.contains(transaction["action"].toString())) error("Invalid legacy entries / action");
            for (const auto& item : transaction["entries"].toArray()) {
                if (!item.isObject()) error("Invalid legacy entry"); auto entry = item.toObject();
                if (!QFileInfo(entry["source"].toString()).isAbsolute() || entry["source"].toString().isEmpty()) error("Legacy source path must be absolute");
                for (const auto& field : {"target", "backup", "sourceBackup"}) if (!entry[field].toString().isEmpty() && !QFileInfo(entry[field].toString()).isAbsolute()) error("Legacy history paths must be absolute");
                if (transaction["action"] != "trash" && entry["target"].toString().isEmpty()) error("Legacy target path is missing");
                entry["action"] = transaction["action"]; entry["batch"] = "legacy-" + transaction["id"].toString();
                entry["time"] = QDateTime::fromMSecsSinceEpoch(qint64(transaction["time"].toDouble() * 1000), Qt::UTC).toString(Qt::ISODate);
                entry["legacy"] = true; entry["legacyDirectory"] = directory;
                entry["legacyTransactions"] = transaction.contains("recoveryTransactions") ? transaction["recoveryTransactions"] : QJsonArray{transaction["id"]};
                for (const auto& field : {"source", "target", "backup", "sourceBackup"}) if (!entry[field].toString().isEmpty()) entry[field] = QDir::cleanPath(QDir::fromNativeSeparators(entry[field].toString()));
                imported.append(entry);
            }
        }
    }
    for (const auto& entry : journal["undo"].toArray()) imported.append(entry); journal["undo"] = imported;
    if (!redoBytes.isEmpty()) {
        const auto document = parse(redoBytes); if (!document.isObject()) error("Legacy Redo journal is not an object");
        if (!hadNativeHistory) journal["redo"] = QJsonArray{QJsonObject{{"action", "legacyRedo"}, {"record", document.object()}}};
        else journal["retainedLegacyRedo"] = document.object();
    }
    journal["legacyDigest"] = digest; journal["legacyDirectory"] = directory; return journal;
}
QString legacyFingerprint(const QString& path, const CancelFlag& cancel) {
    if (cancel && cancel->load()) error("Cancelled");
    const auto native = QDir::toNativeSeparators(path); const auto flags = GetFileAttributesW(reinterpret_cast<LPCWSTR>(native.utf16()));
    if (flags == INVALID_FILE_ATTRIBUTES || flags & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_OFFLINE | 0x40000 | 0x400000)) error("Unavailable / linked legacy history item: " + path);
    QCryptographicHash hash(QCryptographicHash::Sha256);
    if (flags & FILE_ATTRIBUTE_DIRECTORY) {
        hash.addData("D", 1); auto children = checkedChildren(path);
        // PythonのUnicodeコードポイント順に合わせる。UTF-16のサロゲート順にはしない。
        std::sort(children.begin(), children.end(), [](const QFileInfo& a, const QFileInfo& b) { return a.fileName().toUcs4() < b.fileName().toUcs4(); });
        for (const auto& child : children) { hash.addData(child.fileName().toUtf8()); hash.addData(legacyFingerprint(child.absoluteFilePath(), cancel).toLatin1()); }
    } else {
        hash.addData("F", 1); QFile file(path); if (!file.open(QIODevice::ReadOnly)) error("Cannot validate legacy item: " + path);
        while (!file.atEnd()) { if (cancel && cancel->load()) error("Cancelled"); const auto block = file.read(1024 * 1024); if (block.isEmpty() && file.error() != QFileDevice::NoError) error(file.errorString()); hash.addData(block); }
    }
    return QString::fromLatin1(hash.result().toHex());
}
QString legacyTransferId(const QString& id) {
    if (!QRegularExpression("^[a-fA-F0-9]{32}$").match(id).hasMatch()) error("Invalid legacy transfer ID");
    return id.left(8) + '-' + id.mid(8, 4) + '-' + id.mid(12, 4) + '-' + id.mid(16, 4) + '-' + id.mid(20);
}
QFileInfoList checkedChildren(const QString& path) {
    WIN32_FIND_DATAW data{}; const auto pattern = QDir::toNativeSeparators(QDir(path).filePath("*"));
    HANDLE search = FindFirstFileW(reinterpret_cast<LPCWSTR>(pattern.utf16()), &data);
    if (search == INVALID_HANDLE_VALUE) error("Cannot enumerate: " + path + QString(" (%1)").arg(GetLastError()));
    QFileInfoList result;
    do { const auto name = QString::fromWCharArray(data.cFileName); if (name != "." && name != "..") result.append(QFileInfo(QDir(path).filePath(name))); } while (FindNextFileW(search, &data));
    const DWORD last = GetLastError(); FindClose(search);
    if (last != ERROR_NO_MORE_FILES) error("Directory enumeration interrupted: " + path);
    std::sort(result.begin(), result.end(), [](const QFileInfo& a, const QFileInfo& b) { return a.fileName() < b.fileName(); });
    return result;
}
QString legacyMetadataFingerprint(const QString& path, const CancelFlag& cancel) {
    if (cancel && cancel->load()) error("Cancelled");
    const auto native = QDir::toNativeSeparators(path);
    HANDLE handle = CreateFileW(reinterpret_cast<LPCWSTR>(native.utf16()), 0, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
    if (handle == INVALID_HANDLE_VALUE) error("Cannot inspect legacy Redo item: " + path);
    BY_HANDLE_FILE_INFORMATION info{}; const BOOL ok = GetFileInformationByHandle(handle, &info); CloseHandle(handle);
    if (!ok || info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) error("Linked / unavailable legacy Redo item: " + path);
    const bool directory = info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY;
    int mode = directory ? 0040777 : 0100666;
    if (!directory && QStringList{"exe", "com", "bat", "cmd"}.contains(QFileInfo(path).suffix().toLower())) mode |= 0111;
    if (info.dwFileAttributes & FILE_ATTRIBUTE_READONLY) mode &= ~0222;
    const auto nanos = [](FILETIME time) { return (qint64((quint64(time.dwHighDateTime) << 32) | time.dwLowDateTime) - 116444736000000000ll) * 100; };
    const auto fields = QString("(%1, %2, %3, %4, %5, %6)").arg(info.dwVolumeSerialNumber)
        .arg((quint64(info.nFileIndexHigh) << 32) | info.nFileIndexLow).arg(mode)
        .arg(directory ? 0 : (quint64(info.nFileSizeHigh) << 32) | info.nFileSizeLow)
        .arg(nanos(info.ftLastWriteTime)).arg(nanos(info.ftCreationTime));
    QCryptographicHash hash(QCryptographicHash::Sha256); hash.addData(fields.toLatin1());
    if (directory) {
        auto children = checkedChildren(path); std::sort(children.begin(), children.end(), [](const QFileInfo& a, const QFileInfo& b) { return a.fileName().toUcs4() < b.fileName().toUcs4(); });
        for (const auto& child : children) { hash.addData(child.fileName().toUtf8()); hash.addData(legacyMetadataFingerprint(child.absoluteFilePath(), cancel).toLatin1()); }
    }
    return QString::fromLatin1(hash.result().toHex());
}
}
