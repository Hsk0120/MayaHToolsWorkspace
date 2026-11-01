/** @file directory_store.cpp
 * @brief Win32の列挙メタデータを一度だけ取得し、世代付きでGUIへ配送する。
 */
#include "directory_store.h"
#include <QDir>
#include <QRunnable>
#include <QThreadPool>
#include <algorithm>
#include <stdexcept>
#include <utility>
#define NOMINMAX
#include <windows.h>

namespace qpe {
namespace {
std::atomic_int workers{0};
QThreadPool* scanPool = nullptr;
/** @brief Qt型レジストリに登録せず、接続クロージャとワーカーだけで共有する値。 */
struct ScanResult { DirectoryEntries entries; QString error; };
/** @brief 部分一覧と完了一覧に同じ安定した名前順を適用する。 @param entries 整列対象。 */
void sortEntries(DirectoryEntries& entries) {
    std::sort(entries.begin(), entries.end(), [](const DirectoryEntry& a, const DirectoryEntry& b) {
        const int order = QString::compare(a.name, b.name, Qt::CaseInsensitive);
        return order ? order < 0 : a.name < b.name;
    });
}
/** @brief OS列挙を行う自己破棄ワーカー。QObjectの接続先が破棄されると配送も解除される。 */
class ScanJob final : public QObject, public QRunnable {
    Q_OBJECT
public:
    /** @brief GUI側で生成し、キャンセルフラグだけを共有する。
     * @param path 調査先。
     * @param generation 発行世代。
     * @param hidden 隠し項目を含めるか。
     * @param cancelled GUIからの失効フラグ。
     * @param result 最終結果の共有先。
     * @param initial 最初の100件。通知後は変更せず、GUIとの競合を防ぐ。
     */
    ScanJob(QString path, quint64 generation, bool hidden, std::shared_ptr<std::atomic_bool> cancelled, std::shared_ptr<ScanResult> result, std::shared_ptr<ScanResult> initial)
        : path_(std::move(path)), generation_(generation), hidden_(hidden), cancelled_(std::move(cancelled)), result_(std::move(result)), initial_(std::move(initial)) { ++workers; }
    /** @brief すべてのコールバック配送を終えてから生存数を減らす。 */
    ~ScanJob() override { --workers; }
    /** @brief 列挙・名前順整列をワーカーで完了する。ウィジェットには触れない。 */
    void run() override {
        if (cancelled_->load()) return;
        QString native = QDir::toNativeSeparators(path_);
        if (!native.startsWith(QStringLiteral("\\\\?\\"))) {
            native = native.startsWith(QStringLiteral("\\\\"))
                ? QStringLiteral("\\\\?\\UNC\\") + native.mid(2) : QStringLiteral("\\\\?\\") + native;
        }
        if (!native.endsWith('\\')) native += '\\';
        native += '*';
        WIN32_FIND_DATAW info{};
        const HANDLE handle = FindFirstFileExW(reinterpret_cast<LPCWSTR>(native.utf16()), FindExInfoBasic,
                                               &info, FindExSearchNameMatch, nullptr, FIND_FIRST_EX_LARGE_FETCH);
        DirectoryEntries entries;
        QString error;
        DWORD failure = ERROR_SUCCESS;
        if (handle == INVALID_HANDLE_VALUE) {
            failure = GetLastError();
            // 実在する空ディレクトリだけを成功にする。消えたパスは失敗として通知する。
            if (failure == ERROR_FILE_NOT_FOUND) {
                const QString directory = native.left(native.size() - 1);
                const DWORD attr = GetFileAttributesW(reinterpret_cast<LPCWSTR>(directory.utf16()));
                if (attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY)) failure = ERROR_SUCCESS;
            }
        } else {
            do {
                if (cancelled_->load()) break;
                const QString name = QString::fromWCharArray(info.cFileName);
                if (name == "." || name == "..") continue;
                if (!hidden_ && ((info.dwFileAttributes & FILE_ATTRIBUTE_HIDDEN) || name.startsWith('.'))) continue;
                const quint64 ticks = (quint64(info.ftLastWriteTime.dwHighDateTime) << 32) | info.ftLastWriteTime.dwLowDateTime;
                const qint64 milliseconds = qint64(ticks / 10000) - 11644473600000LL;
                entries.push_back({name, bool(info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY),
                    qint64((quint64(info.nFileSizeHigh) << 32) | info.nFileSizeLow),
                    QDateTime::fromMSecsSinceEpoch(milliseconds), info.dwFileAttributes});
                // 一度だけ先頭部分を渡し、全件待ちと小刻みなモデル再生成の両方を避ける。
                if (entries.size() == 100) { initial_->entries = entries; sortEntries(initial_->entries); emit initialReady(); }
            } while (FindNextFileW(handle, &info));
            failure = GetLastError();
            FindClose(handle);
            if (failure == ERROR_NO_MORE_FILES) failure = ERROR_SUCCESS;
        }
        if (cancelled_->load()) return;
        if (failure != ERROR_SUCCESS) {
            wchar_t message[1024]{};
            FormatMessageW(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS, nullptr, failure, 0,
                           message, DWORD(std::size(message)), nullptr);
            error = QString::fromWCharArray(message).trimmed();
            if (error.isEmpty()) error = QStringLiteral("Windows error %1").arg(failure);
            entries.clear();
        }
        sortEntries(entries);
        if (!cancelled_->load()) { result_->entries = std::move(entries); result_->error = error; emit completed(); }
    }
signals:
    /** @brief 変更しない初回バッチを通知する。最終結果とは別の共有値を使用する。 */
    void initialReady();
    /** @brief 共有値への書込完了を通知。DLL内の独自型をホストQtへ登録しない。 */
    void completed();
private:
    QString path_;
    quint64 generation_;
    bool hidden_;
    std::shared_ptr<std::atomic_bool> cancelled_;
    std::shared_ptr<ScanResult> result_;
    std::shared_ptr<ScanResult> initial_;
};
}

