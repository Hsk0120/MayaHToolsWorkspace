/** @file find_bar.h
 * @brief コード欄の右上に重ねて表示する検索・置換バー(Ctrl+F / Ctrl+H)。
 * @details 配置・大きさ・アイコン・動きはVS Codeの検索ウィジェットに合わせ、色とフォントはheditのエディターに合わせる。
 * 部品の配置(格子状。列をそろえて、検索欄と置換欄の位置と幅を同じにする):
 * @code
 * ┌──┬─────────────────────────┬──────────┬──┬──┬──┬──┐
 * │  │ [検索語         Aa ab .*] │ 1 of 4   │ ↑│ ↓│ ≡│ ×│   ← 1行目(高さ33px)
 * │ ⌄├─────────────────────────┼──────────┴──┴──┴──┴──┤
 * │  │ [置換の文字列         AB] │ 置換 全て置換          │   ← 2行目(開いたときだけ。全体で62px)
 * └──┴─────────────────────────┴────────────────────────┘
 * @endcode
 * 寸法は拡大率100%のときのピクセル数(VS Code 1.139を100%で測った値)。幅419px・入力欄の高さ25px・
 * ボタン22px・切り替えボタン20px・アイコン16px。
 * 一致なしは件数を赤く、不正な正規表現は検索欄の枠を赤くして、入力欄の下に理由の吹き出しを出す(VS Codeと同じ)。
 * 本文の中の全ての一致箇所には薄い背景を付ける(CodeEditor::setSearchHighlights)。
 *
 * 速さのための工夫:
 * - 検索の結果は(コード欄・文書の版・検索条件)ごとに覚え、同じなら検索し直さない(F3を続けて押す場合など)。
 *   本文の写し(toPlainText)も文書の版ごとに1回だけ取る。
 * - 正規表現でない検索はQStringMatcherで探す(結果は正規表現で探した場合と同じになるようにしてある)。
 * - 約20万文字を超える本文では、入力・条件の切り替えから少し待ってから検索する(打鍵のたびに全文を探さない)。
 * - アイコン・影は初めて開いたときに作る。影は形が変わったときだけ描き直す(CachedShadowEffect)。
 */
#pragma once
#include "core/text_search.h"
#include <QFont>
#include <QHash>
#include <QList>
#include <QPointer>
#include <QRegularExpression>
#include <QTextCursor>
#include <QTimer>
#include <QWidget>
#include <functional>

class QFrame;
class QLabel;
class QLineEdit;
class QTabWidget;
class QToolButton;

namespace hedit {

class CodeEditor;
enum class FindIcon;

/** @brief 検索・置換バー(objectNameは``findBar``)。
 * @details 一致箇所の計算はcore/text_search.cppに任せ(正規表現でない検索だけはfindPlainMatchesで速く求める)、
 * ここは入力欄・ボタンと、結果に合わせたカーソル移動・件数・強調の表示を行う。
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

    /** @brief 本文やタブが変わったときに呼ぶ。少し待ってから、件数と一致箇所の強調を更新する。
     * @details 入力のたびに全文を検索し直さないよう、最後の変化から150ms後に1回だけ行う。閉じている間は何もしない。
     */
    void scheduleRefresh();

    /** @brief 入力欄と件数の文字を、エディターと同じフォント・大きさにする(文字サイズの変更に合わせて呼ぶ)。
     * @param font エディターのフォント(ピクセル指定、拡大率を掛けた後の大きさ)。
     */
    void setEditorFont(const QFont& font);

    /** @brief 正規表現を使わない検索で一致箇所を求める(結果はcore/text_search.hのfindMatchesと同じ)。
     * @param document 検索する本文。
     * @param options 検索条件。options.regexはfalseであること。
     * @param replacementTemplate 置換の文字列。nullptrなら置換後の文字列は作らない。
     * @param handled findMatchesと同じ結果を保証できない入力(大文字小文字を区別しない英字以外の検索語・
     *        不正なUTF-16を含む本文)ならfalseを入れて、何も求めずに返す。呼出側は正規表現で探し直す。
     * @return 一致箇所と置換後の文字列。
     * @details 大文字小文字を区別しない比較・単語の境界(``\w``)は、正規表現(Unicodeの性質を使う)と同じ規則にする。
     * 単語の文字かどうかは、英数字と_以外をQRegularExpression自身に判定させて覚えておく(Qtの版で規則が違っても同じ結果)。
     */
    SearchResult findPlainMatches(const QString& document, const SearchOptions& options,
                                  const QString* replacementTemplate, bool* handled);

protected:
    /** @brief タブ欄の大きさの変化・入力欄のフォーカス・Shift+Enterを受け取る。
     * @param watched イベントの届いた部品。
     * @param event イベント。
     * @return イベントを処理した(ここで止める)ならtrue。
     */
    bool eventFilter(QObject* watched, QEvent* event) override;

