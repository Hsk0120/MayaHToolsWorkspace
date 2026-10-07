/** @file code_editor.cpp
 * @brief CodeEditorの実装。
 */
#include "editor/code_editor.h"
#include "core/script_lexer.h"
#include "editor/code_navigation.h"
#include "editor/edit_commands.h"
#include "editor/hover_popup.h"
#include "editor/spelling.h"
#include "editor/syntax_highlighter.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QAbstractItemView>
#include <QCompleter>
#include <QElapsedTimer>
#include <QHash>
#include <QIcon>
#include <QPixmap>
#include <QHelpEvent>
#include <QMouseEvent>
#include <QScrollBar>
#include <QFileInfo>
#include <QKeyEvent>
#include <QMimeData>
#include <QRegularExpression>
#include <QPainter>
#include <QStandardItemModel>
#include <QStyledItemDelegate>
#include <QTextBlock>
#include <QTimer>

namespace hedit {
namespace {

/// 補完の候補の、名前の右に出す説明(関数の引数など)を入れる役割。
constexpr int kDetailRole = Qt::UserRole + 1;

/** @brief 補完の種類のアイコン(色付きの文字)を作る。同じ種類は作り直さない。
 * @param category CompletionItem::category。
 * @return アイコン。
 */
QIcon categoryIcon(const QString& category) {
    static QHash<QString, QIcon> cache;
    const auto cached = cache.constFind(category);
    if (cached != cache.constEnd()) {
        return *cached;
    }
    QString letter = "v";
    const char* color = theme::kSymbolVariable;
    if (category == "function") {
        letter = "f";
        color = theme::kSymbolFunction;
    } else if (category == "class") {
        letter = "C";
        color = theme::kSymbolClass;
    } else if (category == "module") {
        letter = "M";
        color = theme::kSymbolModule;
    } else if (category == "keyword") {
        letter = "k";
        color = theme::kSymbolKeyword;
    } else if (category == "builtin") {
        letter = "b";
        color = theme::kSymbolFunction;
    } else if (category == "import") {
        letter = "i";
        color = theme::kSymbolModule;
    }
    const int size = scaled(16);
    QPixmap pixmap(size, size);
    pixmap.fill(Qt::transparent);
    QPainter painter(&pixmap);
    painter.setRenderHint(QPainter::Antialiasing, true);
    painter.setPen(QPen(QColor(color), qMax(1, scaled(1))));
    painter.drawRoundedRect(QRectF(1.5, 1.5, size - 3, size - 3), scaled(3), scaled(3));
    QFont font("Consolas");
    font.setPixelSize(scaled(11));
    font.setBold(true);
    painter.setFont(font);
    painter.drawText(QRect(0, 0, size, size), Qt::AlignCenter, letter);
    painter.end();
    const QIcon icon(pixmap);
    cache.insert(category, icon);
    return icon;
}

/** @brief 補完の一覧の1行の描画。名前の右に、薄い色で説明(関数の引数など)を出す。 */
class CompletionDelegate : public QStyledItemDelegate {
public:
    /** @brief 描画を作る。 @param parent 所有者(一覧)。 */
    explicit CompletionDelegate(QObject* parent) : QStyledItemDelegate(parent) {}

    /** @brief 名前(とアイコン)を描いてから、説明を右寄せで描く。
     * @param painter 描画。 @param option 行の状態。 @param index 行。
     */
    void paint(QPainter* painter, const QStyleOptionViewItem& option, const QModelIndex& index) const override {
        QStyledItemDelegate::paint(painter, option, index);
        const QString detail = index.data(kDetailRole).toString();
        const QString name = index.data(Qt::DisplayRole).toString();
        if (detail.isEmpty() || detail == name) {
            return;
        }
        const QFontMetrics metrics(option.font);
        const int iconWidth = option.decorationSize.width() + scaled(8);
        const int nameRight = option.rect.left() + iconWidth + metrics.horizontalAdvance(name) + scaled(16);
        const QRect area(nameRight, option.rect.top(), option.rect.right() - scaled(6) - nameRight, option.rect.height());
        if (area.width() < scaled(30)) {
            return;
        }
        painter->save();
        painter->setPen(QColor(theme::kCompletionDetail));
        painter->setFont(option.font);
        painter->drawText(area, Qt::AlignRight | Qt::AlignVCenter, metrics.elidedText(detail, Qt::ElideRight, area.width()));
        painter->restore();
    }
};

}  // namespace

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
    completer_->popup()->setItemDelegate(new CompletionDelegate(completer_->popup()));
    completer_->popup()->setIconSize(QSize(scaled(16), scaled(16)));
    // 一覧で候補が選ばれたら本文へ入れる。
    connect(completer_, QOverload<const QString&>::of(&QCompleter::activated), this,
            [this](const QString& value) { insertCompletion(value); });

