/** @file external_file_watch.h
 * @brief 開いているファイルだけを別スレッドで監視する。
 */
#pragma once
#include <QObject>
#include <QStringList>
#include <QThread>
#include <functional>
namespace mce {
class FileWatchWorker;
/** @brief ファイルと親フォルダーを監視する。定期的な全文走査はしない。
 * @details 読み込みと監視登録は専用スレッド、通知は画面スレッドで行う。
 * 破棄時に合流し、mllアンロード後の実行を防ぐ。
 */
class ExternalFileWatch : public QObject {
public:
    using Callback = std::function<void(const QString&, const QString&, const QString&)>;
    /** @brief 監視を作る。 @param callback パス・本文・エラー(成功時は空)を受け取る関数。 */
    explicit ExternalFileWatch(Callback callback);
    /** @brief 未配送の通知を破棄し、監視スレッドを終了する。 */
    ~ExternalFileWatch() override;
    /** @brief 対象を置き換えて確認する。古い結果は配送しない。 @param paths 開いているファイルの絶対パス。 */
    void reset(const QStringList& paths);
    /** @brief アプリへ戻ったとき、通知の取りこぼしと監視登録を確認する。 */
    void check();
private:
    QThread thread_; ///< I/O専用。画面やMayaは操作しない。
    FileWatchWorker* worker_ = nullptr; ///< スレッド終了時にQtが破棄する。
    quint64 generation_ = 0; ///< 閉じたタブや保存前の古い結果を捨てる世代。
};
} // namespace mce