    /** @brief 閉じたときに、本文の一致箇所の強調とエラーの吹き出しを消す。 @param event イベント。 */
    void hideEvent(QHideEvent* event) override;

private:
    /** @brief 入力欄を枠(QFrame)で包む。枠の色で入力中・エラーを表す。
     * @param edit 入力欄。
     * @param name 枠のobjectName。
     * @return 枠。この後、切り替えボタンを枠の中へ足せる。
     */
    QFrame* makeField(QLineEdit* edit, const QString& name);

    /** @brief アイコンのボタンを作る。
     * @param icon アイコン。
     * @param name objectName(テストが探すときの名前)。
     * @param tooltip マウスを重ねたときの説明。
     * @param checkable trueならオン・オフを切り替えるボタン。
     * @param inputOption trueなら入力欄の中の切り替えボタン(20px)、falseなら通常のボタン(22px)。
     * @return 新しいボタン。レイアウトへ追加した時点で親が所有する。
     */
    QToolButton* makeButton(FindIcon icon, const QString& name, const QString& tooltip, bool checkable, bool inputOption);

    /** @brief 置換欄を開閉する。 @param visible trueで開く。 */
    void setReplaceVisible(bool visible);

    /** @brief 初めて開くときに、見た目(スタイルシート・アイコン・影)を用意する。2回目以降は何もしない。
     * @details 編集画面を開くたびに使うとは限らないので、作成時には描かない(アイコン17個と影の用意を後回しにする)。
     */
    void ensureDecorated();

    /** @brief 部品の状態(動的プロパティ)を設定し、スタイルシートを当て直す。
     * @param widget 枠またはラベル。
     * @param property 状態の名前(``focused``・``error``)。
     * @param value 状態。
     */
    void setState(QWidget* widget, const char* property, bool value);

    /** @brief 件数の表示を更新する。 @param text 文字。 @param error trueなら赤で表示する。 */
    void showCount(const QString& text, bool error);

    /** @brief 不正な正規表現の理由を、検索欄の下の吹き出しに出す(空なら隠す)。検索欄の枠も赤くする。
     * @param message 理由。空なら吹き出しを隠して枠を戻す。
     */
    void showError(const QString& message);

    /** @brief 検索欄に1文字入力するたびに、現在の一致を絞り込む(フォーカスは検索欄のまま)。
     * @details 大きな本文では、入力が止まるまで少し待ってから行う(searchTimer_)。
     */
    void searchWhileTyping();

    /** @brief searchWhileTypingの本体。すぐに検索して、選択と件数を更新する。 */
    void searchWhileTypingNow();

    /** @brief カーソルは動かさずに、件数と一致箇所の強調だけを更新する(本文の変更・タブの切り替え後)。 */
    void refreshMatches();

    /** @brief 検索条件の切り替えのとき、件数と強調を更新する。大きな本文では少し待ってから行う。 */
    void scheduleOptionRefresh();

    /** @brief 待っている入力中の検索・条件の切り替えの更新があれば、今すぐ行う(Enter・F3・置換の前)。 */
    void flushPendingSearch();

    /** @brief 本文が大きい(待ってから検索する)か。 @param editor コード欄。 @return 約20万文字を超えればtrue。 */
    static bool isLargeDocument(const CodeEditor* editor);

    /** @brief コード欄の本文の写し。文書の版が変わっていなければ前回の写しを使う。
     * @param editor コード欄。
     * @return 本文(toPlainText)。
     */
    const QString& documentText(CodeEditor* editor);

    /** @brief 正規表現の``\w``(Unicodeの性質を使う)に当たる文字か。 @param code 文字(UCS-4)。 @return 当たればtrue。 */
    bool isWordCharacter(uint code);

    /** @brief 画面のボタンから検索条件を作る。 @return 検索条件。 */
    SearchOptions options() const;

    /** @brief 現在のコード欄で一致箇所を求める。失敗なら理由を吹き出しとステータスバーに出す。
     * @param withReplacements trueなら置換後の文字列も作る。
     * @return 検索の結果。
     */
    SearchResult search(bool withReplacements);

    /** @brief 検索の結果に合わせて、件数・エラー・本文の強調をまとめて更新する。
     * @param result 検索の結果。
     * @param current 選択中の一致の番号(0始まり)。分からなければ-1(「? of N」と表示する)。
     */
    void showResult(const SearchResult& result, int current);

