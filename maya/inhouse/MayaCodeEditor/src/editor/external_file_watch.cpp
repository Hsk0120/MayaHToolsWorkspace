/** @file external_file_watch.cpp
 * @brief 原子的なファイル差し替えにも追従する外部変更監視。
 */
#include "editor/external_file_watch.h"
#include "core/script_file.h"
#include <QFileInfo>
#include <QFileSystemWatcher>
#include <QSet>
#include <QTimer>
namespace mce {
/** @brief 専用スレッドで監視と読み込みを行う。子部品も同じスレッドへ移す。 */
class FileWatchWorker : public QObject {
public:
    using Callback = std::function<void(quint64, const QString&, const QString&, const QString&)>;
    /** @brief 通知を接続する。 @param callback 結果を画面スレッドへ送る関数。 */
    explicit FileWatchWorker(Callback callback) : callback_(std::move(callback)) {}
    /** @brief 対象を置き換える。 @param paths ファイル一覧。 @param generation 配送結果の世代。 */
    void reset(const QStringList& paths, quint64 generation) {
        paths_ = paths; generation_ = generation; pending_.clear(); check();
    }
    /** @brief 通知の取りこぼしをアプリへ戻ったときに補う。 */
    void check() {
        if (!timer_) initialize();
        for (const auto& path : paths_) pending_.insert(path);
        timer_->start();
    }
private:
    /** @brief OSの監視部品は移動前のGUIスレッドではなく、利用するスレッド内で生成する。 */
    void initialize() {
        watcher_ = new QFileSystemWatcher(this);
        timer_ = new QTimer(this);
        timer_->setSingleShot(true);
        timer_->setInterval(250); // 保存時の削除・再作成や連続通知をまとめる。
        connect(watcher_, &QFileSystemWatcher::fileChanged, this, [this](const QString& path) {
            pending_.insert(path); timer_->start();
        });
        connect(watcher_, &QFileSystemWatcher::directoryChanged, this, [this](const QString& directory) {
            for (const auto& path : paths_) {
                if (QFileInfo(path).absolutePath() == directory) pending_.insert(path);
            }
            timer_->start();
        });
        connect(timer_, &QTimer::timeout, this, [this] { readPending(); });
    }
    /** @brief 必要なファイルだけ読み、差し替えで外れた監視を再登録する。 */
    void readPending() {
        const auto pending = pending_; pending_.clear();
        QStringList desiredFiles, desiredDirs;
        for (const auto& path : paths_) {
            const QFileInfo info(path);
            if (info.isFile()) desiredFiles.append(path);
            const QString directory = info.absolutePath();
            if (QFileInfo(directory).isDir() && !desiredDirs.contains(directory)) desiredDirs.append(directory);
        }
        // 既存監視を維持し、削除・再作成されたファイルだけ追加する。
        auto sync = [this](const QStringList& existing, const QStringList& desired) {
            for (const auto& path : existing) if (!desired.contains(path)) watcher_->removePath(path);
            for (const auto& path : desired) if (!existing.contains(path)) watcher_->addPath(path);
        };
        sync(watcher_->files(), desiredFiles);
        sync(watcher_->directories(), desiredDirs);
        for (const auto& path : pending) {
            if (!paths_.contains(path)) continue;
            QString text, error;
            if (!readScriptFile(path, &text, &error) && error.isEmpty()) error = "File is unavailable";
            callback_(generation_, path, text, error);
        }
    }
    Callback callback_; ///< ワーカーから呼ぶ配送関数。
    QFileSystemWatcher* watcher_ = nullptr; ///< このワーカーが所有する。
    QTimer* timer_ = nullptr; ///< このワーカーが所有する通知集約タイマー。
    QStringList paths_; ///< 開いているファイルだけ。
    QSet<QString> pending_; ///< 次回確認するファイル。
    quint64 generation_ = 0; ///< 対象一覧の世代。
};
ExternalFileWatch::ExternalFileWatch(Callback callback) {
    worker_ = new FileWatchWorker([this, callback](quint64 generation, const QString& path,
                                                  const QString& text, const QString& error) {
        QMetaObject::invokeMethod(this, [this, callback, generation, path, text, error] {
            if (generation == generation_) callback(path, text, error);
        }, Qt::QueuedConnection);
    });
    worker_->moveToThread(&thread_);
    connect(&thread_, &QThread::finished, worker_, &QObject::deleteLater);
    thread_.start();
}
ExternalFileWatch::~ExternalFileWatch() {
    ++generation_;
    thread_.quit(); thread_.wait();
}
void ExternalFileWatch::reset(const QStringList& paths) {
    const quint64 generation = ++generation_;
    QMetaObject::invokeMethod(worker_, [worker = worker_, paths, generation] {
        worker->reset(paths, generation);
    }, Qt::QueuedConnection);
}
void ExternalFileWatch::check() {
    QMetaObject::invokeMethod(worker_, [worker = worker_] { worker->check(); }, Qt::QueuedConnection);
}
} // namespace mce
