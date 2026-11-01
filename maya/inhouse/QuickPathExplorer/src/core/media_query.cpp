/** @file media_query.cpp @brief 画像読込・外部デコーダー・シーン宣言を制限付きで扱う。 */
#include "media_query.h"
#include "media_decoder.h"
#include "settings_store.h"
#include "text_decode.h"
#include <QBuffer>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QImageReader>
#include <QJsonArray>
#include <QProcess>
#include <QRegularExpression>
#include <QStandardPaths>
#include <QElapsedTimer>
#define NOMINMAX
#include <windows.h>
namespace qpe {
Availability availabilityFromFlags(quint32 flags, quint32 cloud) {
    if (flags == INVALID_FILE_ATTRIBUTES) return {"Unavailable", true};
    const bool placeholder = cloud != 0xffffffff && (cloud & 1);
    const QString sync = placeholder ? (cloud & 8 ? " / in sync" : " / not in sync (provider details required)") : QString();
    if (placeholder && (cloud & 0x30)) return {"Cloud content not ready" + sync, true};
    if (flags & (FILE_ATTRIBUTE_OFFLINE | 0x40000 | 0x400000)) return {"Download required" + sync, true};
    if (flags & 0x80000) return {"Always available" + sync, false};
    if (flags & 0x100000) return {"Locally available (unpinned)" + sync, false};
    return {sync.isEmpty() ? "Local / provider status unknown" : "Locally available" + sync, false};
}
Availability inspectAvailability(const QString& path) {
    const auto native = QDir::toNativeSeparators(path);
    const auto flags = GetFileAttributesW(reinterpret_cast<LPCWSTR>(native.utf16())); quint32 cloud = 0;
    if (flags != INVALID_FILE_ATTRIBUTES && (flags & FILE_ATTRIBUTE_REPARSE_POINT)) {
        WIN32_FIND_DATAW data{}; const auto find = FindFirstFileW(reinterpret_cast<LPCWSTR>(native.utf16()), &data);
        if (find != INVALID_HANDLE_VALUE) {
            FindClose(find);
            // OSのDLLだけを使う。Maya/QtのDLL検索経路やグローバル設定を変更しない。
            const auto module = LoadLibraryExW(L"CldApi.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
            if (module) { using Query = DWORD(WINAPI*)(DWORD, DWORD); const auto query = reinterpret_cast<Query>(GetProcAddress(module, "CfGetPlaceholderStateFromAttributeTag")); if (query) cloud = query(flags, data.dwReserved0); FreeLibrary(module); }
        }
    }
    return availabilityFromFlags(flags, cloud);
}
QString fileAvailability(const QString& path) { return inspectAvailability(path).text; }
FileResult queryMedia(const FileRequest& request, const CancelFlag& cancel) {
    FileResult result;
    if (request.paths.size() != 1) return result;
    const auto path = request.paths[0]; const QFileInfo info(path); const auto availability = inspectAvailability(path);
    QJsonObject data{{"query", "media"}, {"path", path}, {"token", request.options["token"]}, {"size", double(info.size())}, {"modified", info.lastModified().toString(Qt::ISODate)}, {"availability", availability.text}};
    result.extra = data;
    if (availability.avoidRead || !info.isFile() || (cancel && cancel->load())) return result;
    if (request.options["metadataOnly"].toBool()) {
        QImageReader header(path); const auto dimensions = header.size();
        if (dimensions.isValid()) { data["width"] = dimensions.width(); data["height"] = dimensions.height(); }
        result.extra = data; return result;
    }
    const auto extension = info.suffix().toLower();
    if (QStringList{"txt", "md", "py", "mel", "ma", "json", "csv", "log", "ini", "xml", "yaml", "yml", "rst"}.contains(extension)) {
        QFile text(path); if (text.open(QIODevice::ReadOnly)) {
            const auto bytes = text.read(16 * 1024);
            if (!bytes.contains('\0') || bytes.startsWith("\xff\xfe") || bytes.startsWith("\xfe\xff")) data["text"] = decodeText(bytes);
            if (text.size() > bytes.size()) data["textTruncated"] = true;
        }
    }
    const auto sidecar = path + ".qpe.png";
    QImage image;
    QImageReader reader(QFileInfo::exists(sidecar) && !inspectAvailability(sidecar).avoidRead ? sidecar : path); reader.setAutoTransform(true);
    const auto original = reader.size();
    if (original.isValid() && qint64(original.width()) * original.height() <= 100000000 && info.size() <= 512ll * 1024 * 1024) {
        data["width"] = original.width(); data["height"] = original.height();
        reader.setScaledSize(original.scaled(320, 240, Qt::KeepAspectRatio)); image = reader.read();
    }
    if (image.isNull() && QStringList{"mp4", "mov", "avi", "mkv", "webm", "exr", "hdr"}.contains(extension)) {
        const auto executable = mediaDecoder(cancel);
        if (!executable.isEmpty()) {
            QProcess process; process.setProcessChannelMode(QProcess::SeparateChannels);
            process.start(executable, {"-hide_banner", "-loglevel", "error", "-nostdin", "-threads", "2", "-filter_threads", "1", "-i", path, "-frames:v", "1", "-vf", "scale=320:240:force_original_aspect_ratio=decrease", "-f", "image2pipe", "-vcodec", "png", "pipe:1"});
            QElapsedTimer time; time.start(); QByteArray bytes;
            while (process.state() != QProcess::NotRunning) {
                process.waitForFinished(50); bytes += process.readAllStandardOutput(); process.readAllStandardError();
                if ((cancel && cancel->load()) || time.elapsed() > 10000 || bytes.size() > 8 * 1024 * 1024) { process.kill(); process.waitForFinished(1000); break; }
            }
            bytes += process.readAllStandardOutput(); image.loadFromData(bytes, "PNG");
        } else data["note"] = "Configure FFmpeg for video / EXR thumbnails";
    }
    if (!image.isNull()) { QByteArray bytes; QBuffer buffer(&bytes); buffer.open(QIODevice::WriteOnly); image.save(&buffer, "PNG"); data["png"] = QString::fromLatin1(bytes.toBase64()); }
    if (extension == "ma") {
        QFile file(path);
        if (file.open(QIODevice::ReadOnly)) {
            const auto text = QString::fromUtf8(file.read(8 * 1024 * 1024));
            auto version = QRegularExpression("requires maya \\\"([^\\\"]+)\\\"").match(text); if (version.hasMatch()) data["mayaVersion"] = version.captured(1);
            QJsonArray dependencies; auto matches = QRegularExpression("(?:file[^;]*-r[^;]*|setAttr[^;]*-type \\\"string\\\"[^;]*)\\\"([^\\\"]+\\.(?:ma|mb|abc|fbx|png|jpg|tif|exr))\\\"", QRegularExpression::CaseInsensitiveOption).globalMatch(text);
            while (matches.hasNext() && dependencies.size() < 10000) { const auto match = matches.next(); const auto dependency = match.captured(1); dependencies.append(QJsonObject{{"path", dependency}, {"state", QFileInfo(dependency).isRelative() ? "Relative: project resolution required" : dependency.contains('<') || dependency.contains('*') ? "Pattern" : QFileInfo::exists(dependency) ? "Available" : "Missing"}}); }
            data["dependencies"] = dependencies;
        }
    }
    if (QFileInfo::exists(path + ".qpe.json") && QFileInfo(path + ".qpe.json").size() < 8 * 1024 * 1024 && !inspectAvailability(path + ".qpe.json").avoidRead) {
        try { data["scene"] = loadJson(path + ".qpe.json"); } catch (const std::exception& e) { data["note"] = QString::fromUtf8(e.what()); }
    }
    if (cancel && cancel->load()) { result.cancelled = true; return result; }
    result.extra = data; return result;
}
}
