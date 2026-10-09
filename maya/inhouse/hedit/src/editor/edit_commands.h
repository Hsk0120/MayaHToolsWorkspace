/** @file edit_commands.h
 * @brief VS Code風の行編集(コメント切り替え・インデント・行の移動や複製など)。
 * @details キー入力から操作を選ぶ関数と、操作を本文へ適用する関数に分けてある。
 * どちらもMayaに依存せず、QPlainTextEditだけで動くのでテストしやすい。
 */
#pragma once
#include <QString>

class QKeyEvent;
class QPlainTextEdit;

namespace hedit {

/** @brief コード欄のショートカットで行う編集操作。 */
enum class EditCommand {
    None,           ///< 対象外のキー。Qt標準の入力処理へ渡す。
    ToggleComment,  ///< Ctrl+/ : 選択行/現在行のコメント切り替え。
    Indent,         ///< Ctrl+] や 選択中のTab : 空白4文字のインデント。
    Outdent,        ///< Ctrl+[ や Shift+Tab : インデント解除。
    MoveUp,         ///< Alt+↑ : 行を上へ移動。
    MoveDown,       ///< Alt+↓ : 行を下へ移動。
    CopyUp,         ///< Shift+Alt+↑ : 行を上へ複製。
    CopyDown,       ///< Shift+Alt+↓ : 行を下へ複製。
    DeleteLines,    ///< Ctrl+Shift+K : 行を削除。
    SelectLine,     ///< Ctrl+L : 現在行を選択。繰り返すと次の行まで広げる。
    CopyLine,       ///< 選択なしのCtrl+C : 現在行をコピー。
    CutLine,        ///< 選択なしのCtrl+X : 現在行を切り取り。
    Redo,           ///< Ctrl+Shift+Z : テキストのやり直し。
    ToggleWrap,     ///< Alt+Z : 折り返し表示の切り替え。
    CloseTab,       ///< Ctrl+W / Ctrl+F4 : 現在のタブを閉じる。
    ExpandSelection,  ///< Shift+Alt+→ : 選択範囲を意味のまとまりへ広げる(CodeEditorが扱う)。
    ShrinkSelection,  ///< Shift+Alt+← : 広げる前の選択範囲へ戻す(CodeEditorが扱う)。
};

/// 選択なしのCtrl+C・Ctrl+Xでコピーした「行全体」の印(クリップボードの形式)。この印のある文字列は、
/// 貼り付けのときにカーソルの位置ではなく、カーソルの行の上へ行として入れる(VS Codeと同じ)。
constexpr const char* kWholeLineMimeType = "application/x-hedit-whole-line";

/** @brief 行全体をクリップボードへ入れる(行として貼り付ける印を付ける)。 @param line 行(末尾の改行を含む)。 */
void copyWholeLine(const QString& line);

/** @brief キー入力から編集操作を選ぶ。
 * @param event キーと修飾キー(Ctrl・Alt・Shift)の情報。
 * @param hasSelection 選択範囲があるか(Ctrl+C・Ctrl+X・Tabの意味が変わる)。
 * @return 対応する操作。対象外ならEditCommand::None。
 */
EditCommand editCommandForKey(const QKeyEvent* event, bool hasSelection);

/** @brief 行単位の操作を本文へ適用する。1回の操作は1回のUndoで戻せる。
 * @param editor 対象のテキスト欄。
 * @param command ToggleComment〜CutLineのいずれか。それ以外(Redoなど)は何もしない。
 * @param commentMarker コメント記号(Pythonは``#``、MELは``//``)。
 */
void applyLineCommand(QPlainTextEdit* editor, EditCommand command, const QString& commentMarker);

}  // namespace hedit
