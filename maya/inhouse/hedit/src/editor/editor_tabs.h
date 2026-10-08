/** @file editor_tabs.h
 * @brief コード欄を入れるタブ欄。タブが多いときはマウスホイールと矢印ボタンで移動できる。
 */
#pragma once
#include <QList>
#include <QStringList>
#include <QTabBar>
#include <QTabWidget>

namespace hedit {

class CodeEditor;

/** @brief スクロールボタン付きで、ホイール1段ごとに隣のタブを選ぶタブバー。 */
class ScrollTabBar : public QTabBar {
public:
    /** @brief スクロールボタン付きのタブバーを作る。
     * @param parent タブバーを所有する親。
     */
    explicit ScrollTabBar(QWidget* parent = nullptr);

protected:
    /** @brief ホイール1段で隣のタブを選び、そのタブを表示範囲へ入れる。
     * @param event ホイールの回転量。Qtが所有する。
     */
    void wheelEvent(QWheelEvent* event) override;
};

/** @brief ScrollTabBarを使うタブ欄。1タブに1つのコード欄(CodeEditor)を入れる。 */
class EditorTabs : public QTabWidget {
public:
    /** @brief タブ欄を作る。閉じるボタンとドラッグでの並べ替えを有効にする。
     * @param parent タブ欄を所有する親。
     */
    explicit EditorTabs(QWidget* parent = nullptr);

    /** @brief 選択中のタブのコード欄。 @return タブが無ければnullptr。 */
    CodeEditor* currentEditor() const;

    /** @brief 指定番号のタブのコード欄。 @param index 0始まりの番号。 @return 範囲外ならnullptr。 */
    CodeEditor* editorAt(int index) const;

    /** @brief 全てのタブのコード欄。 @return タブの順のコード欄。 */
    QList<CodeEditor*> editors() const;

    /** @brief 保存先を持つタブのパス。 @return タブの順のパス(未保存の新規タブは含まない)。 */
    QStringList filePaths() const;

    /** @brief ファイルを開いているタブを探す。 @param absolutePath 絶対パス。 @return タブの番号。無ければ-1。 */
    int indexOfFile(const QString& absolutePath) const;

    /** @brief タブの見出しを、ファイル名と未保存の印(●)で更新する。見出しが変わらなければ何もしない。
     * @param editor 対象のタブ。
     */
    void updateTitle(CodeEditor* editor);

    /** @brief 次(前)のタブへ移る。端では反対側へ折り返す。 @param direction 次は1、前は-1。 */
    void switchTab(int direction);
};

}  // namespace hedit
