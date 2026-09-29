/** @file code_editor.h
 * @brief 1つのタブのコード欄。入力のショートカット・自動インデント・補完候補・スペルの波線を担当する。
 */
#pragma once
#include "editor/numbered_text_edit.h"
#include <QList>
#include <QString>
#include <QTextEdit>
#include <functional>

class QCompleter;

namespace hedit {

class Spelling;
class SyntaxHighlighter;

/** @brief 補完候補の1件。 */
struct CompletionItem {
    QString name;    ///< 挿入する名前。
    QString detail;  ///< マウスを重ねたときに出す説明(関数の引数など)。
};

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

    // ---- 言語と保存先 ----

    /** @brief 言語を設定し、色分けを塗り直す。 @param language ``mel``以外は``python``として扱う。 */
    void setLanguage(const QString& language);
    /** @brief 言語を返す。 @return ``python``または``mel``。 */
    QString language() const { return language_; }
    /** @brief MELのタブか。 @return MELならtrue。 */
    bool isMel() const { return language_ == "mel"; }
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

    // ---- MainWindowへ任せる操作(空なら何もしない) ----

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

private:
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

    /** @brief カーソル行の背景とスペルの波線を、まとめて本文に重ねる。 */
    void updateDecorations();

    QString language_ = "python";                        ///< ``python``か``mel``。
    bool smartIndent_ = true;                            ///< Enterでインデントを引き継ぐか。
    bool backspaceToIndentStop_ = true;                  ///< Backspaceを4文字単位で消すか。
    bool insertingCompletion_ = false;                   ///< 候補の確定中か。
    SyntaxHighlighter* highlighter_;                     ///< 色分け。所有者は文書。
    QCompleter* completer_;                              ///< 補完の一覧。所有者はこの欄。
    QList<QTextEdit::ExtraSelection> spellingMarks_;     ///< スペルの波線。
};

}  // namespace hedit
