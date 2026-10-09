/** @file code_editor.h
 * @brief 1つのタブのコード欄。入力のショートカット・自動インデント・補完候補・スペルの波線を担当する。
 * @details 実装は2つのファイルに分けている:
 * - code_editor.cpp      : 入力(キー操作・括弧の自動で閉じる・補完・ホバー・引数のヒント)
 * - code_editor_view.cpp : 表示(同じ名前と括弧の強調・問題の波線・インデントの縦線・折りたたみ・
 *                          見出しの固定表示・保存前との差分の印・スクロールバーの印)
 */
#pragma once
#include "core/code_outline.h"
#include "core/completion_types.h"
#include "core/line_diff.h"
#include "core/script_lexer.h"
#include "core/text_search.h"
#include "editor/code_navigation.h"
#include "editor/numbered_text_edit.h"
#include <QList>
#include <QPair>
#include <QString>
#include <QStringList>
#include <QTextCursor>
#include <QTextEdit>
#include <QTimer>
#include <QVector>
#include <functional>
#include <memory>
#include <vector>

class QCompleter;
class QTextLayout;

namespace hedit {

class HoverPopup;
class MarkerScrollBar;
class Spelling;
class StickyHeader;
class SyntaxHighlighter;

/** @brief 1つのタブのコード欄(objectNameは``codeEditor``)。
 * @details タブを閉じる・実行する・補完を求めるといった「画面全体に関わる操作」は、この欄では行わず、
 * onCloseRequestedなどの関数を呼んでMainWindowへ任せる。
 *
 * テストやPySideから参照できるよう、次の値はQtの動的プロパティ(property())にも入れている:
 * ``language``(python/mel)、``path``(保存先)、``spellCheckAvailable``、``spellCheckMilliseconds``。
 */
class CodeEditor : public NumberedTextEdit {
public:
    /** @brief 本文・行番号・補完候補・構文強調・現在行の強調を用意する。
     * @param parent 所有者。通常はタブ欄に追加したときに決まる。
     */
    explicit CodeEditor(QWidget* parent = nullptr);

    /** @brief 破棄の途中で出るシグナル(スクロール・文書の変更)が、片付け済みのメンバーを使わないよう接続を外す。 */
    ~CodeEditor() override;

    // ---- 言語と保存先 ----

    /** @brief 言語を設定し、色分けを塗り直す。 @param language 言語。 */
    void setLanguage(ScriptLanguage language);
    /** @brief 言語を返す。 @return PythonかMEL。 */
    ScriptLanguage language() const { return language_; }
    /** @brief MELのタブか。 @return MELならtrue。 */
    bool isMel() const { return language_ == ScriptLanguage::Mel; }
    /** @brief 保存先を設定する。 @param path 絶対パス。未保存の新規タブは空。 */
    void setFilePath(const QString& path);
    /** @brief 保存先を返す。 @return 未保存の新規タブは空。
     * @note 保存先は動的プロパティ``path``そのものに持つ。GUIテストはPySideから``setProperty('path', ...)``で
     * 保存先を書き換えるため、C++側に別の変数を持つと食い違う。
     */
    QString filePath() const { return property("path").toString(); }
    /** @brief タブに表示する名前を返す。 @return ファイル名。新規なら``Untitled.py``か``Untitled.mel``。 */
    QString displayName() const;

    // ---- 設定(Preferences) ----

    /** @brief Enterで前の行のインデントを引き継ぐか。 @param enabled trueで引き継ぐ。 */
    void setSmartIndent(bool enabled) { smartIndent_ = enabled; }
    /** @brief 空白だけの行頭でBackspaceを押したとき、4文字単位で消すか。 @param enabled trueで4文字単位。 */
    void setBackspaceToIndentStop(bool enabled) { backspaceToIndentStop_ = enabled; }
    /** @brief 空白とタブを記号で表示するか。 @param visible trueで表示する。 */
    void setWhitespaceVisible(bool visible);
    /** @brief 括弧と引用符を自動で閉じるか。 @param enabled trueで閉じる。 */
    void setAutoClosing(bool enabled) { autoClosing_ = enabled; }
    /** @brief クラス・関数の見出しを上端に残すか(見出しの固定表示)。 @param enabled trueで残す。 */
    void setStickyScroll(bool enabled);

    // ---- 補完 ----

