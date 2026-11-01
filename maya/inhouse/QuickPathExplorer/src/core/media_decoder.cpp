/** @file media_decoder.cpp @brief 再リンク可能なLGPLメディアヘルパーの遅延準備。 */
#include "media_decoder.h"
#include "settings_store.h"
#include <QCryptographicHash>
#include <QDir>
#include <QDateTime>
#include <QFile>
#include <QFileInfo>
#include <QLockFile>
#include <QMutex>
#include <QMutexLocker>
#include <QSaveFile>
#include <QStandardPaths>
#include <QElapsedTimer>
#include <stdexcept>
#define NOMINMAX
#include <windows.h>
namespace qpe {
QString mediaDecoder(const CancelFlag& cancel) {
    auto executable = qEnvironmentVariable("QPE_FFMPEG");
    if (executable.isEmpty()) executable = readSettings()["ffmpegExecutable"].toString();
    if (!executable.isEmpty()) return executable;
    // 全ワーカーが解放された後にDLLを解除する。関数内Qt値をホスト側の登録へ残さない。
    static QMutex mutex; static QString cached; static qint64 cachedSize = -1, cachedModified = -1;
    QMutexLocker guard(&mutex);
    if (cancel && cancel->load()) return {};
    if (!cached.isEmpty()) { const QFileInfo info(cached); if (info.size() == cachedSize && info.lastModified().toMSecsSinceEpoch() == cachedModified) return cached; }
    HMODULE module = nullptr;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, reinterpret_cast<LPCWSTR>(&mediaDecoder), &module);
    const auto resource = module ? FindResourceW(module, MAKEINTRESOURCEW(301), MAKEINTRESOURCEW(10)) : nullptr;
    const auto loaded = resource ? LoadResource(module, resource) : nullptr;
    if (!loaded) return QStandardPaths::findExecutable("ffmpeg");
    const auto data = static_cast<const char*>(LockResource(loaded)); const auto size = SizeofResource(module, resource);
    if (!data || !size || size > 128 * 1024 * 1024) throw std::runtime_error("Invalid embedded media helper");
    const auto bytes = QByteArray::fromRawData(data, int(size)); const auto hash = QCryptographicHash::hash(bytes, QCryptographicHash::Sha256);
    const auto cache = qEnvironmentVariable("QPE_MEDIA_CACHE_ROOT", QStandardPaths::writableLocation(QStandardPaths::GenericCacheLocation) + "/QuickPathExplorer/media");
    if (!QFileInfo(cache).isAbsolute()) throw std::runtime_error("Media cache must be an absolute path");
    const auto directory = cache + '/' + QString::fromLatin1(hash.toHex());
    if (!QDir().mkpath(directory)) throw std::runtime_error("Cannot create QPE media cache");
    QLockFile lease(directory + "/extract.lock"); lease.setStaleLockTime(30000); QElapsedTimer elapsed; elapsed.start();
    while (!lease.tryLock(100)) { if (cancel && cancel->load()) return {}; if (elapsed.elapsed() > 10000) throw std::runtime_error("Media cache is in use; retry later"); }
    const auto target = directory + "/qpe-media.exe"; QFile existing(target); bool valid = false;
    if (existing.open(QIODevice::ReadOnly)) { QCryptographicHash check(QCryptographicHash::Sha256); if (check.addData(&existing)) valid = check.result() == hash; existing.close(); }
    if (!valid) {
        QSaveFile output(target); output.setDirectWriteFallback(false);
        if (!output.open(QIODevice::WriteOnly) || output.write(bytes) != bytes.size() || !output.commit()) throw std::runtime_error("Cannot prepare QPE media helper");
    }
    const QFileInfo info(target); cached = target; cachedSize = info.size(); cachedModified = info.lastModified().toMSecsSinceEpoch(); return cached;
}
}
