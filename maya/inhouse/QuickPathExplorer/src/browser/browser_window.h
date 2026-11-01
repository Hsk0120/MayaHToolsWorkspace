/** @file browser_window.h
 * @brief 現行QPEの上下分割をC++へ移すための共通ウィンドウ。
 */
#pragma once
#include <QWidget>
#include <QJsonArray>
#include <memory>
#include "host_services.h"
class QTabBar;
class QStackedWidget;
class QLineEdit;
class QTreeWidget;
class QSplitter;
class QLabel;
class QTextEdit;
class QToolButton;
class QTimer;
class QAbstractItemView;
class QCloseEvent;
class QResizeEvent;
class QMenu;
namespace qpe {
class BrowserPage;
class Inspector;
class FileJobs;
struct FileRequest;
/** @brief 子ドックをネイティブ化せず、OSダイアログの最上位所有者を返す。
 * @param widget 操作元。nullは受理しない。
 * @return 既存の最上位ウィンドウのハンドル。
 */
WId shellDialogOwner(QWidget* widget);
/** @brief タブと画面内の設定だけを所有する。Maya全体の入力/パレットには介入しない。 */
class BrowserWindow final : public QWidget {
    Q_OBJECT
public:
    /** @brief C++移行用の画面を作る。
     * @param parent Qt所有者。nullptrの場合は単体ウィンドウ。
     */
    explicit BrowserWindow(QWidget* parent = nullptr, HostServices host = {});
    /** @brief 表示タブを指定先へ移動する。
     * @param path 絶対または相対フォルダーパス。
     */
    void navigate(const QString& path);
    /** @brief 独立した履歴/表示状態のタブを追加する。
     * @param path 初期フォルダー。
     */
    void addTab(const QString& path);
    /** @brief 表示タブが要求したパスを返す。
     * @return 要求中を含む現在パス。
     */
    QString currentPath() const;
    /** @brief 表示タブのテスト可能な完了状態を返す。
     * @return 現在一覧を採用済みか。
     */
    bool ready() const;
    /** @brief 現在ビューの選択を返す。 @return 絶対パス列。 */
    QStringList selectedPaths() const;
    /** @brief ホストまたは関連付けで開く。 @param path 対象。 */
    void openPath(const QString& path);
    /** @brief 固定対象のメニューを作る。 @param view ビュー。 @param point ビュー座標。 @param directory 背景対象。 */
    void contextMenu(QAbstractItemView* view, const QPoint& point, const QString& directory);
    /** @brief 明示操作を実行する。 @param action 操作。 @param paths 対象。 @param directory 背景パス。 */
    void perform(const QString& action, const QStringList& paths = {}, const QString& directory = {});
    /** @brief 全タブを再列挙する。 */
    void refresh();
    /** @brief 前回の表示設定とウィンドウ状態を読み戻す。 @param fallback 初期パス。 @param restoreTabs 前回のタブを戻すか。falseは指定パスを単独で開く。 */
    void restoreSession(const QString& fallback = {}, bool restoreTabs = true);
    /** @brief ホスト終了前に状態を保存し、確認画面なしで要求を取消す。待機転送の記録は残す。 */
    void prepareHostShutdown();
    /** @brief 未完了処理の有無。 @return ファイル変更実行中か。 */
    bool busy() const;
protected:
    /** @brief 自分の単体HWNDだけにタイトル統合とリサイズを適用する。
     * @param type OSイベント種別。
     * @param message MSGへの借用ポインター。
     * @param result Windowsへ返す値。
     * @return 処理したか。
     */
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
    bool nativeEvent(const QByteArray& type, void* message, qintptr* result) override;
#else
    bool nativeEvent(const QByteArray& type, void* message, long* result) override;
#endif
    /** @brief 保存と進行中処理の保護。 @param event 終了通知。 */
    void closeEvent(QCloseEvent* event) override;
    /** @brief ドック幅に応じて操作と詳細の配置を更新する。 @param event サイズ通知。 */
    void resizeEvent(QResizeEvent* event) override;
private:
    /** @brief 一時的なWindowsクリップボード占有をGUIを止めずに再試行する。
     * @param action copy/cut/copyPath。 @param paths 固定対象。
     * @param generation このウィンドウの要求世代。 @param sequence OS更新番号。
     * @param attempt 試行回数。新しい外部コピーは上書きしない。
     */
    void writeClipboard(const QString& action, const QStringList& paths, quint64 generation, quint32 sequence, int attempt = 0);
    /** @brief 狭い幅では詳細を全幅にし、利用者が指定した左欄状態は保持する。 */
    void updateResponsiveLayout();
    /** @brief ホスト別の文字・UI倍率・行間を即時反映する。 */
    void appearanceDialog();
    /** @brief 結合の競合を非同期に集計し、個別選択を固定する。 @param request Copy要求。 @return 確定したか。 */
    bool confirmMerge(FileRequest& request);
    /** @brief 世代を分離した検索結果を100件ずつ表示する。 @param request 固定した検索条件。 */
    void streamingSearch(const FileRequest& request);
    /** @brief 保存済みカスタムキーをQPE内・編集欄以外に限定して登録する。 */
    void installCommandKeys();
    /** @brief 名前でコマンドを検索して実行する。 */
    void commandPalette();
    /** @brief キー割当と履歴保持設定を検証して保存する。 */
    void preferencesDialog();
    /** @brief 整理機能のメニューを構築する。 @param menu 所有メニュー。 */
    void organizerMenu(QMenu* menu);
    /** @brief 最近閉じたタブを表示状態ごと復元する。 */
    void reopenTab();
    /** @brief 整理・OS機能の明示操作。 @param action 名称。 @param paths 固定対象。 @param directory 行先。 @return 処理対象か。 */
    bool extendedAction(const QString& action, const QStringList& paths, const QString& directory);
    /** @brief 現在ページを取得する。
     * @return 借用ポインター。
     */
    BrowserPage* page() const;
    /** @brief タブ切替後にパス・情報を更新する。 */
    void updateCurrent();
    /** @brief QPEウィジェット内だけの色/寸法を更新する。 */
    void applyAppearance();
    /** @brief 詳細欄の表示を更新する。
     * @param path 選択されたファイル。
     */
    void showDetails(const QString& path);
    /** @brief 変更したQPE設定だけを保存する。 */
    void saveSession();
    /** @brief Drives/Favorites/Recentを再構築する。 */
    void updatePlaces();
    /** @brief 設定書込みをまとめる。 */
    void scheduleSave();
    /** @brief 検索・集計の条件を固定してワーカーへ渡す。 @param action 種別。 */
    void query(const QString& action);
    /** @brief 非同期結果をモデルへ表示する。 @param result 問い合わせ値。 */
    void showQuery(const QJsonObject& result);
    QTabBar* tabs_;
    QStackedWidget* pages_ = nullptr;
    QLineEdit* address_ = nullptr;
    QTreeWidget* sidebar_ = nullptr;
    QSplitter* horizontal_ = nullptr;
    Inspector* details_ = nullptr;
    QWidget* strip_;
    QToolButton* back_;
    QToolButton* forward_;
    int textSize_ = 12;
    int uiPercent_ = 100;
    QString density_ = "compact";
    QString theme_ = "system";
    HostServices host_;
    FileJobs* jobs_;
    QLabel* status_;
    QTimer* saveTimer_;
    QStringList favorites_;
    QStringList recents_;
    QStringList pathHistory_;
    QJsonArray closedTabs_;
    QJsonArray previousTabSet_;
    QWidget* secondPane_ = nullptr;
    QString selected_;
    bool restoring_ = false;
    bool hidden_ = false;
    bool mayaActionRunning_ = false;
    bool sidebarRequested_ = false;
    bool detailsFullWidth_ = false;
    quint64 clipboardGeneration_ = 0;
    bool clipboardPending_ = false;
    FileJobs* driveJobs_ = nullptr;
};
}