    /** @brief 補完の部品を返す。 @return この欄が所有するQCompleter。 */
    QCompleter* completer() const { return completer_; }
    /** @brief カーソルの直前の、補完中の名前を返す。 @return 英数字と``_``だけ(ドットは含まない)。 */
    QString completionPrefix() const;
    /** @brief 候補を一覧で表示する。
     * @param items 表示する候補。入力した名前に一致するもの(fuzzyScore)を、一致の度合いの順に出す。
     *        一致するものが無ければ一覧を閉じる。
     */
    void showCompletions(const QList<CompletionItem>& items);
    /** @brief 候補の一覧を閉じる。 */
    void hideCompletions();
    /** @brief 候補の一覧を出しているか。 @return 出していればtrue。 */
    bool isCompletionVisible() const;
    /** @brief 一覧を出したまま、入力した名前で候補を絞り込み直す(入力のたびに閉じて開き直さない)。
     * @param keepWhenEmpty trueなら、絞り込んで候補が無くなっても閉じない(呼出側がすぐ候補を求め直して入れ替える場合)。
     * @return 一覧が開いたままならtrue。補完中の名前の外へ出た・候補が無くなった場合は閉じてfalse。
     */
    bool refilterCompletions(bool keepWhenEmpty = false);
    /** @brief 候補の確定で本文を変更している最中か。
     * @return trueの間の本文変更は、利用者の入力として扱わない(次の補完を予約しない)。
     */
    bool isInsertingCompletion() const { return insertingCompletion_; }
    /** @brief 最後の本文の変更で、文字が増えたか。
     * @return 入力・貼り付けならtrue。Backspace・Deleteで消しただけならfalse(消したときは補完を開き直さない)。
     */
    bool lastEditInsertedText() const { return lastEditInserted_; }

    // ---- スペルチェック ----

    /** @brief 表示中の範囲だけを調べ、知らない英単語に波線を付ける。
     * @param spelling Windowsの辞書。
     * @details 入力中の単語(カーソルがあり、直前に文字を入れた単語)には付けない(打っている途中で波線が出ない)。
     * カーソルがその単語から離れたらonSpellingRecheckRequestedで知らせ、調べ直してもらう。
     */
    void checkSpelling(Spelling& spelling);
    /** @brief スペルの波線を全て消す。 */
    void clearSpelling();

    // ---- 検索の一致箇所 ----

    /** @brief 検索の一致箇所に薄い背景を付ける(選択中の一致は、選択の色で表示される)。
     * @param matches 一致箇所。多すぎると描画が重くなるので、呼出側で件数を絞る。
     */
    void setSearchHighlights(const QList<TextMatch>& matches);
    /** @brief 検索の一致箇所の背景を消す。 */
    void clearSearchHighlights();

    // ---- 問題(構文チェック)の波線 ----

    /** @brief 問題を波線で示す(エラーは赤、警告は黄色)。 @param diagnostics 問題。行は1始まり。
     * @details 行は編集に合わせて追従する(行を挿入しても、次の構文チェックまで印が別の行を指さない)。
     */
    void setDiagnostics(const QList<Diagnostic>& diagnostics);
    /** @brief 今の問題。 @return 問題。 */
    const QList<Diagnostic>& diagnostics() const { return diagnostics_; }
    /** @brief 次(前)の問題へ移り、その説明を行の下に出す(F8 / Shift+F8)。
     * @param direction 次は1、前は-1。端では反対側へ折り返す。
     * @return 問題があればtrue。
     */
    bool goToProblem(int direction);

    // ---- 保存前との差分 ----

    /** @brief 保存した内容を設定する。行番号の横に、それとの違い(追加・変更・削除)の印を出す。
     * @param text ファイルの内容。
     */
    void setSavedText(const QString& text);
    /** @brief 保存した内容を消し、変更の印を出さない(保存先の無い新規タブ)。 */
    void clearSavedText();
    /** @brief 保存した内容があるか。 @return 設定済みならtrue。 */
    bool hasSavedText() const { return hasSavedText_; }
    /** @brief 保存した内容。 @return 内容(改行は``\n``)。 */
    QString savedText() const { return savedText_; }
    /** @brief 保存した内容との違い。 @return 変更のまとまり。入力が止まってから0.3秒後に求め直す。 */
    const QList<LineChange>& lineChanges() const { return lineChanges_; }
    /** @brief 保存した内容との違いを、すぐ求め直す。 */
    void updateLineChanges();

