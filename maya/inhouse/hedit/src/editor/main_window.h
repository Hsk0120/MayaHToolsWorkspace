/** @file main_window.h
 * @brief 編集画面の全体。各部品を組み立て、メニュー・タブ・保存と復元をつなぐ。
 * @details 実装は2つのファイルに分けている:
 * - main_window.cpp       : 組み立て・タブ・ファイル・自動保存・実行・補完・設定の反映
 * - main_window_menus.cpp : メニューとツールバーの組み立て、Preferencesのリセット
 */
#pragma once
#include "editor/editor.h"
#include "editor/editor_preferences.h"
#include "editor/session_store.h"
#include "editor/spelling.h"
#include <QElapsedTimer>
#include <QHash>
#include <QMainWindow>
#include <QTimer>

class QAction;
class QComboBox;
class QDockWidget;
class QLabel;
class QMenu;
class QSplitter;

namespace hedit {

class CodeEditor;
class EditorTabs;
class Explorer;
class FindBar;
class OutputPanel;
class ProblemsPanel;

/** @brief 編集画面(objectNameは``hedit``)。
 * @details 画面の配置(上から):
 * @code
 * ┌ メニュー / ツールバー ─────────────────────────┐
 * │ Explorer │ OutputPanel(出力欄)                  │
 * │ (左ドック)│──────── QSplitter ────────────────── │
 * │          │ EditorTabs(CodeEditorが1タブに1つ)+FindBar│
 * │          │ ProblemsPanel(構文チェック。通常は非表示)│
 * └ ステータスバー(行・列 / 補完の状態 / 言語)─────┘
 * @endcode
 * Mayaが必要な処理は全てEditorServicesの関数を呼ぶ。このクラスはMayaのAPIを直接呼ばない。
 * Qtの部品は全て、このウィンドウを祖先とする親子関係で所有し、ウィンドウと一緒に破棄される。
 */
class MainWindow : public QMainWindow {
public:
    /** @brief 部品・メニュー・タイマーを組み立て、保存済みのタブを復元する。
     * @param parent Qtの親。nullptrなら独立したウィンドウ。
     * @param services Maya側の処理の一式。
     */
    MainWindow(QWidget* parent, const EditorServices& services);

    /** @brief 破棄の前に、タブの内容を復元ファイルへ保存する。 */
    ~MainWindow() override;

    /** @brief Mayaの処理の途中でも、出力欄をすぐ描き直す(editor.hのrefreshEditorOutputから呼ぶ)。 */
    void refreshOutputNow();

protected:
    /** @brief 閉じるとき、タブの自動保存を試す。保存できなければ未保存のタブごとに確認する。
     * @param event accept()で閉じる、ignore()で閉じるのをやめる。
     */
    void closeEvent(QCloseEvent* event) override;

private:
    // ---- 組み立て(コンストラクターから1回だけ呼ぶ) ----

    /** @brief 出力欄・タブ欄・検索バー・構文チェック一覧・Explorerを配置する。 */
    void buildLayout();
    /** @brief ステータスバーの補完の状態と言語の選択欄を作る。 */
    void buildStatusBar();
    /** @brief タイマー(補完・構文チェック・スペル・自動保存)を用意する。 */
    void setUpTimers();

    // ---- メニュー(main_window_menus.cpp) ----

    /** @brief メニューとツールバーを作る。 */
    void buildMenusAndToolbar();
    /** @brief Edit > Preferences のチェック項目を作る。 @param menu 追加先のメニュー。 */
    void buildPreferencesMenu(QMenu* menu);
    /** @brief ショートカットを、このウィンドウにフォーカスがあるときだけ効くようにする。 */
    void limitShortcutsToThisWindow();
    /** @brief 確認のうえ、全ての設定と文字サイズを初期値に戻す(Edit > Preferences > Reset to defaults)。
     * @details タブの本文・ファイル・Explorerは変更しない。
     */
    void resetPreferences();

    // ---- タブ ----

    /** @brief 選択中のタブのコード欄。 @return タブが無ければnullptr。 */
    CodeEditor* currentEditor() const;
    /** @brief 新しいタブを作って選択する。
     * @param language ``python``または``mel``。
     * @return 新しいコード欄。所有者はタブ欄(呼出側でdeleteしない)。
     */
    CodeEditor* newTab(const QString& language = "python");
    /** @brief 未保存なら確認してから、タブを閉じる。最後のタブを閉じたら空のタブを作る。
     * @param index 0始まりのタブ番号。
     */
    void closeTab(int index);
    /** @brief 未保存のタブを閉じてよいか、利用者に確認する。
     * @param editor 対象のタブ。
     * @return 保存したか破棄を選んだらtrue。キャンセルならfalse。
     */
    bool confirmClose(CodeEditor* editor);
    /** @brief タブの言語を変え、補完と構文チェックの対象を切り替える。
     * @param editor 対象のタブ。
     * @param language ``python``または``mel``。
     */
    void setLanguage(CodeEditor* editor, const QString& language);
    /** @brief 本文が変わったときの処理(補完の予約・構文チェック・スペル・見出し)。
     * @param editor 変更されたタブ。
     */
    void onTextChanged(CodeEditor* editor);

    // ---- ファイル ----