    /** @brief 本文の中の一致箇所に薄い背景を付ける。前に付けたコード欄が別なら、そちらは消す。
     * @param result 検索の結果。
     */
    void highlight(const SearchResult& result);

    /** @brief 一致箇所の背景を消す。 */
    void clearHighlights();

    /** @brief 「選択範囲内で検索」をオン・オフする。オンにした時点の選択範囲を覚える。 @param enabled trueでオン。 */
    void setFindInSelection(bool enabled);

    /** @brief 一致箇所を選択して、見える位置までスクロールする。 @param match 選択する一致。 */
    void selectMatch(const TextMatch& match);

    /** @brief バーをタブ欄の右上へ置く。吹き出しの位置も合わせる。非表示の間は何もしない。 */
    void updatePosition();

    /** @brief バーを閉じ、コード欄へフォーカスを戻す。 */
    void closeBar();

    QTabWidget* tabs_;                    ///< 重ねる先のタブ欄(親)。
    QToolButton* toggleReplace_;          ///< 置換欄を開閉するボタン(›/⌄)。
    QFrame* findField_;                   ///< 検索欄の枠(検索語と切り替えボタンを含む)。
    QFrame* replaceField_;                ///< 置換欄の枠(置換の文字列とABを含む)。
    QLineEdit* findText_;                 ///< 検索語。
    QLineEdit* replaceText_;              ///< 置換の文字列。
    QToolButton* matchCase_;              ///< ``Aa``: 大文字小文字を区別。
    QToolButton* wholeWord_;              ///< ``ab``: 単語単位。
    QToolButton* regex_;                  ///< ``.*``: 正規表現。
    QToolButton* preserveCase_;           ///< ``AB``: 置換で大文字小文字を保つ。
    QToolButton* inSelection_;            ///< ``≡``: 選択範囲内で検索。
    QToolButton* replaceOne_;             ///< 選択中の一致を置換するボタン。
    QToolButton* replaceAll_;             ///< 全て置換するボタン。
    QLabel* matchCount_;                  ///< ``1 of 4``のような件数。
    QLabel* errorBubble_;                 ///< 不正な正規表現の理由の吹き出し(タブ欄の子で、バーの下にはみ出して表示)。
    QTimer refreshTimer_;                 ///< 本文の変化の後、少し待ってから件数と強調を更新する。
    QTimer searchTimer_;                  ///< 大きな本文で、入力・条件の切り替えが止まってから検索する。
    bool typingPending_ = false;          ///< searchTimer_で行うのが入力中の検索ならtrue(条件の切り替えだけならfalse)。
    QPointer<CodeEditor> highlighted_;    ///< 一致箇所の背景を付けたコード欄。閉じられたら自動でnullptr。
    int highlightedGeneration_ = -1;      ///< highlighted_に付けた一致箇所の、検索の結果の番号(同じなら付け直さない)。
    QPointer<CodeEditor> scopeEditor_;    ///< 「選択範囲内で検索」の範囲を持つコード欄。
    QTextCursor scope_;                   ///< 「選択範囲内で検索」の範囲(本文の編集に合わせて位置が動く)。

    // 見た目(初めて開くときに用意する)。
    bool decorated_ = false;              ///< スタイルシート・アイコン・影を用意したか。
    QList<QPair<QToolButton*, FindIcon>> iconButtons_;  ///< アイコンを後で描くボタンと、その種類。

    // 検索の結果と本文の写しの控え(同じなら検索し直さない)。
    QPointer<CodeEditor> textEditor_;     ///< textの写しを取ったコード欄。
    int textRevision_ = -1;               ///< 写しを取ったときの文書の版。
    QString text_;                        ///< 本文の写し。
    int textValidity_ = -1;               ///< 写しが正しいUTF-16か(-1は未確認、0は不正、1は正しい)。
    QPointer<CodeEditor> resultEditor_;   ///< 控えた結果のコード欄。
    int resultRevision_ = -1;             ///< 控えた結果の文書の版。
    SearchOptions resultOptions_;         ///< 控えた結果の検索条件。
    SearchResult result_;                 ///< 控えた結果(置換後の文字列は含まない)。
    int resultGeneration_ = 0;            ///< 控えた結果の番号。検索し直すたびに増やす。
    int currentGeneration_ = -1;          ///< 直前のsearch()の結果の番号(置換の検索は控えないので-1)。
    QRegularExpression wordPattern_;      ///< 1文字が``\w``に当たるかを調べる正規表現。
    QHash<uint, bool> wordCharacters_;    ///< 英数字と_以外の文字が``\w``に当たるかの控え。
};

}  // namespace hedit