    // ---- 構成と折りたたみ ----

    /** @brief 本文の構成(クラス・関数・変数)。本文が変わっていなければ前回の結果を使う。 @return 項目の一覧。 */
    const QList<OutlineEntry>& outline() const;
    /** @brief 折りたたみの範囲(インデントで決める)。 @return 範囲の一覧。 */
    const QList<FoldRange>& foldRanges() const;
    /** @brief 行を見出しとする範囲を畳む。 @param line 行(0始まり)。 @return 畳めたらtrue。 */
    bool foldAt(int line);
    /** @brief 行を見出しとする範囲を開く。 @param line 行(0始まり)。 @return 開いたらtrue。 */
    bool unfoldAt(int line);
    /** @brief カーソルを含むいちばん内側の範囲を畳む(Ctrl+Shift+[)。 */
    void foldAtCursor();
    /** @brief カーソルの行が畳んだ見出しなら開く(Ctrl+Shift+])。 */
    void unfoldAtCursor();
    /** @brief 全ての範囲を畳む(Ctrl+K Ctrl+0)。 */
    void foldAll();
    /** @brief 全ての範囲を開く(Ctrl+K Ctrl+J)。 */
    void unfoldAll();
    /** @brief 行が畳んだ見出しか。 @param line 行(0始まり)。 @return 畳んでいればtrue。 */
    bool isFolded(int line) const;

    // ---- 選択範囲の拡大 ----

    /** @brief 選択範囲を、次に大きい意味のまとまりへ広げる(Shift+Alt+→)。 */
    void expandSelection();
    /** @brief 広げる前の選択範囲へ戻す(Shift+Alt+←)。 */
    void shrinkSelection();

    // ---- 同じ名前・括弧の強調(テスト用にも使う) ----

    /** @brief カーソルの名前と同じ名前の強調を、すぐ求め直す(普段は入力が止まって0.15秒後)。 */
    void updateWordHighlights();
    /** @brief 強調している同じ名前の位置。 @return 先頭の位置の一覧。 */
    const QList<int>& wordHighlights() const { return wordPositions_; }
    /** @brief 強調している対応する括弧。 @return 2つの位置。無ければ空。 */
    QList<int> bracketHighlights() const { return bracketPositions_; }
    /** @brief 印を描くスクロールバー。 @return スクロールバー。所有者はこの欄。 */
    MarkerScrollBar* markerScrollBar() const { return markers_; }
    /** @brief スクロールバーの印を、すぐ描き直す(印の元が変わっていなければ、カーソルの行だけ)。 */
    void updateScrollMarkers();
    /** @brief 上端に残している見出しの行。 @return 行(0始まり)の一覧。外側から順。 */
    const QList<int>& stickyLines() const { return stickyLines_; }

    // ---- 引数のヒント・補完の説明・定義をその場で見る ----

    /** @brief 引数のヒントを、カーソルの行の上に出す。 @param html HoverPopup::signatureHelpHtmlで作ったHTML。 */
    void showSignatureHelp(const QString& html);
    /** @brief 引数のヒントを閉じる。 */
    void hideSignatureHelp();
    /** @brief 引数のヒントを出しているか。 @return 出していればtrue。 */
    bool isSignatureHelpVisible() const;
    /** @brief 補完の一覧で選んでいる候補の名前。 @return 名前。一覧が閉じていれば空。 */
    QString currentCompletion() const;
    /** @brief 補完の一覧の横に、選んでいる候補の説明を出す。 @param info 見出しとdocstring。空なら閉じる。 */
    void showCompletionDetail(const HoverInfo& info);
    /** @brief 補完の候補の説明を閉じる。 */
    void hideCompletionDetail();
    /** @brief 定義の周りのコードを、名前の下に出す(定義をその場で見る、Alt+F12)。
     * @param html HoverPopup::snippetHtmlで作ったHTML。
     * @param position 名前の位置(この下に出す)。
     */
    void showPeek(const QString& html, int position);
    /** @brief 定義をその場で見る表示と、F8の問題の説明を閉じる。 */
    void hidePeek();
    /** @brief テキストカーソルの位置の名前の終わり。 @return 位置。名前の上でなければ-1。 */
    int nameEndAtCursor() const;

