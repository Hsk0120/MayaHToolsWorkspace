/** @file code_editor.cpp
 * @brief CodeEditorの実装。
 */
#include "editor/code_editor.h"
#include "core/script_lexer.h"
#include "editor/edit_commands.h"
#include "editor/hover_popup.h"
#include "editor/spelling.h"
#include "editor/syntax_highlighter.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QAbstractItemView>
#include <QCompleter>
#include <QElapsedTimer>
#include <QHelpEvent>
#include <QMouseEvent>
#include <QScrollBar>
#include <QFileInfo>
#include <QKeyEvent>
#include <QRegularExpression>
#include <QStandardItemModel>
#include <QTextBlock>

namespace hedit {

CodeEditor::CodeEditor(QWidget* parent) : NumberedTextEdit(parent) {
    setObjectName("codeEditor");
    // ポイント指定の文字サイズはMayaの拡大率が効かない(Qtの高DPI拡大が無効のため)。
    // ピクセルで指定して拡大率を掛ける。
    QFont codeFont("Consolas");
    codeFont.setPixelSize(scaled(14));
    setFont(codeFont);
    setLineWrapMode(NoWrap);
    setTabStopDistance(fontMetrics().horizontalAdvance(' ') * 4);
    setProperty("language", languageName(language_));

    // 色分けは文書の子として作る(文書と一緒に破棄される)。
    highlighter_ = new SyntaxHighlighter(document());

    // 補完の一覧。QCompleterはこの欄の子なので、この欄と一緒に破棄される。
    completer_ = new QCompleter(this);
    completer_->setModel(new QStandardItemModel(completer_));
    completer_->setWidget(this);
    completer_->setCaseSensitivity(Qt::CaseSensitive);
    completer_->setCompletionMode(QCompleter::PopupCompletion);
    completer_->popup()->setFont(codeFont);
    // %1〜%7は、後ろの.arg()で順番に置き換わる。
    completer_->popup()->setStyleSheet(
        QString("QAbstractItemView{background:%1;color:%2;border:%3px solid %4;"
                "selection-background-color:%5;selection-color:%6;padding:%7px;}")
            .arg(QString(theme::kPopupBackground))
            .arg(QString(theme::kText))
            .arg(scaled(1))
            .arg(QString(theme::kPopupBorder))
            .arg(QString(theme::kPopupSelection))
            .arg(QString(theme::kPopupSelectedText))
            .arg(scaled(3)));
    // 一覧で候補が選ばれたら本文へ入れる。
    connect(completer_, QOverload<const QString&>::of(&QCompleter::activated), this,
            [this](const QString& value) { insertCompletion(value); });

    connect(this, &QPlainTextEdit::cursorPositionChanged, this, [this] { updateDecorations(); });

    // 名前の説明(ホバー): マウスの移動を受け取り、名前から離れたら閉じる。スクロールでも閉じる。
    viewport()->setMouseTracking(true);
    connect(verticalScrollBar(), &QScrollBar::valueChanged, this, [this] { hideHover(); });
    connect(horizontalScrollBar(), &QScrollBar::valueChanged, this, [this] { hideHover(); });
}

bool CodeEditor::nameAt(int position, int* start, int* end) const {
    const QTextBlock block = document()->findBlock(position);
    if (!block.isValid()) {
        return false;
    }
    const QString line = block.text();
    const int column = position - block.position();
    // 行をまたぐ文字列の途中かは、色分けが行ごとに保存している状態(前の行の終わり)で分かる。
    const int state = qMax(0, block.previous().isValid() ? block.previous().userState() : 0);
    for (const Token& token : tokenizeLine(line, ScriptLanguage::Python, state, nullptr)) {
        if (column < token.start || column > token.start + token.length) {
            continue;
        }
        const QString text = line.mid(token.start, token.length);
        if (token.type != TokenType::Name || isKeyword(text, ScriptLanguage::Python)) {
            return false;
        }
        *start = block.position() + token.start;
        *end = *start + token.length;
        return true;
    }
    return false;
}

void CodeEditor::showHover(int start, int end) {
    const HoverInfo info = onHoverRequested ? onHoverRequested(end) : HoverInfo();
    if (info.isEmpty()) {
        hideHover();
        return;
    }
    if (!hover_) {
        hover_ = new HoverPopup(this);
    }
    // 名前の範囲を画面全体の座標にする(小窓はその上に出す)。
    QTextCursor cursor(document());
    cursor.setPosition(start);
    const QRect first = cursorRect(cursor);
    cursor.setPosition(end);
    const QRect last = cursorRect(cursor);
    const QRect local(first.topLeft(), QPoint(last.right(), qMax(first.bottom(), last.bottom())));
    const QRect anchor(viewport()->mapToGlobal(local.topLeft()), local.size());
    hover_->showInfo(info, anchor, font());
}

void CodeEditor::showHoverAtCursor() {
    int start = 0;
    int end = 0;
    if (!isMel() && nameAt(textCursor().position(), &start, &end)) {
        showHover(start, end);
    }
}

void CodeEditor::hideHover() {
    if (hover_) {
        hover_->cancelHide();
        hover_->hide();
    }
}

bool CodeEditor::viewportEvent(QEvent* event) {
    if (event->type() == QEvent::ToolTip && !isMel() && onHoverRequested) {
        // マウスが少し止まった: その位置が名前の上なら説明を出す。
        auto help = static_cast<QHelpEvent*>(event);
        const QTextCursor cursor = cursorForPosition(help->pos());
        int start = 0;
        int end = 0;
        // cursorForPositionは行末より右や最後の行より下でも近い文字の位置を返すので、文字の上にあるかを確かめる。
        const QRect rect = cursorRect(cursor);
        const bool onText = qAbs(help->pos().x() - rect.center().x()) <= fontMetrics().averageCharWidth() * 2
                            && help->pos().y() >= rect.top() && help->pos().y() <= rect.bottom();
        if (onText && nameAt(cursor.position(), &start, &end)) {
            // 同じ名前の説明を出している間は、問い合わせ直さない。
            const QPoint global = viewport()->mapToGlobal(help->pos());
            if (!hover_ || !hover_->anchor().contains(global)) {
                showHover(start, end);
            }
        } else {
            hideHover();
        }
        return true;
    }
    if (hover_ && hover_->isVisible()) {
        if (event->type() == QEvent::MouseMove) {
            // 名前の上にいる間は開いたまま、離れたら少し待って閉じる(小窓へ移れるように)。
            auto mouse = static_cast<QMouseEvent*>(event);
            const QPoint global = viewport()->mapToGlobal(mouse->pos());
            if (hover_->anchor().contains(global)) {
                hover_->cancelHide();
            } else {
                hover_->scheduleHide();
            }
        } else if (event->type() == QEvent::Leave) {
            hover_->scheduleHide();
        } else if (event->type() == QEvent::MouseButtonPress || event->type() == QEvent::Wheel) {
            hideHover();
        }
    }
    return NumberedTextEdit::viewportEvent(event);
}

void CodeEditor::focusOutEvent(QFocusEvent* event) {
    // 小窓自体はフォーカスを取らないので、別の部品へ移ったときだけ閉じる。
    hideHover();
    NumberedTextEdit::focusOutEvent(event);
}

void CodeEditor::setLanguage(ScriptLanguage language) {
    language_ = language;
    // テストやPySideから参照できるよう、保存名(python/mel)を動的プロパティにも入れる。
    setProperty("language", languageName(language_));
    highlighter_->setMel(isMel());
    highlighter_->rehighlight();
    hideCompletions();
}

void CodeEditor::setFilePath(const QString& path) {
    setProperty("path", path);
}

QString CodeEditor::displayName() const {
    const QString path = filePath();
    if (!path.isEmpty()) {
        return QFileInfo(path).fileName();
    }
    return isMel() ? "Untitled.mel" : "Untitled.py";
}

void CodeEditor::setWhitespaceVisible(bool visible) {
    QTextOption option = document()->defaultTextOption();
    if (visible) {
        option.setFlags(option.flags() | QTextOption::ShowTabsAndSpaces);
    } else {
        option.setFlags(option.flags() & ~QTextOption::ShowTabsAndSpaces);
    }
    document()->setDefaultTextOption(option);
}

QString CodeEditor::completionPrefix() const {
    QTextCursor cursor = textCursor();
    cursor.movePosition(QTextCursor::StartOfBlock, QTextCursor::KeepAnchor);
    static const QRegularExpression trailingName("[A-Za-z_0-9]*$");
    return trailingName.match(cursor.selectedText()).captured();
}

void CodeEditor::showCompletions(const QList<CompletionItem>& items) {
    auto model = static_cast<QStandardItemModel*>(completer_->model());
    model->clear();
    for (const CompletionItem& item : items) {
        // appendRowに渡した項目は、モデルが所有する。
        auto row = new QStandardItem(item.name);
        row->setToolTip(item.detail);
        model->appendRow(row);
    }
    if (model->rowCount() == 0) {
        hideCompletions();
        return;
    }
    completer_->setCompletionPrefix(completionPrefix());
    completer_->popup()->setCurrentIndex(completer_->completionModel()->index(0, 0));
    // カーソルの位置に、幅380px(100%時)の一覧を出す。
    QRect rect = cursorRect();
    rect.setWidth(scaled(380));
    completer_->complete(rect);
}

void CodeEditor::hideCompletions() {
    completer_->popup()->hide();
}

void CodeEditor::insertCompletion(const QString& value) {
    insertingCompletion_ = true;
    QTextCursor cursor = textCursor();
    // 入力途中の名前を選択して、選んだ名前で置き換える。
    cursor.movePosition(QTextCursor::Left, QTextCursor::KeepAnchor, completionPrefix().size());
    cursor.insertText(value);
    setTextCursor(cursor);
    insertingCompletion_ = false;
    hideCompletions();
}

void CodeEditor::checkSpelling(Spelling& spelling) {
    spellingMarks_.clear();
    // 表示中の行だけ(最大8,000文字)を集める。全文は調べない。
    QTextBlock block = firstVisibleBlock();
    const int base = block.position();
    QString visibleText;
    while (block.isValid() && visibleText.size() < 8000) {
        const qreal top = blockBoundingGeometry(block).translated(contentOffset()).top();
        if (top >= viewport()->height()) {
            break;
        }
        visibleText += block.text() + '\n';
        block = block.next();
    }

    QElapsedTimer elapsed;
    elapsed.start();
    for (const auto& range : spelling.check(visibleText)) {
        QTextEdit::ExtraSelection mark;
        mark.cursor = QTextCursor(document());
        mark.cursor.setPosition(base + range.first);
        mark.cursor.setPosition(base + range.first + range.second, QTextCursor::KeepAnchor);
        mark.format.setUnderlineStyle(QTextCharFormat::WaveUnderline);
        mark.format.setUnderlineColor(QColor(theme::kSpellingUnderline));
        mark.format.setToolTip("Unknown English word");
        spellingMarks_.append(mark);
    }
    // テストが所要時間と辞書の有無を確かめられるよう、プロパティに残す。
    setProperty("spellCheckMilliseconds", elapsed.elapsed());
    setProperty("spellCheckAvailable", spelling.available());
    updateDecorations();
}

void CodeEditor::clearSpelling() {
    spellingMarks_.clear();
    updateDecorations();
}

void CodeEditor::setSearchHighlights(const QList<TextMatch>& matches) {
    searchMarks_.clear();
    for (const TextMatch& match : matches) {
        QTextEdit::ExtraSelection mark;
        mark.cursor = QTextCursor(document());
        mark.cursor.setPosition(match.start);
        mark.cursor.setPosition(match.start + match.length, QTextCursor::KeepAnchor);
        mark.format.setBackground(QColor(theme::kSearchMatch));
        searchMarks_.append(mark);
    }
    updateDecorations();
}

void CodeEditor::clearSearchHighlights() {
    if (searchMarks_.isEmpty()) {
        return;
    }
    searchMarks_.clear();
    updateDecorations();
}

void CodeEditor::updateDecorations() {
    // ExtraSelectionは、本文を変えずに色や波線を重ねて表示する仕組み。
    QTextEdit::ExtraSelection currentLine;
    currentLine.format.setBackground(QColor(theme::kCurrentLine));
    currentLine.format.setProperty(QTextFormat::FullWidthSelection, true);
    currentLine.cursor = textCursor();
    currentLine.cursor.clearSelection();
    // 後ろのものほど上に重なる: カーソル行 → 検索の一致 → スペルの波線。
    QList<QTextEdit::ExtraSelection> selections;
    selections.append(currentLine);
    selections.append(searchMarks_);
    selections.append(spellingMarks_);
    setExtraSelections(selections);
}

bool CodeEditor::isRunKey(const QKeyEvent* event) {
    // テンキーのEnterはKeypadModifierが付くので、それを除いて比べる。
    const Qt::KeyboardModifiers modifiers = event->modifiers() & ~Qt::KeypadModifier;
    const bool enterKey = event->key() == Qt::Key_Return || event->key() == Qt::Key_Enter;
    const bool ctrlEnter = enterKey && modifiers == Qt::ControlModifier;
    const bool keypadEnter = event->key() == Qt::Key_Enter && modifiers == Qt::NoModifier;
    return ctrlEnter || keypadEnter;
}

bool CodeEditor::event(QEvent* event) {
    // ShortcutOverrideをacceptすると、Mayaやメニューのショートカットより先に、
    // このキーをkeyPressEventで受け取れる。
    if (event->type() == QEvent::ShortcutOverride) {
        auto key = static_cast<QKeyEvent*>(event);
        const bool handledHere = isRunKey(key)
                                 || editCommandForKey(key, textCursor().hasSelection()) != EditCommand::None;
        if (handledHere) {
            event->accept();
            return true;
        }
    }
    return NumberedTextEdit::event(event);
}

void CodeEditor::keyPressEvent(QKeyEvent* event) {
    // 0. 名前の説明を出している間のキー入力: Escは閉じるだけ、それ以外は閉じてから通常どおり処理する。
    if (hover_ && hover_->isVisible()) {
        hideHover();
        if (event->key() == Qt::Key_Escape && event->modifiers() == Qt::NoModifier) {
            event->accept();
            return;
        }
    }

    // 1. 実行キー(Ctrl+Enter)。
    if (isRunKey(event)) {
        hideCompletions();
        if (onRunRequested) {
            onRunRequested();
        }
        event->accept();
        return;
    }

    // 2. 補完の一覧が開いているときのEnter・Tab・Escは、一覧(QCompleter)に任せる。
    //    ignore()すると、キーは一覧の側で処理される。
    if (completer_->popup()->isVisible()) {
        switch (event->key()) {
        case Qt::Key_Enter:
        case Qt::Key_Return:
        case Qt::Key_Escape:
        case Qt::Key_Tab:
            event->ignore();
            return;
        default:
            break;
        }
    }

    // 3. VS Code風の編集ショートカット。
    const EditCommand command = editCommandForKey(event, textCursor().hasSelection());
    if (command == EditCommand::CloseTab) {
        if (onCloseRequested) {
            onCloseRequested();
        }
        event->accept();
        return;
    }
    if (command == EditCommand::Redo) {
        redo();
        event->accept();
        return;
    }
    if (command == EditCommand::ToggleWrap) {
        setLineWrapMode(lineWrapMode() == NoWrap ? WidgetWidth : NoWrap);
        event->accept();
        return;
    }
    if (command != EditCommand::None) {
        applyLineCommand(this, command, isMel() ? "//" : "#");
        event->accept();
        return;
    }

    // 4. Ctrl+Spaceで補完を求める。
    if (event->key() == Qt::Key_Space && event->modifiers() == Qt::ControlModifier) {
        if (onCompletionRequested) {
            onCompletionRequested();
        }
        return;
    }

    // 5. 選択なしのTabは空白4文字。
    if (event->key() == Qt::Key_Tab && event->modifiers() == Qt::NoModifier) {
        insertPlainText("    ");
        return;
    }

    // 6. 行頭の空白でのBackspace。
    if (event->key() == Qt::Key_Backspace && event->modifiers() == Qt::NoModifier && deleteToIndentStop()) {
        return;
    }

    // 7. Enterでインデントを引き継ぐ。
    if (event->key() == Qt::Key_Return && event->modifiers() == Qt::NoModifier) {
        insertNewlineWithIndent();
        return;
    }

    // 8. それ以外は普通の文字入力。
    QPlainTextEdit::keyPressEvent(event);
}

bool CodeEditor::deleteToIndentStop() {
    if (!backspaceToIndentStop_ || textCursor().hasSelection()) {
        return false;
    }
    QTextCursor cursor = textCursor();
    const QString before = cursor.block().text().left(cursor.positionInBlock());
    const bool onlySpaces = !before.isEmpty() && before == QString(before.size(), ' ');
    if (!onlySpaces) {
        return false;
    }
    // 例: 空白6文字なら2文字、8文字なら4文字消して、4の倍数の位置へ戻る。
    const int count = (before.size() - 1) % 4 + 1;
    cursor.beginEditBlock();
    for (int i = 0; i < count; ++i) {
        cursor.deletePreviousChar();
    }
    cursor.endEditBlock();
    setTextCursor(cursor);
    return true;
}

void CodeEditor::insertNewlineWithIndent() {
    if (!smartIndent_) {
        insertPlainText("\n");
        return;
    }
    QTextCursor cursor = textCursor();
    cursor.movePosition(QTextCursor::StartOfBlock, QTextCursor::KeepAnchor);
    const QString before = cursor.selectedText();
    static const QRegularExpression leadingSpaces("^ *");
    QString indent = leadingSpaces.match(before).captured();
    // Pythonは「:」、MELは「{」で終わる行の次を1段深くする。
    const QChar blockOpener = isMel() ? '{' : ':';
    if (before.trimmed().endsWith(blockOpener)) {
        indent += "    ";
    }
    insertPlainText("\n" + indent);
}

}  // namespace hedit