    // 印を描くスクロールバーに置き換えるので、スクロールバーへの接続はこの後で行う。
    setUpView();
    connect(this, &QPlainTextEdit::cursorPositionChanged, this, [this] {
        onCursorMoved();
        updateDecorations();
    });

    // 名前の説明(ホバー): マウスの移動を受け取り、止まってから0.5秒後に出す。名前から離れたら閉じる。スクロールでも閉じる。
    viewport()->setMouseTracking(true);
    hoverTimer_.setSingleShot(true);
    hoverTimer_.setInterval(500);
    connect(&hoverTimer_, &QTimer::timeout, this, [this] {
        if (viewport()->underMouse()) {
            hoverAt(hoverPoint_);
        }
    });
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
    const QStringList problems = problemsAt(start);
    if (info.isEmpty() && problems.isEmpty()) {
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
    hover_->showInfo(info, anchor, font(), problems);
}

void CodeEditor::hoverAt(const QPoint& position) {
    const QTextCursor cursor = cursorForPosition(position);
    // cursorForPositionは行末より右や最後の行より下でも近い文字の位置を返すので、文字の上にあるかを確かめる。
    const QRect rect = cursorRect(cursor);
    const bool onText = qAbs(position.x() - rect.center().x()) <= fontMetrics().averageCharWidth() * 2
                        && position.y() >= rect.top() && position.y() <= rect.bottom();
    int start = 0;
    int end = 0;
    if (onText && !isMel() && onHoverRequested && nameAt(cursor.position(), &start, &end)) {
        // 同じ名前の説明を出している間は、問い合わせ直さない。
        const QPoint global = viewport()->mapToGlobal(position);
        if (!hover_ || !hover_->isVisible() || !hover_->anchor().contains(global)) {
            showHover(start, end);
        }
        return;
    }
    const QStringList problems = onText ? problemsAt(cursor.position()) : QStringList();
    if (!problems.isEmpty()) {
        // 名前でない位置(記号・文字列など)やMELのタブの、問題の説明。
        if (!hover_) {
            hover_ = new HoverPopup(this);
        }
        hover_->showInfo(HoverInfo(), QRect(viewport()->mapToGlobal(rect.topLeft()), rect.size()), font(), problems);
        return;
    }
    if (hover_ && hover_->isVisible() && !hover_->anchor().contains(viewport()->mapToGlobal(position))) {
        hover_->scheduleHide();  // 小窓へマウスを移す途中かもしれないので、すぐには閉じない。
    }
}

int CodeEditor::nameEndAtCursor() const {
    int start = 0;
    int end = 0;
    if (isMel() || !nameAt(textCursor().position(), &start, &end)) {
        return -1;
    }
    return end;
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
    // Ctrl+クリック: 名前の定義へ移動する(VS Codeと同じ)。
    if (event->type() == QEvent::MouseButtonPress && !isMel() && onDefinitionRequested) {
        auto mouse = static_cast<QMouseEvent*>(event);
        if (mouse->button() == Qt::LeftButton && mouse->modifiers() == Qt::ControlModifier) {
            const QTextCursor cursor = cursorForPosition(mouse->pos());
            int start = 0;
            int end = 0;
            if (nameAt(cursor.position(), &start, &end)) {
                setTextCursor(cursor);
                hideHover();
                onDefinitionRequested(end, false);
                return true;
            }
        }
    }
    if (event->type() == QEvent::ToolTip) {
        // Qtのツールチップ(マウスが少し止まった合図)。Mayaの「Popup Help」がオフだとMayaがこの合図を止めるので、
        // 普段は下のMouseMoveの自前のタイマーで出す。届いた場合(テストなど)も同じ処理をする。
        hoverAt(static_cast<QHelpEvent*>(event)->pos());
        return true;
    }
    if (event->type() == QEvent::MouseMove) {
        // ボタンを押していないマウスの移動: 止まってから0.5秒後に、その位置の説明を出す(VS Codeと同じ考え方)。
        auto mouse = static_cast<QMouseEvent*>(event);
        if (mouse->buttons() == Qt::NoButton) {
            hoverPoint_ = mouse->pos();
            hoverTimer_.start();
        } else {
            hoverTimer_.stop();
        }
    } else if (event->type() == QEvent::Leave || event->type() == QEvent::MouseButtonPress
               || event->type() == QEvent::Wheel) {
        hoverTimer_.stop();
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
    if (event->type() == QEvent::MouseButtonPress || event->type() == QEvent::Wheel) {
        hidePeek();
    }
    return NumberedTextEdit::viewportEvent(event);
}

void CodeEditor::focusOutEvent(QFocusEvent* event) {
    // 小窓自体はフォーカスを取らないので、別の部品へ移ったときだけ閉じる。
    hideHover();
    hideSignatureHelp();
    NumberedTextEdit::focusOutEvent(event);
}

void CodeEditor::setLanguage(ScriptLanguage language) {
    language_ = language;
    // テストやPySideから参照できるよう、保存名(python/mel)を動的プロパティにも入れる。
    setProperty("language", languageName(language_));
    highlighter_->setMel(isMel());
    highlighter_->rehighlight();
    hideCompletions();
    outlineRevision_ = -1;  // 構成の読み方(Python/MEL)が変わる。
    updateSticky();
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
        auto row = new QStandardItem(categoryIcon(item.category.isEmpty() ? item.kind : item.category), item.name);
        row->setToolTip(item.detail);
        row->setData(item.detail, kDetailRole);
        model->appendRow(row);
    }
    if (model->rowCount() == 0) {
        hideCompletions();
        return;
    }
    completer_->setCompletionPrefix(completionPrefix());
    completer_->popup()->setCurrentIndex(completer_->completionModel()->index(0, 0));
    // カーソルの位置に、幅480px(100%時)の一覧を出す(名前の右に説明を出すため、以前の380pxより広い)。
    QRect rect = cursorRect();
    rect.setWidth(scaled(480));
    completer_->complete(rect);
    if (onCompletionSelectionChanged) {
        onCompletionSelectionChanged();
    }
}

void CodeEditor::hideCompletions() {
    completer_->popup()->hide();
    hideCompletionDetail();
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
    // 一覧(別のウィンドウ)が閉じた後も、入力を続けられるようにコード欄へフォーカスを戻す。
    setFocus(Qt::OtherFocusReason);
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
    markerTimer_.start();
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
    markerTimer_.start();
    updateDecorations();
}

void CodeEditor::updateDecorations() {
    // ExtraSelectionは、本文を変えずに色や波線を重ねて表示する仕組み。
    QTextEdit::ExtraSelection currentLine;
    currentLine.format.setBackground(QColor(theme::kCurrentLine));
    currentLine.format.setProperty(QTextFormat::FullWidthSelection, true);
    currentLine.cursor = textCursor();
    currentLine.cursor.clearSelection();
    // 後ろのものほど上に重なる: カーソル行 → 同じ名前 → 括弧 → 検索の一致 → 問題の波線 → スペルの波線。
    QList<QTextEdit::ExtraSelection> selections;
    selections.append(currentLine);
    selections.append(wordMarks_);
    selections.append(bracketMarks_);
    selections.append(searchMarks_);
    selections.append(diagnosticMarks_);
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
    // 0. 名前の説明・定義をその場で見る表示を出している間のキー入力: Escは閉じるだけ、
    //    それ以外は閉じてから通常どおり処理する。
    const bool escape = event->key() == Qt::Key_Escape && event->modifiers() == Qt::NoModifier;
    const bool popupOpen = (hover_ && hover_->isVisible()) || (peek_ && peek_->isVisible())
                           || (problemPopup_ && problemPopup_->isVisible());
    if (popupOpen) {
        hideHover();
        hidePeek();
        if (escape) {
            event->accept();
            return;
        }
    }
    // 引数のヒントはEscで閉じる(補完の一覧が開いていれば、先に一覧を閉じる)。
    if (escape && isSignatureHelpVisible() && !completer_->popup()->isVisible()) {
        hideSignatureHelp();
        event->accept();
        return;
    }
    // ( と , の入力の後に、引数のヒントを求める(入力の処理が終わった後に予約する)。
    if ((event->text() == "(" || event->text() == ",") && onSignatureHelpRequested && !isMel()) {
        QTimer::singleShot(0, this, [this] {
            if (onSignatureHelpRequested) {
                onSignatureHelpRequested(false);
            }
        });
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

    // 2. 補完の一覧が開いているときのEnter・Tab・Escは、ここで処理して、親の部品へは回さない。
    //    以前はignore()して一覧に任せていたが、ignoreしたキーはQtの決まりで親へ順に回り、
    //    ドックの外のMayaのウィンドウまで届く。Mayaはそれを選択中のアウトライナなどへ渡し、
    //    フォーカスがコード欄から外れてしまっていた(確定後に改行などができなくなる)。
    if (completer_->popup()->isVisible()) {
        switch (event->key()) {
        case Qt::Key_Enter:
        case Qt::Key_Return:
        case Qt::Key_Tab: {
            const QModelIndex current = completer_->popup()->currentIndex();
            if (current.isValid()) {
                insertCompletion(current.data().toString());
            } else {
                hideCompletions();
            }
            setFocus(Qt::OtherFocusReason);
            event->accept();
            return;
        }
        case Qt::Key_Escape:
            hideCompletions();
            setFocus(Qt::OtherFocusReason);
            event->accept();
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
    if (command == EditCommand::ExpandSelection || command == EditCommand::ShrinkSelection) {
        if (command == EditCommand::ExpandSelection) {
            expandSelection();
        } else {
            shrinkSelection();
        }
        event->accept();
        return;
    }
    if (command != EditCommand::None) {
        // 行の移動・削除などは、畳んだ範囲を開いてから行う(隠れた行を誤って動かさないため)。
        if (command != EditCommand::SelectLine && command != EditCommand::CopyLine) {
            unfoldAll();
        }
        applyLineCommand(this, command, isMel() ? "//" : "#");
        event->accept();
        return;
    }

    // 4. Ctrl+Spaceで補完を、Ctrl+Shift+Spaceで引数のヒントを求める。
    if (event->key() == Qt::Key_Space && event->modifiers() == Qt::ControlModifier) {
        if (onCompletionRequested) {
            onCompletionRequested();
        }
        return;
    }
    if (event->key() == Qt::Key_Space && event->modifiers() == (Qt::ControlModifier | Qt::ShiftModifier)) {
        if (onSignatureHelpRequested && !isMel()) {
            onSignatureHelpRequested(true);
        }
        event->accept();
        return;
    }

    // 5. 選択なしのTabは空白4文字。
    if (event->key() == Qt::Key_Tab && event->modifiers() == Qt::NoModifier) {
        insertPlainText("    ");
        return;
    }

    // 5b. 括弧と引用符(自動で閉じる・閉じ括弧の上書き・選択を囲む・空の対をまとめて消す)。
    if (handleAutoClosing(event)) {
        event->accept();
        return;
    }

    // 6. 行頭の空白でのBackspace。
    if (event->key() == Qt::Key_Backspace && event->modifiers() == Qt::NoModifier && deleteToIndentStop()) {
        return;
    }

    // 7. Enterでインデントを引き継ぐ。Shift+EnterもQt標準ではU+2028(行区切り)を入れてしまい、
    //    見た目は改行でもPythonの構文エラーになるので、普通の改行として扱う(VS Codeと同じ)。
    if (event->key() == Qt::Key_Return
        && (event->modifiers() == Qt::NoModifier || event->modifiers() == Qt::ShiftModifier)) {
        insertNewlineWithIndent();
        return;
    }

    // 8. それ以外は普通の文字入力。
    QPlainTextEdit::keyPressEvent(event);
}

void CodeEditor::insertFromMimeData(const QMimeData* source) {
    if (!source->hasText()) {
        QPlainTextEdit::insertFromMimeData(source);
        return;
    }
    QString text = source->text();
    text.replace("\r\n", "\n");
    text.replace('\r', '\n');
    text.replace(QChar(QChar::LineSeparator), '\n');
    text.replace(QChar(QChar::ParagraphSeparator), '\n');
    textCursor().insertText(text);
    ensureCursorVisible();
}

bool CodeEditor::handleAutoClosing(QKeyEvent* event) {
    if (!autoClosing_ || (event->modifiers() & (Qt::ControlModifier | Qt::AltModifier | Qt::MetaModifier))) {
        return false;
    }
    static const QString openers = "([{";
    static const QString closers = ")]}";
    QTextCursor cursor = textCursor();
    const QString line = cursor.block().text();
    const int column = cursor.positionInBlock();
    const QChar before = column > 0 ? line[column - 1] : QChar();
    const QChar after = column < line.size() ? line[column] : QChar();
    // 空の対 () "" の間でのBackspaceは、両方を消す。
    if (event->key() == Qt::Key_Backspace) {
        if (cursor.hasSelection() || before.isNull() || after.isNull()) {
            return false;
        }
        const int opener = openers.indexOf(before);
        const bool pair = (opener >= 0 && closers[opener] == after) || ((before == '"' || before == '\'') && after == before);
        if (!pair) {
            return false;
        }
        cursor.beginEditBlock();
        cursor.deletePreviousChar();
        cursor.deleteChar();
        cursor.endEditBlock();
        setTextCursor(cursor);
        return true;
    }
    const QString typed = event->text();
    if (typed.size() != 1) {
        return false;
    }
    const QChar character = typed[0];
    const bool quote = character == '"' || character == '\'';
    const int opener = openers.indexOf(character);
    if (opener < 0 && !quote && !closers.contains(character)) {
        return false;
    }
    // 選択中に開き括弧・引用符を打つと、選択を囲む。
    if (cursor.hasSelection() && (opener >= 0 || quote)) {
        const QChar closing = quote ? character : closers[opener];
        const int start = cursor.selectionStart();
        const int end = cursor.selectionEnd();
        cursor.beginEditBlock();
        QTextCursor edit(document());
        edit.setPosition(end);
        edit.insertText(QString(closing));
        edit.setPosition(start);
        edit.insertText(QString(character));
        cursor.endEditBlock();
        QTextCursor selected(document());
        selected.setPosition(start + 1);
        selected.setPosition(end + 1, QTextCursor::KeepAnchor);
        setTextCursor(selected);
        return true;
    }
    if (cursor.hasSelection()) {
        return false;
    }
    const bool insideText = isInsideStringOrComment(document(), language_, cursor.position());
    // 閉じ括弧・閉じ引用符の上書き: 直後に同じ文字があれば、入れずにカーソルだけ進める。
    if (after == character && (closers.contains(character) || (quote && insideText))) {
        cursor.movePosition(QTextCursor::NextCharacter);
        setTextCursor(cursor);
        return true;
    }
    if (insideText || closers.contains(character)) {
        return false;  // 文字列・コメントの中では閉じない。
    }
    const bool roomAfter = after.isNull() || after.isSpace() || closers.contains(after) || QString(",:;").contains(after);
    if (!roomAfter) {
        return false;
    }
    if (quote) {
        if (before == character) {
            return false;  // 三重引用符を打っている途中("" の次の ")。
        }
        if (isNamePart(before)) {
            // 直前が名前なら、文字列の接頭辞(r・b・f・u・rb など)のときだけ閉じる。
            int start = column;
            while (start > 0 && isNamePart(line[start - 1])) {
                --start;
            }
            static const QRegularExpression prefix("^(?:[rRbBfFuU]|[rR][bBfF]|[bBfF][rR])$");
            if (!prefix.match(line.mid(start, column - start)).hasMatch()) {
                return false;
            }
        }
    }
    const QChar closing = quote ? character : closers[opener];
    cursor.insertText(QString(character) + closing);
    cursor.movePosition(QTextCursor::PreviousCharacter);
    setTextCursor(cursor);
    return true;
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