    // ---- ホバー(名前の説明) ----

    /** @brief テキストカーソルの位置の名前の説明を出す(Edit → Show hover、Ctrl+K Ctrl+I)。 */
    void showHoverAtCursor();
    /** @brief 名前の説明を閉じる。 */
    void hideHover();

    // ---- MainWindowへ任せる操作(空なら何もしない) ----

    /// 名前の説明を求める(名前の終わりの位置)。MELのタブや、説明が無ければ空のHoverInfoを返す。
    std::function<HoverInfo(int end)> onHoverRequested;

    /// 定義を求める(名前の終わりの位置, その場で見るならtrue)。F12・Alt+F12・Ctrl+クリック。
    std::function<void(int end, bool peek)> onDefinitionRequested;
    /// 引数のヒントを求める(Ctrl+Shift+Spaceならtrue)。``(``・``,``の入力と、ヒントの表示中のカーソル移動で呼ぶ。
    std::function<void(bool explicitRequest)> onSignatureHelpRequested;
    /// 補完の一覧で選んでいる候補が変わった(候補の説明を出し直す)。
    std::function<void()> onCompletionSelectionChanged;
    /// 入力中だったため波線を付けなかった単語から、カーソルが離れた(スペルを調べ直す)。
    std::function<void()> onSpellingRecheckRequested;

    std::function<void()> onCompletionRequested;  ///< Ctrl+Spaceが押された。
    std::function<void()> onRunRequested;         ///< Ctrl+EnterかテンキーのEnterが押された。
    std::function<void()> onCloseRequested;       ///< Ctrl+WかCtrl+F4が押された。
    /// 小窓・補完の一覧が無いときにEscが押された(検索バーを閉じる)。処理したらtrueを返す。
    std::function<bool()> onEscapePressed;

protected:
    /** @brief heditのショートカットを、Mayaのショートカットより先に受け取る。
     * @param event Qtのイベント。
     * @return 処理した場合true。
     */
    bool event(QEvent* event) override;

    /** @brief heditのキー操作を処理し、残りはQt標準の入力処理へ渡す。
     * @param event キー入力。
     */
    void keyPressEvent(QKeyEvent* event) override;

    /** @brief 本文の表示部分へのマウスの操作を受け取る。止まったら名前の説明を出し、離れたら閉じる。
     * @param event Qtのイベント。QEvent::ToolTipは、マウスが少し止まったときにQtが送る。
     * @return 処理した場合true。
     */
    bool viewportEvent(QEvent* event) override;

    /** @brief フォーカスを失ったら、名前の説明を閉じる。 @param event イベント。 */
    void focusOutEvent(QFocusEvent* event) override;

    /** @brief 貼り付け・ドロップの文字列を、行の区切りを``\n``にそろえて挿入する。
     * @param source 貼り付ける内容。
     * @note Webページなどからコピーした文字列にはU+2028(行区切り)が混ざることがある。そのまま入れると
     *       Pythonの実行で「invalid non-printable character U+2028」のSyntaxErrorになる。
     */
    void insertFromMimeData(const QMimeData* source) override;

    /** @brief 本文を描いた後に、インデントの縦線と、畳んだ見出しの「⋯」を重ねる。
     * @param event 描き直す範囲。カーソルの点滅では、その行だけが来る(範囲の外の行は描かない)。
     */
    void paintEvent(QPaintEvent* event) override;

    /** @brief 大きさが変わったら、見出しの固定表示の大きさも合わせる。 @param event 大きさの変化。 */
    void resizeEvent(QResizeEvent* event) override;

    /** @brief 補完の一覧が閉じたら、候補の説明も閉じる。 @param watched 対象。 @param event イベント。 @return 基底の結果。 */
    bool eventFilter(QObject* watched, QEvent* event) override;

    /** @brief 折りたたみの矢印の欄の幅。 @return ピクセル数。 */
    int extraGutterWidth() const override;
    /** @brief 変更の印と折りたたみの矢印を描く。 @param painter 描画。 @param block 行。 @param rect 行の範囲。 */
    void paintGutterBlock(QPainter& painter, const QTextBlock& block, const QRectF& rect) override;
    /** @brief 見出しの固定表示の行番号を描く。 @param painter 描画。 @param rect 描き直す範囲。 */
    void paintGutterOverlay(QPainter& painter, const QRect& rect) override;
    /** @brief 折りたたみの矢印のクリックで、畳む・開く。 @param position 位置。 */
    void gutterPressed(const QPoint& position) override;

private:
    friend class StickyHeader;

