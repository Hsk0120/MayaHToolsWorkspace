/** @file file_operations.h @brief 非GUIスレッドで実行するファイル更新と復旧記録。 */
#pragma once
#include <QObject>
#include <QJsonObject>
#include <QQueue>
#include <QElapsedTimer>
#include <QStringList>
#include <atomic>
#include <functional>
#include <memory>
namespace qpe {
namespace detail {
/** @brief ファイル操作の親検査境界。 @param path 絶対パス。 @return 対象からドライブ/UNC共有ルートまで。 */
QStringList operationAncestors(const QString& path);
}
/** @brief 実行時に固定される要求。実パス以外の表示文字列を使用しない。 */
struct FileRequest {
    QString action;
    QStringList paths;
    QString destination;
    QString conflict = "rename";
    QJsonObject options;
    QString id;
};
/** @brief 部分成功・エラー・取消しを分離した結果。 */
struct FileResult {
    QStringList completed;
    QStringList errors;
    QStringList warnings;
    QJsonObject extra;
    bool cancelled = false;
};
/** @brief Qt組込型の配送値を内部結果へ戻す。 @param value 配送値。 @return 結果。 */
FileResult fileResultFromJson(const QJsonObject& value);
using CancelFlag = std::shared_ptr<std::atomic_bool>;
using FileProgress = std::function<void(const QString&, qint64)>;
using FilePartial = std::function<void(const QJsonObject&)>;
/** @brief 単一部品名のWindows制約を検査する。 @param name 部品名。 */
void validateFileName(const QString& name);
/** @brief リンクを辿らず内容指紋を求める。
 * @param path ファイル/フォルダー。 @param cancel 中断要求。 @return SHA256。
 */
QString fileFingerprint(const QString& path, const CancelFlag& cancel = {});
/** @brief 新エンジン専用履歴領域を返す。 @return 旧履歴と衝突しないフォルダー。 */
QString operationsDirectory();
/** @brief 同期エンジン。GUIから直接呼ばずJobQueue経由で使う。 */
class FileOperations {
public:
    /** @brief 履歴の保存先を固定する。 @param directory 専用領域。 */
    explicit FileOperations(QString directory);
    /** @brief OSロック内で処理し確定履歴を保持する。
     * @param request 固定要求。 @param cancel 中断。 @param progress 進捗。 @param partial 世代付きの途中結果。
     * @return 完了と失敗を分けた結果。
     */
    FileResult run(const FileRequest& request, const CancelFlag& cancel = {}, const FileProgress& progress = {}, const FilePartial& partial = {});
private:
    QString directory_;
};
/** @brief UI所有の直列キュー。ワーカーは値だけを扱いQt UIへ触れない。 */
class FileJobs final : public QObject {
    Q_OBJECT
public:
    /** @brief キューを作る。 @param parent Qt所有者。 */
    explicit FileJobs(QObject* parent = nullptr);
    /** @brief 実行前要求を破棄し、実行中へ取消しを通知する。 */
    ~FileJobs() override;
    /** @brief 要求を追加する。 @param request 処理対象。 */
    void enqueue(const FileRequest& request);
    /** @brief 実行中を取消し、待ち要求を取り下げる。 */
    void cancel();
    /** @brief 実行中だけ中止し、待機要求は保持する。 */
    void cancelActive();
    /** @brief 待機要求だけ中止する。 */
    void cancelQueued();
    /** @brief ブロック境界で転送を一時停止。 @param value 停止か。 */
    void pauseActive(bool value);
    /** @brief 後続の開始を停止。 @param value 停止か。 */
    void pauseQueue(bool value);
    /** @brief ダイアログ再表示時の停止状態。 @return 停止中か。 */
    bool queuePaused() const { return queuePaused_; }
    /** @brief 実行中転送の停止状態。 @return 停止中か。 */
    bool activePaused() const { return pause_ && pause_->load(); }
    /** @brief 待機位置を交換する。 @param index 現在位置。 @param delta -1/+1。 */
    void moveQueued(int index, int delta);
    /** @brief 実行/待機状態を値で返す。 @return 表示用配列。 */
    QJsonArray records() const;
    /** @brief 利用者の明示操作で未完了転送を再予約。 @param id 記録識別子。 */
    void resume(const QString& id);
    /** @brief 原本/バックアップを残して転送記録だけを除外する。 @param id 選択記録。 */
    void discard(const QString& id);
    /** @brief 作業があるか。 @return 実行中または待機中。 */
    bool busy() const;
    /** @brief mllの解除判定。 @return 生存ワーカー数。 */
    static int liveWorkers();
    /** @brief 自分のスレッドをコード解放より先にjoinする。 @param wait exe終了時だけ実行中も待つ。 @return 安全に解放できたか。 */
    static bool releaseWorkers(bool wait = false);
signals:
    /** @brief 現在要求の途中結果。 @param value 世代と値。 */
    void partial(QJsonObject value);
    /** @brief 開始通知。 @param action 操作名。 */
    void started(QString action);
    /** @brief GUIスレッドへ渡す進捗。 @param path 対象。 @param bytes バイト数。 */
    void progress(QString path, qint64 bytes);
    /** @brief 完了通知。 @param result 成功/エラー/取消し。 */
    void finished(QJsonObject result);
private:
    /** @brief 次の1件だけをワーカーへ送る。 */
    void next();
    QQueue<FileRequest> queue_;
    CancelFlag cancel_;
    CancelFlag pause_;
    FileRequest active_;
    QElapsedTimer elapsed_;
    qint64 transferred_ = 0;
    qint64 totalBytes_ = -1;
    QString progressPath_;
    QString transferPhase_;
    bool queuePaused_ = false;
    bool running_ = false;
};
}