    /** @brief UTF-8のスクリプトを開く。開いているファイルなら、そのタブを選ぶ。
     * @param path ファイルのパス。空なら何もしない。
     */
    void openFile(const QString& path);
    /** @brief ファイルへ保存する。
     * @param editor 保存するタブ。
     * @param saveAs trueなら毎回保存先を選ぶ。
     * @return 保存できたらtrue。キャンセルや書き込み失敗ならfalse。
     */
    bool saveFile(CodeEditor* editor, bool saveAs = false);
    /** @brief 保存先を持つタブを、ExplorerのOPEN EDITORSへ反映する。 */
    void updateExplorer();

    // ---- 未保存タブの自動復元 ----

    /** @brief tabs.jsonを読み、タブを復元する。読めなければ出力欄で知らせる。 */
    void restoreSession();
    /** @brief 全タブの内容をtabs.jsonへ保存する。前回の保存から何も変わっていなければ書かない。
     * @return 保存できた(または変更が無かった)らtrue。
     */
    bool saveSession();
    /** @brief 自動保存が必要な変化(本文・カーソル・タブの並びなど)があったことを記録する。 */
    void markSessionDirty() { sessionDirty_ = true; }

    // ---- 実行と表示 ----

    /** @brief コードをMayaで実行する。
     * @param all trueならタブ全体。falseなら選択範囲(選択が無ければ全体)。
     */
    void runCode(bool all);
    /** @brief 入力欄を空にする(Ctrl+Zで戻せる)。 */
    void clearInput();
    /** @brief 出力欄と入力欄の表示を切り替える。 @param output 出力欄を表示するか。 @param input 入力欄を表示するか。 */
    void showPanels(bool output, bool input);
    /** @brief ステータスバーに行番号の入力欄を出し、Enterでその行へ移動する(Ctrl+G)。 */
    void showGoToLine();
    /** @brief コード欄と出力欄の文字サイズを変えて保存する。 @param pixels 100%時のピクセル数。 */
    void setZoom(int pixels);
    /** @brief 保存済みの文字サイズを、コード欄と出力欄の表示に反映する。 */
    void applyZoom();
    /** @brief ステータスバーに文字を出す。 @param text 文字。 @param timeout 表示するミリ秒。0なら消えない。 */
    void showStatus(const QString& text, int timeout = 0);

    // ---- 補完・構文チェック・スペル ----

    /** @brief Mayaの補完環境を取り直す。 */
    void refreshCompletion();
    /** @brief 現在の位置の補完候補を求めて表示する。
     * @param force Ctrl+Spaceからならtrue(自動補完の設定を無視する)。
     */
    void requestCompletion(bool force);
    /** @brief 入力が止まってから構文チェックするよう予約する。 */
    void scheduleAnalysis();
    /** @brief 選択中のPythonタブを構文チェックする(実行はしない)。 */
    void runAnalysis();
    /** @brief 入力が止まってからスペルチェックするよう予約する。オフなら全タブの波線を消す。 */
    void scheduleSpelling();

    // ---- 設定 ----

    /** @brief 設定をコード欄へ反映する。 @param editor 対象のタブ。 */
    void applyPreferences(CodeEditor* editor);
    /** @brief Preferencesの項目が切り替えられたときの処理。
     * @param key 設定の保存名。
     * @param enabled 新しい値。
     */
    void onOptionToggled(const QString& key, bool enabled);

    // ---- データ ----

    EditorServices services_;        ///< Maya側の処理の一式。
    EditorPreferences preferences_;  ///< 設定(preferences.ini)。
    SessionStore session_;           ///< 未保存タブの復元ファイル(tabs.json)。
    Spelling spelling_;              ///< Windowsの英語辞書。
    bool sessionDirty_ = true;       ///< 前回の自動保存の後に変化があったか。最初は保存が必要として始める。

    // 部品。全てこのウィンドウの子孫なので、deleteしなくてよい。
    QSplitter* splitter_ = nullptr;          ///< 出力欄と入力欄の境界。
    EditorTabs* tabs_ = nullptr;             ///< タブ欄。
    OutputPanel* output_ = nullptr;          ///< 出力欄。
    FindBar* findBar_ = nullptr;             ///< 検索・置換バー。
    ProblemsPanel* problems_ = nullptr;      ///< 構文チェックの一覧。
    Explorer* explorer_ = nullptr;           ///< ファイルツリー。
    QDockWidget* explorerDock_ = nullptr;    ///< Explorerを入れる左のドック。
    QComboBox* languageSelector_ = nullptr;  ///< ステータスバーの言語(Python/MEL)。
    QLabel* completionStatus_ = nullptr;     ///< ステータスバーの補完の状態。
    QHash<QString, QAction*> optionActions_; ///< Preferencesのチェック項目(保存名 → メニュー項目)。

    // タイマー。いずれも「最後の入力から一定時間後に1回だけ」動かすために使う。
    QTimer completionTimer_;  ///< 入力が止まって250ms後に自動補完する。
    QTimer analysisTimer_;    ///< 入力が止まって800ms後に構文チェックする。
    QTimer spellingTimer_;    ///< 入力が止まって450ms後にスペルチェックする。
    QTimer sessionTimer_;     ///< 1秒ごとに、入力が止まっていて変化があればタブを自動保存する。
    QElapsedTimer lastEdit_;  ///< 最後に本文が変わってからの時間。
};

}  // namespace hedit