    /** @brief 表示の部品(印のスクロールバー・見出しの固定表示)とタイマーを用意する(コンストラクターから1回だけ呼ぶ)。 */
    void setUpView();

    /** @brief カーソルが動いたときの表示の更新(括弧・同じ名前・畳んだ範囲・引数のヒント)。 */
    void onCursorMoved();

    /** @brief 括弧・引用符の入力を処理する(自動で閉じる・閉じ括弧を上書き・選択を囲む・空の対をまとめて消す)。
     * @param event キー入力。
     * @return 処理した場合true。
     */
    bool handleAutoClosing(QKeyEvent* event);

    /** @brief カーソルの隣の括弧と、対応する括弧を強調する。 */
    void updateBracketMatch();

    /** @brief 本文が変わったときの表示の更新(折りたたみ・差分・見出しの固定表示)。 */
    void onContentsChanged();

    /** @brief 本文の一部が変わったときに、編集した範囲に合わせて印を直す(QTextDocument::contentsChangeから呼ぶ)。
     * @param position 変わった位置。
     * @param removed 削除した文字数。
     * @param added 追加した文字数。
     * @details 編集した単語のスペルの波線だけを消し、行の増減に合わせて変更の印をずらす
     * (全体を消して数百ms後に描き直すと、入力のたびに印がちらつくため)。
     */
    void onContentsChange(int position, int removed, int added);

    /** @brief 本文に重ねる印を、イベントループへ戻ってから渡し直す(スクロール・大きさの変化のとき)。
     * @details 印の渡し直しはQTextCursorを作り・消すため、Qtの文書の処理の途中かもしれない通知の中では行わない。
     */
    void scheduleDecorations();

    /** @brief 本文の変更の後でまとめて行う処理(編集した単語のスペルの波線を消す・畳んだ範囲を合わせ直す・印を渡し直す)。
     * @details 本文の変更の通知(contentsChange・contentsChanged)の中ではQTextCursorを作らない・消さないため、
     * イベントループへ戻ってから(0msのタイマーで)行う。
     */
    void applyEditFollowUps();

    /** @brief 行が折りたたみの見出しか(次の空でない行の方がインデントが深いか)。
     * @param block 行。
     * @return 見出しならtrue。indentationFoldRangesと同じ判断を、前後の行だけで行う(本文全体を読まない)。
     */
    bool isFoldHeader(const QTextBlock& block) const;

    /** @brief 見出しの行から畳む最後の行を求める。
     * @param header 見出しの行。
     * @return 最後の行(0始まり)。畳めない行なら-1。indentationFoldRangesと同じ結果を、その範囲だけ読んで求める。
     */
    int foldEnd(const QTextBlock& header) const;

    /** @brief カーソルのあるブロック(インデントの縦線を明るくする範囲)を、必要なときだけ求め直す。
     * @param firstLine 表示している最初の行。
     * @param lastLine 表示している最後の行。
     * @details 範囲は表示している行の外までは求めない(画面の外の行の縦線は描かないため)。
     * 文書の版・カーソルの行・表示範囲が前回と同じなら、前回の結果を使う(カーソルの点滅のたびに走査しない)。
     */
    void updateActiveGuide(int firstLine, int lastLine);

    /** @brief 問題の今の行を返す(編集に合わせて追従した行)。 @param index diagnostics_の番号。 @return 行(1始まり)。 */
    int diagnosticLine(int index) const;

    /** @brief 補完の一覧の部品(QCompleter::popup)を作って整える(初めて一覧を出すときに1回だけ)。
     * @details 一覧の部品と、その見た目(スタイルシート)の解析は、タブを開くたびには行わない。
     */
    void ensureCompletionPopup();
    /** @brief 畳んだ見出しの一覧に合わせて、行の表示・非表示を設定し直す。 */
    void applyFolds();

    /** @brief カーソルの行が畳んだ範囲に隠れていれば開く。 */
    void revealCursor();

    /** @brief 位置の上にある問題の説明を返す。 @param position 位置。 @return 説明の一覧。 */
    QStringList problemsAt(int position) const;

