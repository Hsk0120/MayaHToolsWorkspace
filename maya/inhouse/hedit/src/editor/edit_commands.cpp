/** @file edit_commands.cpp
 * @brief 行編集の操作の実装。
 * @details QTextCursorは文書の中の位置(と選択範囲)を表す。beginEditBlock〜endEditBlockの間の変更は、
 * Ctrl+Zの1回でまとめて戻せる。位置はUTF-16の文字単位で、文書の先頭が0。
 * 「ブロック」はQtの用語で、1行(改行で区切られた段落)のこと。
 */
#include "editor/edit_commands.h"
#include <QApplication>
#include <QClipboard>
#include <QKeyEvent>
#include <QPlainTextEdit>
#include <QStringList>
#include <QTextBlock>

namespace hedit {
namespace {

/** @brief 選択範囲が触れる行の範囲。0始まりの行番号。 */
struct LineRange {
    int first = 0;  ///< 先頭の行。
    int last = 0;   ///< 末尾の行。
};

/** @brief 操作の対象になる行を求める。
 * @param editor 対象のテキスト欄。
 * @return 選択が触れる行。選択なしなら現在行だけ。
 * @note 選択の末尾が次の行の先頭ちょうどなら、その行は含めない(行を選択したときの見た目に合わせる)。
 */
LineRange selectedLines(const QPlainTextEdit* editor) {
    const QTextCursor cursor = editor->textCursor();
    const QTextDocument* document = editor->document();
    int end = cursor.selectionEnd();
    if (cursor.hasSelection() && end > 0 && document->findBlock(end).position() == end) {
        --end;
    }
    LineRange range;
    range.first = document->findBlock(cursor.selectionStart()).blockNumber();
    range.last = document->findBlock(end).blockNumber();
    return range;
}

/** @brief 文書の[start, end)を文字列で置き換える。1回のUndoで戻せる。
 * @param cursor 置き換えに使うカーソル。呼出後は置き換えた文字列の末尾にある。
 * @param start 置き換える範囲の先頭。
 * @param end 置き換える範囲の末尾(この位置の文字は含まない)。
 * @param text 新しい文字列。
 */
void replaceRange(QTextCursor& cursor, int start, int end, const QString& text) {
    cursor.beginEditBlock();
    cursor.setPosition(start);
    cursor.setPosition(end, QTextCursor::KeepAnchor);
    cursor.insertText(text);
    cursor.endEditBlock();
}

/** @brief Ctrl+L。現在行を選択し、選択中なら次の行まで選択を広げる。
 * @param editor 対象のテキスト欄。
 * @param range 対象の行。
 */
void selectLine(QPlainTextEdit* editor, LineRange range) {
    QTextDocument* document = editor->document();
    const QTextBlock startBlock = document->findBlockByNumber(range.first);
    const QTextBlock endBlock = document->findBlockByNumber(range.last);
    const int start = startBlock.position();
    const int end = endBlock.position() + endBlock.text().size();
    int target = end + 1;  // 改行の後ろまで選ぶ。
    const QTextBlock nextBlock = endBlock.next();
    if (editor->textCursor().hasSelection() && nextBlock.isValid()) {
        target = nextBlock.position() + nextBlock.length();
    }
    QTextCursor cursor = editor->textCursor();
    cursor.setPosition(start);
    // 文書の末尾(characterCount()-1)を超えないようにする。
    cursor.setPosition(qMin(target, document->characterCount() - 1), QTextCursor::KeepAnchor);
    editor->setTextCursor(cursor);
}

/** @brief Ctrl+Shift+K、または選択なしのCtrl+X。行を削除する(Ctrl+Xはクリップボードへも入れる)。
 * @param editor 対象のテキスト欄。
 * @param range 対象の行。
 * @param copyToClipboard trueなら削除前に先頭の行をクリップボードへ入れる。
 */
void deleteLines(QPlainTextEdit* editor, LineRange range, bool copyToClipboard) {
    QTextDocument* document = editor->document();
    const QTextBlock startBlock = document->findBlockByNumber(range.first);
    const QTextBlock endBlock = document->findBlockByNumber(range.last);
    if (copyToClipboard) {
        QApplication::clipboard()->setText(startBlock.text() + "\n");
    }
    int start = startBlock.position();
    int end = endBlock.position() + endBlock.text().size();
    // 行の後ろの改行も消す。最後の行なら、代わりに前の行の改行を消す。
    if (endBlock.next().isValid()) {
        ++end;
    } else if (start > 0) {
        --start;
    }
    QTextCursor cursor = editor->textCursor();
    cursor.beginEditBlock();
    cursor.setPosition(start);
    cursor.setPosition(end, QTextCursor::KeepAnchor);
    cursor.removeSelectedText();
    cursor.endEditBlock();
    editor->setTextCursor(cursor);
}

/** @brief Alt+↑↓(移動)とShift+Alt+↑↓(複製)。
 * @param editor 対象のテキスト欄。
 * @param range 対象の行。
 * @param command MoveUp・MoveDown・CopyUp・CopyDownのいずれか。
 * @details 対象の行と隣の行をまとめて置き換える。移動・複製の後も、同じ列と選択を保つ。
 */
void moveOrCopyLines(QPlainTextEdit* editor, LineRange range, EditCommand command) {
    QTextDocument* document = editor->document();
    const QTextBlock startBlock = document->findBlockByNumber(range.first);
    const QTextBlock endBlock = document->findBlockByNumber(range.last);
    const bool hadSelection = editor->textCursor().hasSelection();
    const int column = editor->textCursor().positionInBlock();

    QStringList lines;
    for (int number = range.first; number <= range.last; ++number) {
        lines.append(document->findBlockByNumber(number).text());
    }
    int start = startBlock.position();
    int end = endBlock.position() + endBlock.text().size();
    QStringList replacement = lines;
    int newFirst = range.first;  // 操作後に、対象の行が始まる行番号。

    if (command == EditCommand::MoveUp) {
        if (range.first == 0) {
            return;  // 先頭の行はそれ以上上へ動かせない。
        }
        // 1つ上の行を対象の行の後ろへ回す。
        const QTextBlock above = startBlock.previous();
        start = above.position();
        replacement.append(above.text());
        --newFirst;
    } else if (command == EditCommand::MoveDown) {
        const QTextBlock below = endBlock.next();
        if (!below.isValid()) {
            return;  // 末尾の行はそれ以上下へ動かせない。
        }
        // 1つ下の行を対象の行の前へ回す。
        end = below.position() + below.text().size();
        replacement.prepend(below.text());
        ++newFirst;
    } else {
        // 複製: 対象の行を2回並べる。下へ複製したときは、カーソルを下の組へ移す。
        replacement.append(lines);
        if (command == EditCommand::CopyDown) {
            newFirst += lines.size();
        }
    }

    QTextCursor cursor = editor->textCursor();
    replaceRange(cursor, start, end, replacement.join("\n"));

    const QTextBlock target = document->findBlockByNumber(newFirst);
    cursor.setPosition(target.position() + qMin(column, int(target.text().size())));
    if (hadSelection) {
        const QTextBlock tail = document->findBlockByNumber(newFirst + lines.size() - 1);
        cursor.setPosition(target.position());
        cursor.setPosition(tail.position() + tail.text().size(), QTextCursor::KeepAnchor);
    }
    editor->setTextCursor(cursor);
}

/** @brief 行の先頭の空白の数を数える。
 * @param line 1行の文字列。
 * @return 先頭から続く空白(タブを含む)の文字数。
 */
int leadingWhitespace(const QString& line) {
    int count = 0;
    while (count < line.size() && line[count].isSpace()) {
        ++count;
    }
    return count;
}

/** @brief 1行のインデントを解除する。
 * @param line 対象の行。書き換える。
 * @return 取り除いた文字数。
 */
int outdentLine(QString& line) {
    int count = 0;
    if (line.startsWith('\t')) {
        count = 1;
    } else {
        while (count < 4 && count < line.size() && line[count] == ' ') {
            ++count;
        }
    }
    line.remove(0, count);
    return count;
}

/** @brief Ctrl+/(コメント)・インデント・インデント解除。
 * @param editor 対象のテキスト欄。
 * @param range 対象の行。
 * @param command ToggleComment・Indent・Outdentのいずれか。
 * @param marker コメント記号。
 * @details 空行以外が全てコメントならコメントを外し、そうでなければ付ける(VS Codeと同じ)。
 * 選択がなければ、カーソルの列を文字の増減に合わせてずらす。
 */
void indentOrComment(QPlainTextEdit* editor, LineRange range, EditCommand command, const QString& marker) {
    QTextDocument* document = editor->document();
    const QTextBlock startBlock = document->findBlockByNumber(range.first);
    const QTextBlock endBlock = document->findBlockByNumber(range.last);
    const bool hadSelection = editor->textCursor().hasSelection();
    const int column = editor->textCursor().positionInBlock();
    const int start = startBlock.position();
    const int end = endBlock.position() + endBlock.text().size();

    QStringList lines;
    for (int number = range.first; number <= range.last; ++number) {
        lines.append(document->findBlockByNumber(number).text());
    }
    bool uncomment = true;
    for (const QString& line : lines) {
        const QString trimmed = line.trimmed();
        if (!trimmed.isEmpty() && !trimmed.startsWith(marker)) {
            uncomment = false;
        }
    }

    int firstLineColumnDelta = 0;  // 先頭の行で、カーソルより前に増減した文字数。
    for (int i = 0; i < lines.size(); ++i) {
        QString& line = lines[i];
        int delta = 0;
        if (command == EditCommand::Indent) {
            line.prepend("    ");
            delta = 4;
        } else if (command == EditCommand::Outdent) {
            delta = -outdentLine(line);
        } else if (command == EditCommand::ToggleComment && !line.trimmed().isEmpty()) {
            const int position = leadingWhitespace(line);
            if (uncomment) {
                // "# " のように記号の後ろの空白1つも一緒に外す。
                int count = marker.size();
                if (position + count < line.size() && line[position + count] == ' ') {
                    ++count;
                }
                line.remove(position, count);
                if (column > position) {
                    delta = -count;
                }
            } else {
                line.insert(position, marker + " ");
                if (column >= position) {
                    delta = marker.size() + 1;
                }
            }
        }
        if (i == 0) {
            firstLineColumnDelta = delta;
        }
    }

    const QString newText = lines.join("\n");
    QTextCursor cursor = editor->textCursor();
    replaceRange(cursor, start, end, newText);
    if (hadSelection) {
        cursor.setPosition(start);
        cursor.setPosition(start + newText.size(), QTextCursor::KeepAnchor);
    } else {
        cursor.setPosition(start + qBound(0, column + firstLineColumnDelta, int(lines[0].size())));
    }
    editor->setTextCursor(cursor);
}

}  // namespace

EditCommand editCommandForKey(const QKeyEvent* event, bool hasSelection) {
    const Qt::KeyboardModifiers modifiers = event->modifiers();
    const int key = event->key();

    if (modifiers == Qt::ControlModifier) {
        if (key == Qt::Key_W || key == Qt::Key_F4) return EditCommand::CloseTab;
        if (key == Qt::Key_Slash) return EditCommand::ToggleComment;
        if (key == Qt::Key_BracketRight) return EditCommand::Indent;
        if (key == Qt::Key_BracketLeft) return EditCommand::Outdent;
        if (key == Qt::Key_L) return EditCommand::SelectLine;
        // 選択があるときのCtrl+C/Xは、Qt標準のコピー/切り取りに任せる。
        if (!hasSelection && key == Qt::Key_C) return EditCommand::CopyLine;
        if (!hasSelection && key == Qt::Key_X) return EditCommand::CutLine;
    }
    if (modifiers == (Qt::ControlModifier | Qt::ShiftModifier)) {
        if (key == Qt::Key_K) return EditCommand::DeleteLines;
        if (key == Qt::Key_Z) return EditCommand::Redo;
    }
    if (modifiers == Qt::AltModifier) {
        if (key == Qt::Key_Up) return EditCommand::MoveUp;
        if (key == Qt::Key_Down) return EditCommand::MoveDown;
        if (key == Qt::Key_Z) return EditCommand::ToggleWrap;
    }
    if (modifiers == (Qt::AltModifier | Qt::ShiftModifier)) {
        if (key == Qt::Key_Up) return EditCommand::CopyUp;
        if (key == Qt::Key_Down) return EditCommand::CopyDown;
        if (key == Qt::Key_Right) return EditCommand::ExpandSelection;
        if (key == Qt::Key_Left) return EditCommand::ShrinkSelection;
    }
    // Shift+TabはQtではKey_Backtabとして届くことがある。
    if ((key == Qt::Key_Backtab || key == Qt::Key_Tab) && modifiers == Qt::ShiftModifier) return EditCommand::Outdent;
    if (key == Qt::Key_Tab && modifiers == Qt::NoModifier && hasSelection) return EditCommand::Indent;
    return EditCommand::None;
}

void applyLineCommand(QPlainTextEdit* editor, EditCommand command, const QString& commentMarker) {
    const LineRange range = selectedLines(editor);
    switch (command) {
    case EditCommand::SelectLine:
        selectLine(editor, range);
        break;
    case EditCommand::CopyLine:
        QApplication::clipboard()->setText(editor->document()->findBlockByNumber(range.first).text() + "\n");
        break;
    case EditCommand::CutLine:
        deleteLines(editor, range, true);
        break;
    case EditCommand::DeleteLines:
        deleteLines(editor, range, false);
        break;
    case EditCommand::MoveUp:
    case EditCommand::MoveDown:
    case EditCommand::CopyUp:
    case EditCommand::CopyDown:
        moveOrCopyLines(editor, range, command);
        break;
    case EditCommand::ToggleComment:
    case EditCommand::Indent:
    case EditCommand::Outdent:
        indentOrComment(editor, range, command, commentMarker);
        break;
    default:
        // Redo・ToggleWrap・CloseTabは行の操作ではない(CodeEditorが扱う)。
        break;
    }
}

}  // namespace hedit
