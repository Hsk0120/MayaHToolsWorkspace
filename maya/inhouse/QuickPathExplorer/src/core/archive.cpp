/** @file archive.cpp @brief ZIPのパス逸脱・リンク・上限超過を公開前に拒否する。 */
#include "archive.h"
#include "../../third_party/miniz/miniz.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QSet>
#include <stdexcept>
#define NOMINMAX
#include <windows.h>
namespace qpe {
namespace {
constexpr quint64 maximumBytes = 20ull * 1024 * 1024 * 1024;
constexpr int maximumEntries = 100000;
/** @brief 中断をアーカイブ処理の例外として通知する。 @param flag 共有フラグ。 */
void check(const CancelFlag& flag) { if (flag && flag->load()) throw std::runtime_error("Archive operation cancelled"); }
/** @brief minizのC境界で例外を投げずQtファイルを読む。 @param opaque QFile。 @param offset 位置。 @param buffer 出力。 @param size 長さ。 @return 読んだ量。 */
size_t readFile(void* opaque, mz_uint64 offset, void* buffer, size_t size) {
    auto* file = static_cast<QFile*>(opaque); if (!file->seek(qint64(offset))) return 0;
    const auto count = file->read(static_cast<char*>(buffer), qint64(size)); return count < 0 ? 0 : size_t(count);
}
/** @brief 中断可能な出力。GUIと共有するのはフラグだけ。 */
struct Output { QFile* file; CancelFlag cancel; FileProgress progress; QString path; quint64 limit = maximumBytes; };
/** @brief Cライブラリへ失敗を返す。 @param opaque 出力状態。 @param offset 位置。 @param buffer 内容。 @param size 長さ。 @return 書込量。 */
size_t writeFile(void* opaque, mz_uint64 offset, const void* buffer, size_t size) {
    auto& out = *static_cast<Output*>(opaque);
    if ((out.cancel && out.cancel->load()) || offset > out.limit || size > out.limit - offset || !out.file->seek(qint64(offset))) return 0;
    const auto count = out.file->write(static_cast<const char*>(buffer), qint64(size));
    if (out.progress) out.progress(out.path, qint64(offset + size));
    return count < 0 ? 0 : size_t(count);
}
/** @brief Cリソースを例外時にも解放する。 */
struct Archive {
    mz_zip_archive zip{}; bool writer = false;
    /** @brief reader/writer別に終了する。 */
    ~Archive() { if (writer) mz_zip_writer_end(&zip); else mz_zip_reader_end(&zip); }
};
/** @brief Windowsで別名になる不正名も拒否する。 @param raw ZIPの名前。 @return 安全な相対名。 */
QString safeName(QString raw) {
    raw.replace('\\', '/'); if (raw.endsWith('/')) raw.chop(1);
    if (raw.isEmpty() || raw.startsWith('/') || raw.contains(QChar(0))) throw std::runtime_error("Unsafe ZIP path");
    for (const auto& part : raw.split('/')) validateFileName(part);
    return raw;
}
/** @brief ZIP全体を事前検査する。 @param archive 初期化済みreader。 @param cancel 中断。 @return 項目。 */
QJsonArray entries(Archive& archive, const CancelFlag& cancel) {
    const auto count = mz_zip_reader_get_num_files(&archive.zip);
    if (count > maximumEntries) throw std::runtime_error("ZIP exceeds 100,000 entries");
    QJsonArray rows; QSet<QString> names, files; quint64 total = 0;
    for (mz_uint i = 0; i < count; ++i) {
        check(cancel); mz_zip_archive_file_stat stat{};
        if (!mz_zip_reader_file_stat(&archive.zip, i, &stat) || stat.m_is_encrypted || !stat.m_is_supported
            || ((stat.m_external_attr >> 16) & 0170000) == 0120000 || (stat.m_external_attr & FILE_ATTRIBUTE_REPARSE_POINT))
            throw std::runtime_error("Unsupported, encrypted or linked ZIP entry");
        QByteArray raw(int(mz_zip_reader_get_filename(&archive.zip, i, nullptr, 0)), '\0');
        if (raw.size() < 2 || !mz_zip_reader_get_filename(&archive.zip, i, raw.data(), mz_uint(raw.size()))) throw std::runtime_error("Invalid ZIP name");
        raw.chop(1); const auto name = safeName(QString::fromUtf8(raw)); const auto key = name.toCaseFolded();
        if (names.contains(key)) throw std::runtime_error("Duplicate ZIP path");
        names.insert(key); if (!stat.m_is_directory) files.insert(key);
        if (stat.m_uncomp_size > maximumBytes - total) throw std::runtime_error("ZIP exceeds 20 GiB expanded size");
        total += stat.m_uncomp_size;
        rows.append(QJsonObject{{"path", name}, {"size", double(stat.m_uncomp_size)}, {"index", int(i)}, {"directory", bool(stat.m_is_directory)}});
    }
    for (const auto& name : names) { QString parent = name; while (parent.contains('/')) { parent = parent.left(parent.lastIndexOf('/')); if (files.contains(parent)) throw std::runtime_error("ZIP file conflicts with a parent directory"); } }
    return rows;
}
/** @brief QFileでUnicodeパスを開く。 @param file 入力。 @param archive reader。 */
void openReader(QFile& file, Archive& archive) {
    if (!file.open(QIODevice::ReadOnly)) throw std::runtime_error(file.errorString().toStdString());
    archive.zip.m_pRead = readFile; archive.zip.m_pIO_opaque = &file;
    if (!mz_zip_reader_init(&archive.zip, mz_uint64(file.size()), 0)) throw std::runtime_error("Invalid ZIP archive");
}
/** @brief シンボリックリンク/オンラインファイルを辿らず追加する。 @param archive writer。 @param path 元。 @param name 相対名。 @param cancel 中断。 @param count 項目数。 */
void add(Archive& archive, const QString& path, const QString& name, const CancelFlag& cancel, int& count) {
    check(cancel); if (++count > maximumEntries) throw std::runtime_error("Too many archive entries");
    const auto flags = GetFileAttributesW(reinterpret_cast<LPCWSTR>(QDir::toNativeSeparators(path).utf16()));
    if (flags == INVALID_FILE_ATTRIBUTES || flags & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_OFFLINE | 0x40000 | 0x400000)) throw std::runtime_error("ZIP source unavailable or not a local ordinary file");
    safeName(name); const QFileInfo info(path);
    if (info.isDir()) {
        const auto encoded = (name + '/').toUtf8();
        if (!mz_zip_writer_add_mem(&archive.zip, encoded.constData(), nullptr, 0, MZ_DEFAULT_COMPRESSION)) throw std::runtime_error("Cannot add ZIP folder");
        for (const auto& child : QDir(path).entryInfoList(QDir::AllEntries | QDir::NoDotAndDotDot | QDir::Hidden | QDir::System, QDir::Name))
            add(archive, child.absoluteFilePath(), name + '/' + child.fileName(), cancel, count);
    } else {
        QFile input(path); if (!input.open(QIODevice::ReadOnly)) throw std::runtime_error(input.errorString().toStdString());
        const auto encoded = name.toUtf8();
        if (!mz_zip_writer_add_read_buf_callback(&archive.zip, encoded.constData(), readFile, &input, mz_uint64(input.size()), nullptr, nullptr, 0, MZ_DEFAULT_COMPRESSION, nullptr, 0, nullptr, 0)) throw std::runtime_error("Cannot add ZIP file");
    }
}
}
QJsonArray inspectArchive(const QString& path, const CancelFlag& cancel) { QFile file(path); Archive archive; openReader(file, archive); return entries(archive, cancel); }
void writeArchive(const FileRequest& request, const QString& output, const CancelFlag& cancel, const FileProgress& progress) {
    if (QFileInfo::exists(output)) throw std::runtime_error("Archive output already exists");
    if (request.action == "createZip") {
        QFile file(output); if (!file.open(QIODevice::WriteOnly | QIODevice::NewOnly)) throw std::runtime_error(file.errorString().toStdString());
        Output context{&file, cancel, progress, output}; Archive archive; archive.writer = true;
        archive.zip.m_pWrite = writeFile; archive.zip.m_pIO_opaque = &context;
        if (!mz_zip_writer_init_v2(&archive.zip, 0, MZ_ZIP_FLAG_WRITE_ZIP64)) throw std::runtime_error("Cannot initialize ZIP");
        QSet<QString> names; int count = 0;
        for (const auto& path : request.paths) { const auto name = QFileInfo(path).fileName(); if (names.contains(name.toCaseFolded())) throw std::runtime_error("Duplicate ZIP root name"); names.insert(name.toCaseFolded()); add(archive, path, name, cancel, count); }
        if (!mz_zip_writer_finalize_archive(&archive.zip) || !file.flush()) throw std::runtime_error("Cannot finish ZIP");
    } else {
        if (request.paths.size() != 1) throw std::invalid_argument("Choose one ZIP");
        QFile input(request.paths[0]); Archive archive; openReader(input, archive); const auto rows = entries(archive, cancel);
        const auto selection = request.options["entries"].toArray();
        if (!QDir().mkdir(output)) throw std::runtime_error("Cannot create extraction folder");
        for (const auto& value : rows) {
            check(cancel); const auto row = value.toObject(); const auto name = row["path"].toString();
            bool selected = selection.isEmpty(); for (const auto& prefix : selection) if (name == prefix.toString() || name.startsWith(prefix.toString() + '/')) selected = true;
            if (!selected) continue;
            const auto target = QDir(output).filePath(name);
            if (!QDir().mkpath(row["directory"].toBool() ? target : QFileInfo(target).absolutePath())) throw std::runtime_error("Cannot create ZIP subfolder");
            if (row["directory"].toBool()) continue;
            QFile file(target); if (!file.open(QIODevice::WriteOnly | QIODevice::NewOnly)) throw std::runtime_error(file.errorString().toStdString());
            Output context{&file, cancel, progress, target, quint64(row["size"].toDouble())};
            if (!mz_zip_reader_extract_to_callback(&archive.zip, mz_uint(row["index"].toInt()), writeFile, &context, 0) || !file.flush()) throw std::runtime_error("ZIP extraction failed (CRC, I/O or cancellation)");
        }
    }
}
}