    /** @brief 見出しの固定表示を計算し直す。 */
    void updateSticky();

    /** @brief 見出しの固定表示を描く(StickyHeaderのpaintEventから呼ぶ)。 @param painter 描画。 */
    void paintSticky(QPainter& painter);

    /** @brief 見出しの固定表示の1行の高さ。 @return ピクセル数。 */
    int stickyLineHeight() const;

    /** @brief 見出しの固定表示がクリックされた行へ移る。 @param y 表示の中の縦の位置。 */
    void stickyClicked(int y);

    /** @brief 位置にある名前の範囲を求める。文字列・コメント・予約語の上なら名前として扱わない。
     * @param position 文書の中の位置。
     * @param start 名前の先頭の位置を入れる。
     * @param end 名前の終わりの位置を入れる。
     * @return 名前の上ならtrue。
     */
    bool nameAt(int position, int* start, int* end) const;

    /** @brief 表示部分の位置の名前(または問題)の説明を出す。マウスが止まったときに呼ぶ。
     * @param position 表示部分(viewport)の中の位置。
     * @details QtのツールチップのイベントはMayaの「Help → Popup Help」がオフだとMayaに止められるため、
     * マウスの移動から自前のタイマー(0.3秒)で呼ぶ。
     */
    void hoverAt(const QPoint& position);

    /** @brief 名前の説明を求めて表示する。説明が無ければ閉じる。
     * @param start 名前の先頭の位置。
     * @param end 名前の終わりの位置。
     */
    void showHover(int start, int end);

    /** @brief Ctrl+EnterかテンキーのEnterか(スクリプトの実行キー)。
     * @param event キー入力。
     * @return 実行キーならtrue。
     */
    static bool isRunKey(const QKeyEvent* event);

    /** @brief 空白だけの行頭で、Backspaceを4文字単位で消す。 @return 処理した場合true。 */
    bool deleteToIndentStop();

    /** @brief 改行し、前の行のインデントを引き継ぐ。
     * @details Pythonでは VS Code の Python 拡張と同じ規則にする。
     * - ``:``・開き括弧で終わる行の次は1段深くする。``return``・``pass``・``break``・``continue``・``raise``の次は1段浅くする。
     * - 開き括弧と閉じ括弧の間なら、閉じ括弧を次の行へ送り、間の行を1段深くする。
     * - 空白だけの行で押したら、その行の空白は消す(空行にインデントを残さない)。
     * MELは``{``で終わる行の次を1段深くする。
     */
    void insertNewlineWithIndent();

    /** @brief ``else:``・``elif ...:``・``except ...:``・``finally:``の``:``を打った直後に、その行を1段浅くする。
     * @details 前の行と同じ深さ(まだ前のブロックの中)にあるときだけ浅くする(自分で浅くした行はそのまま)。
     */
    void dedentBlockKeyword();

    /** @brief Home: 行頭の空白の後へ動く。既にそこにいれば行の先頭へ(VS Codeと同じ)。 @param select Shift+Homeならtrue。 */
    void moveToLineHome(bool select);

    /** @brief カーソルの行が見出しの固定表示の下に隠れていれば、見える位置までスクロールする。 */
    void revealUnderSticky();

    /** @brief 自動で入れた閉じ括弧・閉じ引用符か(上書き・まとめて消すのは、自動で入れたものだけ)。
     * @param position 文書の中の位置。
     * @param character その位置の文字。
     * @return 自動で入れたもので、まだその位置にあればtrue。
     */
    bool isAutoCloser(int position, QChar character) const;

    /** @brief 自動で入れた閉じ括弧の控えから、消された・別の行へ移ったものを除く(キー入力の処理の中で呼ぶ)。 */
    void pruneAutoClosers();

    /** @brief 補完の候補を、入力中の名前で絞り込んで一覧に入れる。
     * @param prefix 入力中の名前。
     * @return 一覧に入れた件数。
     */
    int applyCompletionFilter(const QString& prefix);

    /** @brief 候補の確定。補完中の名前を、選んだ名前で置き換える。 @param value 選んだ名前。 */
    void insertCompletion(const QString& value);

