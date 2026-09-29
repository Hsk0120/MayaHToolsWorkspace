/** @file find_bar.h
 * @brief コード欄の右上に重ねて表示する検索・置換バー(Ctrl+F / Ctrl+H)。
 */
#pragma once
#include "core/text_search.h"
#include <QWidget>
#include <functional>

class QCheckBox;
class QLabel;
class QLineEdit;
class QTabWidget;

namespace hedit {

class CodeEditor;

/** @brief 検索・置換バー(objectNameは``findBar``)。
 * @details 一致箇所の計算はcore/text_search.cppに任せ、ここは入力欄・ボタンと、
 * 結果に合わせたカーソル移動・件数の表示だけを行う。
 * タブ欄の子として作り、タブ欄の右上へ重ねる(レイアウトには入れない)。
 */
class FindBar : public QWidget {
public:
    /** @brief 入力欄・切り替えボタン・置換欄を作る。作成直後は非表示。
     * @param tabs 重ねて表示する先のタブ欄。このバーの親(所有者)になる。
     */
    explicit FindBar(QTabWidget* tabs);

    /// 検索の対象になる、現在のコード欄を返す関数。MainWindowが設定する。
    std::function<CodeEditor*()> currentEditor;
    /// ステータスバーへ文字を出す関数(文字列, 表示するミリ秒。0なら消えない)。MainWindowが設定する。
    std::function<void(const QString&, int)> showStatus;

    /** @brief バーを開き、入力欄へフォーカスを移す。
     * @param withReplace trueなら置換欄も表示する。
     * @details 1行だけの選択があれば、その文字列を検索語にする。
     */
    void open(bool withReplace);

    /** @brief 次(または前)の一致箇所を選択する。末尾・先頭で折り返す。
     * @param backward trueなら前へ。
     * @return 移動できた場合true。検索語が空ならバーを開いてfalse。
     */
    bool findNext(bool backward = false);

    /** @brief 置換する。
     * @param all trueなら全ての一致を置換(1回のUndoで戻せる)。falseなら選択中の一致だけ置換して次へ移る。
     */
    void replace(bool all);

protected:
    /** @brief タブ欄の大きさが変わったら、右上の位置を合わせ直す。
     * @param watched イベントの届いた部品。
     * @param event イベント。
     * @return 常にfalse(イベントは止めない)。
     */
    bool eventFilter(QObject* watched, QEvent* event) override;

private:
    /** @brief 検索欄に1文字入力するたびに、現在の一致を絞り込む(フォーカスは検索欄のまま)。 */
    void searchWhileTyping();

    /** @brief 画面のチェックボックスから検索条件を作る。 @return 検索条件。 */
    SearchOptions options() const;

    /** @brief 現在のコード欄で一致箇所を求める。失敗ならステータスバーに理由を出す。
     * @param withReplacements trueなら置換後の文字列も作る。
     * @return 検索の結果。
     */
    SearchResult search(bool withReplacements);

    /** @brief 一致箇所を選択して、見える位置までスクロールする。
     * @param match 選択する一致。
     */
    void selectMatch(const TextMatch& match);

    /** @brief バーをタブ欄の右上へ置く。非表示の間は何もしない。 */
    void updatePosition();

    /** @brief バーを閉じ、コード欄へフォーカスを戻す。 */
    void closeBar();

    QTabWidget* tabs_;          ///< 重ねる先のタブ欄(親)。
    QLineEdit* findText_;       ///< 検索語。
    QLineEdit* replaceText_;    ///< 置換の文字列。
    QWidget* replaceRow_;       ///< 置換欄の行(表示・非表示を切り替える)。
    QCheckBox* matchCase_;      ///< ``Tt``: 大文字小文字を区別。
    QCheckBox* wholeWord_;      ///< ``Abc``: 単語単位。
    QCheckBox* regex_;          ///< ``.*``: 正規表現。
    QLabel* matchCount_;        ///< ``1 of 3``のような件数。
};

}  // namespace hedit
