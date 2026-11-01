/** @file file_queries.cpp @brief 再帰処理ではリンク/オンライン専用ファイルを辿らない。 */
#include "file_queries.h"
#include "settings_store.h"
#include "media_query.h"
#include "text_decode.h"
#include <QProcess>
#include <QStandardPaths>
#include <QTemporaryDir>
#include <QElapsedTimer>
#include <QSet>
#include <QCryptographicHash>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QRegularExpression>
#include <stdexcept>
#define NOMINMAX
#include <windows.h>
namespace qpe {
namespace {
/** @brief ローカル通常項目か。 @param path パス。 @return 安全な通常項目。 */
bool local(const QString& path) { const DWORD flags = GetFileAttributesW(reinterpret_cast<LPCWSTR>(QDir::toNativeSeparators(path).utf16())); return flags != INVALID_FILE_ATTRIBUTES && !(flags & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_OFFLINE | 0x40000 | 0x400000)); }
/** @brief リンクなしの巡回。 @param path 入口。 @param hidden 隠し項目。 @param cancel 取消し。 @param visit 各項目の処理。 @param errors 読取失敗の蓄積。 */
void walk(const QString& path, bool hidden, const CancelFlag& cancel, const std::function<bool(const QFileInfo&)>& visit, QStringList& errors) {
    if (cancel && cancel->load()) return;
    if (!local(path)) { errors.append("Skipped unavailable, linked, or online-only item: " + path); return; }
    const QFileInfo info(path); if (!visit(info)) return;
    if (!info.isDir()) return;
    const auto pattern = QDir::toNativeSeparators(QDir(path).filePath("*")); WIN32_FIND_DATAW data{};
    const auto handle = FindFirstFileW(reinterpret_cast<LPCWSTR>(pattern.utf16()), &data);
    if (handle == INVALID_HANDLE_VALUE) { const auto error = GetLastError(); if (error != ERROR_FILE_NOT_FOUND) errors.append(QString("Cannot enumerate (%1): %2").arg(error).arg(path)); return; }
    QStringList children; DWORD error = ERROR_SUCCESS;
    do { const auto name = QString::fromWCharArray(data.cFileName); if (name == "." || name == "..") continue;
        if (hidden || (!(data.dwFileAttributes & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)) && !name.startsWith('.'))) children.append(QDir(path).filePath(name));
    } while (!(cancel && cancel->load()) && FindNextFileW(handle, &data));
    error = GetLastError(); FindClose(handle);
    if (!(cancel && cancel->load()) && error != ERROR_NO_MORE_FILES) errors.append(QString("Enumeration interrupted (%1): %2").arg(error).arg(path));
    children.sort(Qt::CaseInsensitive); for (const auto& child : children) walk(child, hidden, cancel, visit, errors);
}
/** @brief 通常ファイルの標準SHA256。 @param path 元。 @param cancel 取消し。 @return 16進文字列。 */
QString sha(const QString& path, const CancelFlag& cancel) {
    QFile file(path); if (!file.open(QIODevice::ReadOnly)) throw std::runtime_error(file.errorString().toStdString());
    QCryptographicHash hash(QCryptographicHash::Sha256);
    while (!file.atEnd()) { if (cancel && cancel->load()) return {}; const auto data = file.read(1024 * 1024); if (data.isEmpty() && file.error() != QFileDevice::NoError) throw std::runtime_error(file.errorString().toStdString()); hash.addData(data); }
    return QString::fromLatin1(hash.result().toHex());
}
}
FileResult runFileQuery(const FileRequest& request, const CancelFlag& cancel, const FileProgress& progress, const FilePartial& partial) {
    FileResult result; QJsonArray rows; qint64 total = 0, files = 0, directories = 0;
    if (request.action == "diagnose") {
        for (const auto& path : request.paths) { const QFileInfo info(path); rows.append(QJsonObject{{"path", path}, {"size", double(info.size())}, {"state", fileAvailability(path)}, {"readable", info.isReadable()}, {"writable", info.isWritable()}, {"directory", info.isDir()}}); }
        const auto settings = readSettings(); auto executable = settings["fileLocksmithExecutable"].toString(settings["fileLocksmith"].toString()); if (executable.isEmpty()) executable = QStandardPaths::findExecutable("FileLocksmithCLI.exe");
        QString detail = "Process identification: configure optional PowerToys File Locksmith CLI in Tools.";
        if (!executable.isEmpty()) {
            QProcess process; process.setProcessChannelMode(QProcess::MergedChannels); process.start(executable, QStringList{"--json"} + request.paths);
            if (!process.waitForStarted(3000)) detail = "File Locksmith could not start: " + process.errorString();
            else {
                QElapsedTimer timer; timer.start(); QByteArray bytes;
                while (process.state() != QProcess::NotRunning) { process.waitForFinished(50); const auto chunk = process.readAll(); if (bytes.size() < 30000) bytes += chunk.left(30000 - bytes.size());
                    if ((cancel && cancel->load()) || timer.elapsed() > 30000) { process.kill(); process.waitForFinished(1000); result.cancelled = cancel && cancel->load(); detail = "File Locksmith query stopped / timed out."; break; }
                }
                if (timer.elapsed() <= 30000 && !result.cancelled) detail = "File Locksmith (read only), exit " + QString::number(process.exitCode()) + ":\n" + QString::fromUtf8(bytes);
            }
        }
        result.extra = {{"query", "diagnose"}, {"rows", rows}, {"detail", detail}}; return result;
    }
    if (request.action == "drives") {
        const DWORD mask = GetLogicalDrives();
        for (int i = 0; i < 26; ++i) if (mask & (1u << i)) {
            if (cancel && cancel->load()) break;
            const auto path = QString(QChar('A' + i)) + ":/"; const auto native = QDir::toNativeSeparators(path);
            wchar_t label[261]{}, format[261]{}; ULARGE_INTEGER free{}, capacity{};
            // 未挿入媒体のOSダイアログはこのワーカースレッドだけで抑制する。
            DWORD oldMode = 0; SetThreadErrorMode(SEM_FAILCRITICALERRORS, &oldMode);
            const bool named = GetVolumeInformationW(reinterpret_cast<LPCWSTR>(native.utf16()), label, 261, nullptr, nullptr, nullptr, format, 261);
            const bool sized = GetDiskFreeSpaceExW(reinterpret_cast<LPCWSTR>(native.utf16()), &free, &capacity, nullptr);
            SetThreadErrorMode(oldMode, nullptr);
            rows.append(QJsonObject{{"path", path}, {"label", named && label[0] ? QString::fromWCharArray(label) : "Local Disk"},
                {"format", QString::fromWCharArray(format)}, {"free", sized ? double(free.QuadPart) : -1.0}, {"total", sized ? double(capacity.QuadPart) : -1.0}});
        }
        result.extra = {{"query", "drives"}, {"rows", rows}}; return result;
    }
    const auto options = request.options;
    const auto pattern = options["query"].toString();
    if (request.action == "search" && options["backend"].toString() == "everything") {
        if (request.paths.size() != 1 || !options["extensions"].toString().isEmpty() || !options["content"].toString().isEmpty() || !options["exclude"].toString().isEmpty() || !options["tags"].toString().isEmpty() || options["minimum"].toDouble() || options["maximum"].toDouble() || options["days"].toInt() || !options["since"].toString().isEmpty() || options["kind"].toString("Files") != "Files") throw std::invalid_argument("Everything uses its own query syntax; clear additional filters or choose Folder scan");
        const auto executable = readSettings()["everythingExecutable"].toString();
        if (!QFileInfo(executable).isFile()) throw std::runtime_error("Configure Everything CLI first");
        QDir().mkpath(operationsDirectory());
        QTemporaryDir temporary(operationsDirectory() + "/search-XXXXXX"); if (!temporary.isValid()) throw std::runtime_error("Cannot create search output");
        const auto output = temporary.filePath("results.txt"); QProcess process;
        process.start(executable, {"-path", request.paths.value(0), "-full-path", "-export-txt", output, "-utf8-bom", "--", pattern});
        QElapsedTimer elapsed; elapsed.start();
        while (process.state() != QProcess::NotRunning) { process.waitForFinished(100); if ((cancel && cancel->load()) || elapsed.elapsed() > 60000) { process.kill(); process.waitForFinished(1000); result.cancelled = true; break; } }
        if (!result.cancelled && process.exitCode()) throw std::runtime_error(QString::fromLocal8Bit(process.readAllStandardError()).toStdString());
        QFile file(output); if (file.open(QIODevice::ReadOnly)) for (const auto& line : decodeText(file.readAll()).split('\n')) { const QFileInfo info(line.trimmed()); if (info.isFile() && rows.size() < 10000) rows.append(QJsonObject{{"path", info.absoluteFilePath()}, {"size", double(info.size())}}); }
        result.extra = {{"query", "search"}, {"rows", rows}, {"token", options["token"]}}; if (partial) partial(result.extra); return result;
    }
    QRegularExpression regex(options["regex"].toBool() ? pattern : QRegularExpression::wildcardToRegularExpression(pattern.contains('*') || pattern.contains('?') ? pattern : '*' + pattern + '*'), QRegularExpression::CaseInsensitiveOption);
    if (!regex.isValid()) throw std::invalid_argument(regex.errorString().toStdString());
    const auto extensions = options["extensions"].toString().toLower().split(QRegularExpression("[ ,;]+"), Qt::SkipEmptyParts);
    const auto content = options["content"].toString();
    QHash<QString, QStringList> duplicates;
    QSet<QString> visited;
    const auto excluded = options["exclude"].toString().split(';', Qt::SkipEmptyParts);
    QList<QRegularExpression> excludeRules, extensionRules;
    for (const auto& value : excluded) excludeRules.append(QRegularExpression(QRegularExpression::wildcardToRegularExpression(QDir::fromNativeSeparators(value.trimmed())), QRegularExpression::CaseInsensitiveOption));
    for (const auto& value : extensions) extensionRules.append(QRegularExpression(QRegularExpression::wildcardToRegularExpression(value), QRegularExpression::CaseInsensitiveOption));
    if (options["minimum"].toDouble() < 0 || options["maximum"].toDouble() < 0 || (options["maximum"].toDouble() > 0 && options["maximum"].toDouble() < options["minimum"].toDouble())) throw std::invalid_argument("Invalid size range");
    auto since = QDateTime::fromString(options["since"].toString(), Qt::ISODate);
    if (!options["since"].toString().isEmpty() && !since.isValid()) throw std::invalid_argument("Invalid modified-since date");
    if (!since.isValid() && options["days"].toInt() > 0) since = QDateTime::currentDateTimeUtc().addDays(-options["days"].toInt());
    const auto kind = options["kind"].toString("Files"); const auto tagMode = options["tagMode"].toString("All");
    if (!QStringList{"Files", "Folders", "Both"}.contains(kind) || !QStringList{"All", "Any"}.contains(tagMode)) throw std::invalid_argument("Invalid search kind / tag mode");
    const auto labels = readSettings()["fileLabels"].toObject(); QSet<QString> wanted;
    for (const auto& tag : options["tags"].toString().split(',')) if (!tag.trimmed().isEmpty()) wanted.insert(tag.trimmed().toCaseFolded());
    QJsonArray pending;
    const auto flush = [&] { if (!pending.isEmpty() && partial) partial({{"query", request.action}, {"token", options["token"]}, {"rows", pending}}); pending = {}; };
    int skipped = 0;
    for (const auto& root : request.paths) {
        if (!QFileInfo::exists(root)) { result.errors.append("Unavailable: " + root); continue; }
        walk(root, options["hidden"].toBool(), cancel, [&](const QFileInfo& info) -> bool {
            const auto key = info.absoluteFilePath().toCaseFolded(); if (visited.contains(key)) return false;
            visited.insert(key);
            if (info.fileName().startsWith(".qpe-", Qt::CaseInsensitive)) return false;
            if (request.action == "search" && rows.size() >= 10000) return false;
            if (info.isDir()) for (const auto& rule : excludeRules) if (rule.match(info.fileName()).hasMatch() || rule.match(QDir(root).relativeFilePath(info.absoluteFilePath())).hasMatch()) return false;
            if (progress && (files + directories) % 128 == 0) progress(info.absoluteFilePath(), total);
            if (info.isDir()) ++directories; else { ++files; total += info.size(); }
            QJsonObject row{{"path", info.absoluteFilePath()}, {"size", double(info.size())}, {"modified", info.lastModified().toString(Qt::ISODate)}};
            if (request.action == "listRecursive") { if (!info.isDir()) rows.append(row); }
            else if (request.action == "search") {
                if (info.absoluteFilePath().compare(QFileInfo(root).absoluteFilePath(), Qt::CaseInsensitive) == 0 && info.isDir()) return true;
                if ((kind == "Files" && info.isDir()) || (kind == "Folders" && !info.isDir())) return true;
                if (rows.size() >= 10000 || !regex.match(info.fileName()).hasMatch()) return true;
                bool matchesExtension = extensions.isEmpty() || extensions.contains(info.suffix().toLower()) || extensions.contains('.' + info.suffix().toLower()); for (const auto& rule : extensionRules) if (rule.match(info.fileName()).hasMatch()) matchesExtension = true;
                if (!matchesExtension) return true;
                if (!info.isDir() && (info.size() < options["minimum"].toDouble() || (options["maximum"].toDouble() > 0 && info.size() > options["maximum"].toDouble()))) return true;
                if (since.isValid() && info.lastModified() < since) return true;
                if (!wanted.isEmpty()) { QSet<QString> actual; const auto label = labels[QDir::toNativeSeparators(info.absoluteFilePath()).toLower()].toObject(); for (const auto& tag : label["tags"].toArray()) actual.insert(tag.toString().toCaseFolded()); auto overlap = wanted; overlap.intersect(actual); if ((tagMode == "All" && overlap != wanted) || (tagMode == "Any" && overlap.isEmpty())) return true; }
                if (!content.isEmpty()) {
                    if (info.isDir()) return true;
                    if (info.size() > 16 * 1024 * 1024 || !QStringList{"txt", "md", "py", "mel", "ma", "json", "csv", "log", "ini", "xml", "yaml", "yml", "rst", "cpp", "h"}.contains(info.suffix().toLower())) { ++skipped; return true; }
                    QFile file(info.absoluteFilePath()); if (!file.open(QIODevice::ReadOnly)) { result.errors.append(info.absoluteFilePath() + ": " + file.errorString()); return true; }
                    const auto data = file.readAll(); if (data.contains('\0') && !data.startsWith("\xff\xfe") && !data.startsWith("\xfe\xff")) { ++skipped; return true; }
                    const auto lines = decodeText(data).split('\n'); QJsonArray matches;
                    for (int i = 0; i < lines.size() && matches.size() < 200; ++i) if (lines[i].contains(content, Qt::CaseInsensitive)) matches.append(QString::number(i + 1) + ": " + lines[i].left(400));
                    if (matches.isEmpty()) return true; row["matches"] = matches; row["state"] = matches[0];
                }
                rows.append(row); pending.append(row); if (pending.size() >= 100) flush();
            } else if (request.action == "hash" && !info.isDir()) { row["sha256"] = sha(info.absoluteFilePath(), cancel); rows.append(row); }
            else if (request.action == "duplicates" && !info.isDir()) duplicates[QString::number(info.size())].append(info.absoluteFilePath());
            else if (request.action == "compare" && !info.isDir()) {
                const auto target = QDir(request.destination).filePath(QDir(root).relativeFilePath(info.absoluteFilePath()));
                if (!QFileInfo::exists(target) || QFileInfo(target).size() != info.size() || (local(target) && sha(target, cancel) != sha(info.absoluteFilePath(), cancel))) { row["destination"] = target; row["state"] = QFileInfo::exists(target) ? "Changed" : "New"; rows.append(row); }
            } else if (request.action == "diagnose") {
                row["state"] = fileAvailability(info.absoluteFilePath()); row["readable"] = info.isReadable(); row["writable"] = info.isWritable(); row["directory"] = info.isDir(); rows.append(row);
            }
            return true;
        }, result.errors);
    }
    flush();
    if (request.action == "search" && rows.size() >= 10000) result.warnings.append("Result limit reached (10000). Narrow the search to see all matches.");
    if (request.action == "duplicates") {
        for (const auto& group : duplicates) if (group.size() > 1) {
            QHash<QString, QStringList> hashes; for (const auto& path : group) { if (cancel && cancel->load()) break; hashes[sha(path, cancel)].append(path); }
            for (auto it = hashes.begin(); it != hashes.end(); ++it) if (it.value().size() > 1 && !it.key().isEmpty()) for (const auto& path : it.value()) rows.append(QJsonObject{{"path", path}, {"sha256", it.key()}, {"size", double(QFileInfo(path).size())}});
        }
    }
    if (skipped) result.warnings.append(QString("%1 files skipped (unsupported type, binary, or above 16 MiB)").arg(skipped));
    result.extra = {{"query", request.action}, {"rows", rows}, {"bytes", double(total)}, {"files", double(files)}, {"directories", double(directories)}};
    result.extra["token"] = options["token"];
    result.cancelled = cancel && cancel->load(); return result;
}
}