    /** @brief カーソル行の背景・同じ名前・括弧・検索の一致・問題・スペルの波線を、まとめて本文に重ねる。
     * @details 表示している範囲(と前後に少し)にかかる印だけを渡す。QPlainTextEditは描くたびに、表示中の行ごとに
     * 全ての印を調べるため、数千件の印をそのまま渡すと、カーソルの点滅やスクロールのたびに重くなる。
     * スクロールで表示範囲が変わったら、渡し直す。
     */
    void updateDecorations();

    ScriptLanguage language_ = ScriptLanguage::Python;   ///< 言語。
    bool smartIndent_ = true;                            ///< Enterでインデントを引き継ぐか。
    bool backspaceToIndentStop_ = true;                  ///< Backspaceを4文字単位で消すか。
    bool insertingCompletion_ = false;                   ///< 候補の確定中か。
    bool lastEditInserted_ = false;                      ///< 最後の本文の変更で文字が増えたか。
    int lastEditEnd_ = -1;                               ///< 最後に文字を入れた範囲の終わり(入力中の単語の判断)。無ければ-1。
    QList<CompletionItem> completionItems_;              ///< 補完エンジンが返した候補(絞り込む前)。
    QList<QTextCursor> autoClosers_;                     ///< 自動で入れた閉じ括弧・閉じ引用符(1文字を選んだカーソル。編集に合わせて動く)。
    QTextCursor spellingSkipped_;                        ///< 入力中のため波線を付けなかった単語(選んだカーソル)。無ければnull。
    bool spellingRecheckSent_ = false;                   ///< spellingSkipped_から離れたことを知らせたか。
    SyntaxHighlighter* highlighter_ = nullptr;           ///< 色分け。所有者は文書。
    QCompleter* completer_ = nullptr;                    ///< 補完の一覧。所有者はこの欄。
    HoverPopup* hover_ = nullptr;                        ///< 名前の説明の小窓。初めて使うときに作る。所有者はこの欄。
    QList<QTextEdit::ExtraSelection> spellingMarks_;     ///< スペルの波線。
    QList<QTextEdit::ExtraSelection> searchMarks_;       ///< 検索の一致箇所の背景。
    QList<QTextEdit::ExtraSelection> wordMarks_;         ///< 同じ名前の背景。
    QList<QTextEdit::ExtraSelection> bracketMarks_;      ///< 対応する括弧の背景。
    QList<QTextEdit::ExtraSelection> diagnosticMarks_;   ///< 問題の波線。