DirectoryStore::DirectoryStore(QObject* parent) : QObject(parent) {
    connect(&watcher_, &QFileSystemWatcher::directoryChanged, this, [this](const QString& path) { request(path); });
}
DirectoryStore::~DirectoryStore() {
    for (const auto& flag : cancellations_) flag->store(true);
}
QString DirectoryStore::normalized(const QString& path) { return QDir::cleanPath(QDir(path).absolutePath()); }
void DirectoryStore::activate(const QStringList& paths) {
    QSet<QString> next;
    for (const QString& path : paths) if (!path.isEmpty()) next.insert(normalized(path));
    for (const QString& old : active_ - next) {
        if (cancellations_.contains(old)) cancellations_.take(old)->store(true);
        generations_.remove(old);
    }
    const auto previous = active_;
    active_ = next;
    const auto watched = watcher_.directories();
    for (const QString& old : watched) if (!active_.contains(old)) watcher_.removePath(old);
    // 存在確認・watch登録は列挙完了後に行い、初回ナビゲーションをI/O待ちさせない。
    for (const QString& path : active_ - previous) request(path);
    trimCache();
}
quint64 DirectoryStore::request(const QString& input) {
    const QString path = normalized(input);
    if (!active_.contains(path)) return 0;
    if (cancellations_.contains(path)) cancellations_.take(path)->store(true);
    auto flag = std::make_shared<std::atomic_bool>(false);
    cancellations_.insert(path, flag);
    const auto generation = ++serial_;
    generations_[path] = generation;
    auto result = std::make_shared<ScanResult>();
    auto initial = std::make_shared<ScanResult>();
    auto* job = new ScanJob(path, generation, hidden_, flag, result, initial);
    connect(job, &ScanJob::initialReady, this, [this, path, generation, initial] {
        deliver(path, generation, initial->entries, {}, false);
    }, Qt::QueuedConnection);
    connect(job, &ScanJob::completed, this, [this, path, generation, result] {
        deliver(path, generation, result->entries, result->error);
    }, Qt::QueuedConnection);
    if (!scanPool) scanPool = new QThreadPool;
    scanPool->start(job);
    return generation;
}
const DirectorySnapshot* DirectoryStore::snapshot(const QString& path) const {
    const auto found = cache_.constFind(normalized(path));
    return found == cache_.cend() ? nullptr : &found.value();
}
void DirectoryStore::primeCache(const DirectoryStore& source) {
    if (this == &source) return;
    if (!active_.isEmpty() || !generations_.isEmpty()) throw std::logic_error("Only an inactive directory store can be primed");
    if (hidden_ != source.hidden_) return;
    for (const auto& path : source.recency_) {
        const auto found = source.cache_.constFind(path);
        if (found == source.cache_.cend() || !found->complete || !found->error.isEmpty()) continue;
        auto copy = found.value(); copy.generation = ++serial_;
        cache_[path] = std::move(copy); recency_.removeAll(path); recency_.append(path);
    }
    trimCache();
}
bool DirectoryStore::deliver(const QString& input, quint64 generation, const DirectoryEntries& entries, const QString& error, bool complete) {
    const QString path = normalized(input);
    if (!active_.contains(path) || !generation || generations_.value(path) != generation) return false;
    if (!complete && cache_.contains(path)) {
        // 完成済み一覧を100件へ縮めない。初回通知の二重配送も反映しない。
        const auto& previous = cache_[path];
        if (previous.complete || previous.generation == generation) return false;
    }
    if (complete) { generations_.remove(path); cancellations_.remove(path); }
    // 再訪時の再照会は続けるが、内容が同じなら表示世代を保ちモデル再構築を避ける。
    bool same = cache_.contains(path) && cache_[path].complete == complete && cache_[path].error == error && cache_[path].entries.size() == entries.size();
    if (same) {
        const auto& before = cache_[path].entries;
        for (int i = 0; i < entries.size(); ++i) {
            const auto& a = before[i]; const auto& b = entries[i];
            if (a.name != b.name || a.directory != b.directory || a.size != b.size || a.modified != b.modified || a.attributes != b.attributes) { same = false; break; }
        }
    }
    if (!same) cache_[path] = {entries, error, generation, complete};
    recency_.removeAll(path);
    recency_.append(path);
    if (complete && error.isEmpty() && !watcher_.directories().contains(path)) watcher_.addPath(path);
    trimCache();
    emit changed(path);
    return true;
}
void DirectoryStore::setShowHidden(bool enabled) {
    if (hidden_ == enabled) return;
    hidden_ = enabled;
    cache_.clear();
    recency_.clear();
    for (const QString& path : active_) request(path);
}
int DirectoryStore::liveWorkers() { return workers.load(); }
bool DirectoryStore::releaseWorkers(bool wait) {
    if (!wait && (workers.load() || (scanPool && scanPool->activeThreadCount()))) return false;
    if (scanPool) { scanPool->waitForDone(); delete scanPool; scanPool = nullptr; }
    return true;
}
void DirectoryStore::trimCache() {
    for (int i = 0; cache_.size() > 64 && i < recency_.size();) {
        if (active_.contains(recency_[i])) { ++i; continue; }
        cache_.remove(recency_.takeAt(i));
    }
}
}
#include "directory_store.moc"
