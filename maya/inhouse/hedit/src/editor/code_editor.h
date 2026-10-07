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
#include "editor/numbered_text_edit.h"
#include <QList>
#include <QPair>
#include <QString>
#include <QTextCursor>
#include <QTextEdit>
#include <QTimer>
#include <QVector>
#include <functional>

class QCompleter;

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
    /** @brief 候補を一覧で表示する。 @param items 表示する候補。空なら一覧を閉じる。 */
    void showCompletions(const QList<CompletionItem>& items);
    /** @brief 候補の一覧を閉じる。 */
    void hideCompletions();
    /** @brief 候補の確定で本文を変更している最中か。
     * @return trueの間の本文変更は、利用者の入力として扱わない(次の補完を予約しない)。
     */
    bool isInsertingCompletion() const { return insertingCompletion_; }

    // ---- スペルチェック ----

    /** @brief 表示中の範囲だけを調べ、知らない英単語に波線を付ける。 @param spelling Windowsの辞書。 */
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

    /** @brief 問題を波線で示す(エラーは赤、警告は黄色)。 @param diagnostics 問題。行は1始まり。 */
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
    /** @brief スクロールバーの印を、すぐ描き直す。 */
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

    std::function<void()> onCompletionRequested;  ///< Ctrl+Spaceが押された。
    std::function<void()> onRunRequested;         ///< Ctrl+EnterかテンキーのEnterが押された。
    std::function<void()> onCloseRequested;       ///< Ctrl+WかCtrl+F4が押された。

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

    /** @brief 本文を描いた後に、インデントの縦線と、畳んだ見出しの「⋯」を重ねる。 @param event 描き直す範囲。 */
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
     * マウスの移動から自前のタイマー(0.5秒)で呼ぶ。
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

    /** @brief 改行し、前の行のインデントを引き継ぐ(``:``や``{``で終わる行なら1段深くする)。 */
    void insertNewlineWithIndent();

    /** @brief 候補の確定。補完中の名前を、選んだ名前で置き換える。 @param value 選んだ名前。 */
    void insertCompletion(const QString& value);

    /** @brief カーソル行の背景・同じ名前・括弧・検索の一致・問題・スペルの波線を、まとめて本文に重ねる。 */
    void updateDecorations();

    ScriptLanguage language_ = ScriptLanguage::Python;   ///< 言語。
    bool smartIndent_ = true;                            ///< Enterでインデントを引き継ぐか。
    bool backspaceToIndentStop_ = true;                  ///< Backspaceを4文字単位で消すか。
    bool insertingCompletion_ = false;                   ///< 候補の確定中か。
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
    QList<Diagnostic> diagnostics_;         ///< 問題。
    QString savedText_;                     ///< 保存した内容。
    bool hasSavedText_ = false;             ///< 保存した内容があるか。
    QList<LineChange> lineChanges_;         ///< 保存した内容との違い。
    QVector<char> changeKinds_;             ///< 行ごとの変更の種類(0=なし・1=追加・2=変更)。
    QVector<char> deletedAbove_;            ///< 行の上で削除された行があれば1。
    mutable QList<OutlineEntry> outline_;   ///< 構成のキャッシュ。
    mutable int outlineRevision_ = -1;      ///< 構成を求めたときの文書の版。
    mutable QList<FoldRange> foldRanges_;   ///< 折りたたみの範囲のキャッシュ。
    mutable int foldRevision_ = -1;         ///< 折りたたみの範囲を求めたときの文書の版。
    QList<QTextCursor> foldedHeaders_;      ///< 畳んだ見出しの行(QTextCursorは編集に合わせて位置が動く)。
    QList<QPair<int, int>> selectionStack_; ///< 選択範囲の拡大の前の選択(アンカー, 位置)。
    QList<int> stickyLines_;                ///< 上端に残している見出しの行。
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
    QTimer hoverTimer_;                     ///< マウスが止まって0.5秒後に名前の説明を出す。
    QPoint hoverPoint_;                     ///< 最後にマウスが動いた位置(表示部分の座標)。
    QTimer diffTimer_;                      ///< 入力が止まって0.3秒後に差分を求め直す。
    QTimer markerTimer_;                    ///< スクロールバーの印をまとめて描き直す。
};

}  // namespace hedit