    bool autoClosing_ = true;               ///< 括弧と引用符を自動で閉じるか。
    bool stickyScroll_ = true;              ///< 見出しを上端に残すか。
    QList<int> wordPositions_;              ///< 同じ名前の位置。
    QList<int> bracketPositions_;           ///< 対応する括弧の位置。
    BracketCache bracketCache_;             ///< 括弧の対応を探すときの、行ごとの括弧の控え(本文が変わるまで使う)。
    QString wordName_;                      ///< 同じ名前の強調を求めた名前(同じ名前・同じ本文なら求め直さない)。
    int wordRevision_ = -1;                 ///< 同じ名前の強調を求めたときの文書の版。
    QList<Diagnostic> diagnostics_;         ///< 問題。
    QList<QTextCursor> diagnosticAnchors_;  ///< 問題ごとの行の先頭(QTextCursorは編集に合わせて位置が動く)。
    QString savedText_;                     ///< 保存した内容。
    QStringList savedLines_;                ///< 保存した内容の行(差分を求めるたびに分け直さない)。
    bool hasSavedText_ = false;             ///< 保存した内容があるか。
    QList<LineChange> lineChanges_;         ///< 保存した内容との違い。
    QVector<char> changeKinds_;             ///< 行ごとの変更の種類(0=なし・1=追加・2=変更)。
    QVector<char> deletedAbove_;            ///< 行の上で削除された行があれば1。
    int lastBlockCount_ = 1;                ///< 前回の編集の後の行数(行の増減の判断)。
    mutable QList<OutlineEntry> outline_;   ///< 構成のキャッシュ。
    mutable int outlineRevision_ = -1;      ///< 構成を求めたときの文書の版。
    mutable QList<FoldRange> foldRanges_;   ///< 折りたたみの範囲のキャッシュ。
    mutable int foldRevision_ = -1;         ///< 折りたたみの範囲を求めたときの文書の版。
    QList<QTextCursor> foldedHeaders_;      ///< 畳んだ見出しの行(QTextCursorは編集に合わせて位置が動く)。
    QList<QPair<int, int>> selectionStack_; ///< 選択範囲の拡大の前の選択(アンカー, 位置)。
    QList<int> stickyLines_;                ///< 上端に残している見出しの行。
    int stickyRevision_ = -1;               ///< 見出しの固定表示を描いたときの文書の版。
    std::vector<std::unique_ptr<QTextLayout>> stickyLayouts_;  ///< 見出しの固定表示の行のレイアウト(描くたびに作らない)。
    QString stickyLayoutKey_;               ///< stickyLayouts_を作ったときの行・版・フォント。
    int activeGuideKey_[4] = {-1, -1, -1, -1};  ///< 縦線の範囲を求めたときの(版, カーソルの行, 最初の行, 最後の行)。
    int visibleRangeKey_[4] = {-1, -1, -1, -1};  ///< 印を絞る表示範囲を求めたときの(版, スクロール位置, 高さ, 幅)。折りたたみで-1に戻す。
    int visibleStart_ = 0;                  ///< 印を絞る表示範囲の最初の位置(文書の中)。
    int visibleEnd_ = 0;                    ///< 印を絞る表示範囲の最後の位置(文書の中)。
    int activeLevel_ = -1;                  ///< 明るくする縦線の段(0始まり)。無ければ-1。
    int activeTop_ = 0;                     ///< 明るくする範囲の最初の行。
    int activeBottom_ = 0;                  ///< 明るくする範囲の最後の行。
    bool markersDirty_ = true;              ///< スクロールバーの印の元(差分・検索・同じ名前・問題)が変わったか。
    bool decorationsDirty_ = false;         ///< 本文に重ねる印を、本文の変更の後で渡し直す必要があるか。
    bool foldsDirty_ = false;               ///< 畳んだ範囲を、本文の変更の後で合わせ直す必要があるか。
    int editedStart_ = -1;                  ///< まだ波線を消していない編集の範囲の先頭。無ければ-1。
    int editedEnd_ = -1;                    ///< まだ波線を消していない編集の範囲の終わり。無ければ-1。
    int completionStart_ = -1;              ///< 補完の一覧を出したときの、補完中の名前の先頭の位置。
    bool completionPopupReady_ = false;     ///< 補完の一覧の部品を作って整えたか。
    int lastCursorBlock_ = 0;               ///< 前回のカーソルの行(畳んだ範囲を飛び越える向きの判断)。
    bool expanding_ = false;                ///< 選択範囲の拡大で選択を変えている最中か。
    QPair<int, int> lastExpanded_{-1, -1};  ///< 最後に広げた選択範囲(先頭, 終わり)。
    MarkerScrollBar* markers_ = nullptr;    ///< 印を描くスクロールバー。所有者はこの欄。
    StickyHeader* sticky_ = nullptr;        ///< 見出しの固定表示。所有者は表示部分(viewport)。
    HoverPopup* signature_ = nullptr;       ///< 引数のヒント。初めて使うときに作る。所有者はこの欄。
    HoverPopup* completionDetail_ = nullptr;  ///< 補完の候補の説明。所有者はこの欄。
    HoverPopup* peek_ = nullptr;            ///< 定義をその場で見る表示。所有者はこの欄。
    HoverPopup* problemPopup_ = nullptr;    ///< F8で出す問題の説明(マウスの位置では閉じない)。所有者はこの欄。
    QTimer wordTimer_;                      ///< カーソルが止まって0.15秒後に同じ名前を強調する。
    QTimer hoverTimer_;                     ///< マウスが止まって0.3秒後に名前の説明を出す。
    QPoint hoverPoint_;                     ///< 最後にマウスが動いた位置(表示部分の座標)。
    QTimer diffTimer_;                      ///< 入力が止まって0.3秒後に差分を求め直す。
    QTimer markerTimer_;                    ///< スクロールバーの印をまとめて描き直す。
    QTimer stickyTimer_;                    ///< 入力が止まって0.1秒後に見出しの固定表示を求め直す(入力のたびに構成を作らない)。
    QTimer afterEditTimer_;                 ///< 本文の変更の後、イベントループへ戻ってからapplyEditFollowUpsを呼ぶ(0ms)。
};

}  // namespace hedit
