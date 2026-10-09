/** @file code_editor.cpp
 * @brief CodeEditorの実装。
 */
#include "editor/code_editor.h"
#include "core/fuzzy_match.h"
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
#include <algorithm>

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
    setCursorWidth(scaled(2));  // VS Codeと同じ2px(1pxは見失いやすい)。
    setProperty("language", languageName(language_));

    // 色分けは文書の子として作る(文書と一緒に破棄される)。
    highlighter_ = new SyntaxHighlighter(document());

    // 補完。QCompleterはこの欄の子なので、この欄と一緒に破棄される。
    // 一覧の部品(popup)とその見た目は、初めて一覧を出すときにensureCompletionPopupで作る
    // (タブを開くたびに、一覧の部品の作成とスタイルシートの解析をしない)。
    completer_ = new QCompleter(this);
    completer_->setModel(new QStandardItemModel(completer_));
    completer_->setWidget(this);
    // 絞り込みと並べ替えはapplyCompletionFilterで行う(大文字小文字を区別しない・単語の頭からの飛び飛びの一致)。
    // QCompleterには常に空の接頭辞を渡し、モデルに入れた候補をそのまま出させる。
    completer_->setCompletionMode(QCompleter::PopupCompletion);
    completer_->setMaxVisibleItems(12);  // VS Codeと同じく12行(QCompleterの既定は7行)。
    // 一覧で候補が選ばれたら本文へ入れる。
    connect(completer_, QOverload<const QString&>::of(&QCompleter::activated), this,
            [this](const QString& value) { insertCompletion(value); });

    // 印を描くスクロールバーに置き換えるので、スクロールバーへの接続はこの後で行う。
    setUpView();
    connect(this, &QPlainTextEdit::cursorPositionChanged, this, [this] {
        onCursorMoved();
        updateDecorations();
    });
    lastBlockCount_ = blockCount();

    // 名前の説明(ホバー): マウスの移動を受け取り、止まってから0.3秒後に出す(VS Codeの既定と同じ)。名前から離れたら閉じる。
    // スクロールでも閉じる。
    viewport()->setMouseTracking(true);
    hoverTimer_.setSingleShot(true);
    hoverTimer_.setInterval(300);
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
        // 名前でない位置(記号・文字列など)やMELのタブの、問題の説明。同じ位置の説明を出している間は出し直さない。
        const QRect anchor(viewport()->mapToGlobal(rect.topLeft()), rect.size());
        if (hover_ && hover_->isVisible() && hover_->anchor() == anchor) {
            return;
        }
        if (!hover_) {
            hover_ = new HoverPopup(this);
        }
        hover_->showInfo(HoverInfo(), anchor, font(), problems);
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
        // ボタンを押していないマウスの移動: 止まってから0.3秒後に、その位置の説明を出す(VS Codeと同じ考え方)。
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
    if (language == language_) {
        return;  // 同じ言語なら、全体の塗り直し(行数に比例する)をしない。
    }
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

void CodeEditor::ensureCompletionPopup() {
    if (completionPopupReady_) {
        return;
    }
    completionPopupReady_ = true;
    // popup()は初めて呼んだときにQCompleterが一覧の部品を作る(所有者はQCompleter)。
    QAbstractItemView* popup = completer_->popup();
    popup->setFont(font());
    // %1〜%7は、後ろの.arg()で順番に置き換わる。
    popup->setStyleSheet(
        QString("QAbstractItemView{background:%1;color:%2;border:%3px solid %4;"
                "selection-background-color:%5;selection-color:%6;padding:%7px;}")
            .arg(QString(theme::kPopupBackground))
            .arg(QString(theme::kText))
            .arg(scaled(1))
            .arg(QString(theme::kPopupBorder))
            .arg(QString(theme::kPopupSelection))
            .arg(QString(theme::kPopupSelectedText))
            .arg(scaled(3)));
    popup->setItemDelegate(new CompletionDelegate(popup));
    popup->setIconSize(QSize(scaled(16), scaled(16)));
    // 選んでいる候補が変わったら説明を出し直し、一覧が閉じたら説明も閉じる(eventFilter)。
    popup->installEventFilter(this);
    connect(popup->selectionModel(), &QItemSelectionModel::currentChanged, this, [this] {
        if (onCompletionSelectionChanged && completer_->popup()->isVisible()) {
            onCompletionSelectionChanged();
        }
    });
}

bool CodeEditor::isCompletionVisible() const {
    return completionPopupReady_ && completer_->popup()->isVisible();
}

int CodeEditor::applyCompletionFilter(const QString& prefix) {
    auto model = static_cast<QStandardItemModel*>(completer_->model());
    model->clear();
    const QList<CompletionItem> ranked = rankCompletions(completionItems_, prefix);
    QList<QStandardItem*> rows;
    rows.reserve(ranked.size());
    for (const CompletionItem& item : ranked) {
        auto row = new QStandardItem(categoryIcon(item.category.isEmpty() ? item.kind : item.category), item.name);
        row->setToolTip(item.detail);
        row->setData(item.detail, kDetailRole);
        rows.append(row);
    }
    // まとめて追加する(1件ずつだと、開いている一覧が1件ごとに大きさを計算し直す)。追加した項目はモデルが所有する。
    model->invisibleRootItem()->appendRows(rows);
    completer_->setCompletionPrefix(QString());
    return model->rowCount();
}

void CodeEditor::showCompletions(const QList<CompletionItem>& items) {
    ensureCompletionPopup();
    completionItems_ = items;
    const QString prefix = completionPrefix();
    if (applyCompletionFilter(prefix) == 0) {
        hideCompletions();
        return;
    }
    completionStart_ = textCursor().position() - prefix.size();
    completer_->popup()->setCurrentIndex(completer_->completionModel()->index(0, 0));
    // 補完中の名前の先頭に、幅480px(100%時)の一覧を出す(名前の右に説明を出すため、以前の380pxより広い)。
    // 先頭に合わせるので、続けて入力しても一覧が横へ動かない(VS Codeと同じ)。
    QTextCursor start(document());
    start.setPosition(completionStart_);
    QRect rect = cursorRect(start);
    rect.setWidth(scaled(480));
    completer_->complete(rect);
    if (onCompletionSelectionChanged) {
        onCompletionSelectionChanged();
    }
}

bool CodeEditor::refilterCompletions(bool keepWhenEmpty) {
    if (!isCompletionVisible()) {
        return false;
    }
    const QTextCursor cursor = textCursor();
    const QString prefix = completionPrefix();
    if (cursor.hasSelection() || cursor.position() - prefix.size() != completionStart_) {
        hideCompletions();  // 補完中の名前の外へ出た(``(``や空白を入力した・別の位置へ移った)。
        return false;
    }
    if (applyCompletionFilter(prefix) == 0) {
        if (keepWhenEmpty) {
            return true;  // 呼出側が、描画の前に候補を入れ替える。
        }
        hideCompletions();
        return false;
    }
    completer_->popup()->setCurrentIndex(completer_->completionModel()->index(0, 0));
    // 開いたまま、件数に合わせて高さを直す(complete()は表示中の一覧を閉じずに位置と大きさだけを変える)。
    QTextCursor start(document());
    start.setPosition(completionStart_);
    QRect rect = cursorRect(start);
    rect.setWidth(scaled(480));
    completer_->complete(rect);
    if (onCompletionSelectionChanged) {
        onCompletionSelectionChanged();
    }
    return true;
}

void CodeEditor::hideCompletions() {
    if (completionPopupReady_) {
        completer_->popup()->hide();
    }
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
    spellingSkipped_ = QTextCursor();
    spellingRecheckSent_ = false;
    const QTextCursor caret = textCursor();
    // 表示中の行だけ(最大8,000文字)を集める。全文は調べない。
    QTextBlock block = firstVisibleBlock();
    const int base = block.position();
    QString visibleText;
    qreal top = blockTop(block);
    while (block.isValid() && visibleText.size() < 8000 && top < viewport()->height()) {
        visibleText += block.text() + '\n';
        if (block.isVisible()) {
            top += blockBoundingRect(block).height();
        }
        block = block.next();
    }

    QElapsedTimer elapsed;
    elapsed.start();
    for (const auto& range : spelling.check(visibleText)) {
        const int start = base + range.first;
        const int end = start + range.second;
        // 入力中の単語(直前に文字を入れた位置にカーソルがある単語)には付けない。カーソルが離れたら調べ直す。
        if (!caret.hasSelection() && lastEditEnd_ >= start && lastEditEnd_ <= end && caret.position() >= start
            && caret.position() <= end) {
            spellingSkipped_ = QTextCursor(document());
            spellingSkipped_.setPosition(start);
            spellingSkipped_.setPosition(end, QTextCursor::KeepAnchor);
            continue;
        }
        QTextEdit::ExtraSelection mark;
        mark.cursor = QTextCursor(document());
        mark.cursor.setPosition(start);
        mark.cursor.setPosition(end, QTextCursor::KeepAnchor);
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
    spellingSkipped_ = QTextCursor();
    if (spellingMarks_.isEmpty()) {
        return;  // 既に空(スペルチェックがオフのときは、入力のたびに全タブから呼ばれる)。
    }
    spellingMarks_.clear();
    updateDecorations();
}

void CodeEditor::setSearchHighlights(const QList<TextMatch>& matches) {
    searchMarks_.clear();
    markersDirty_ = true;
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
    markersDirty_ = true;
    markerTimer_.start();
    updateDecorations();
}

void CodeEditor::updateDecorations() {
    // ExtraSelectionは、本文を変えずに色や波線を重ねて表示する仕組み。
    static const QColor currentLineColor(theme::kCurrentLine);
    QTextEdit::ExtraSelection currentLine;
    currentLine.format.setBackground(currentLineColor);
    currentLine.format.setProperty(QTextFormat::FullWidthSelection, true);
    currentLine.cursor = textCursor();
    currentLine.cursor.clearSelection();

    // 表示している範囲(前後に40行の余裕)の位置。この範囲にかかる印だけを渡す。
    // 範囲は、本文・スクロール位置・表示部分の大きさ・折りたたみが変わったときだけ求め直す(カーソルの移動では同じ)。
    const int key[4] = {document()->revision(), verticalScrollBar()->value(), viewport()->height(), viewport()->width()};
    if (!std::equal(key, key + 4, visibleRangeKey_)) {
        std::copy(key, key + 4, visibleRangeKey_);
        constexpr int kMargin = 40;
        QTextBlock first = firstVisibleBlock();
        for (int i = 0; i < kMargin && first.previous().isValid(); ++i) {
            first = first.previous();
        }
        // 行の位置は高さを足して求める(blockTopの説明を参照)。畳んで隠した行は測らない。
        QTextBlock last = firstVisibleBlock();
        const int height = viewport()->height();
        qreal top = blockTop(last);
        for (QTextBlock block = last; block.isValid() && top <= height; block = block.next()) {
            if (!block.isVisible()) {
                continue;
            }
            last = block;
            top += blockBoundingRect(block).height();
        }
        for (int i = 0; i < kMargin && last.next().isValid(); ++i) {
            last = last.next();
        }
        visibleStart_ = first.isValid() ? first.position() : 0;
        visibleEnd_ = last.isValid() ? last.position() + last.length() : document()->characterCount();
    }
    const int start = visibleStart_;
    const int end = visibleEnd_;
    QList<QTextEdit::ExtraSelection> selections;
    selections.append(currentLine);
    auto appendVisible = [&selections, start, end](const QList<QTextEdit::ExtraSelection>& marks) {
        for (const QTextEdit::ExtraSelection& mark : marks) {
            if (mark.cursor.selectionEnd() >= start && mark.cursor.selectionStart() <= end) {
                selections.append(mark);
            }
        }
    };
    // 後ろのものほど上に重なる: カーソル行 → 同じ名前 → 括弧 → 検索の一致 → 問題の波線 → スペルの波線。
    appendVisible(wordMarks_);
    appendVisible(bracketMarks_);
    appendVisible(searchMarks_);
    appendVisible(diagnosticMarks_);
    appendVisible(spellingMarks_);
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
        const bool scrollKey = (key->key() == Qt::Key_Up || key->key() == Qt::Key_Down)
                               && key->modifiers() == Qt::ControlModifier;
        const bool homeKey = key->key() == Qt::Key_Home
                             && (key->modifiers() == Qt::NoModifier || key->modifiers() == Qt::ShiftModifier);
        const bool handledHere = isRunKey(key) || scrollKey || homeKey
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
    if (escape && isSignatureHelpVisible() && !isCompletionVisible()) {
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

    // 0b. 小窓も補完の一覧も無いときのEsc: 検索バーを開いていれば閉じる(本文にフォーカスがあっても。VS Codeと同じ)。
    if (escape && !isCompletionVisible() && onEscapePressed && onEscapePressed()) {
        event->accept();
        return;
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
    if (isCompletionVisible() && (event->key() == Qt::Key_Return || event->key() == Qt::Key_Enter)
        && event->modifiers() == Qt::NoModifier) {
        // 選んでいる候補が、打った名前と同じなら、確定しても何も変わらない。一覧を閉じて改行する
        // (VS Codeの設定 editor.acceptSuggestionOnEnter を smart にしたときと同じ)。
        const QModelIndex current = completer_->popup()->currentIndex();
        if (current.isValid() && current.data().toString() == completionPrefix()) {
            hideCompletions();
        }
    }
    if (isCompletionVisible()) {
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

    // 3b. Home は行頭の空白の後と行の先頭を行き来する。Ctrl+↑↓ はカーソルを動かさずに1行スクロールする(VS Codeと同じ)。
    if (event->key() == Qt::Key_Home
        && (event->modifiers() == Qt::NoModifier || event->modifiers() == Qt::ShiftModifier)) {
        moveToLineHome(event->modifiers() == Qt::ShiftModifier);
        event->accept();
        return;
    }
    if ((event->key() == Qt::Key_Up || event->key() == Qt::Key_Down) && event->modifiers() == Qt::ControlModifier) {
        QScrollBar* bar = verticalScrollBar();
        bar->setValue(bar->value() + (event->key() == Qt::Key_Down ? 1 : -1));
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

    // 8. それ以外は普通の文字入力。else: などの : を打ったら、その行を1段浅くする。
    const bool colon = event->text() == ":" && !isMel() && smartIndent_;
    QPlainTextEdit::keyPressEvent(event);
    if (colon) {
        dedentBlockKeyword();
    }
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
    QTextCursor cursor = textCursor();
    if (source->hasFormat(kWholeLineMimeType) && !cursor.hasSelection() && text.endsWith('\n')) {
        // 選択なしのCtrl+C・Ctrl+Xでコピーした行: カーソルの行の上へ入れる。カーソルは元の文字の上に残る(VS Codeと同じ)。
        QTextCursor lineStart(document());
        lineStart.setPosition(cursor.block().position());
        lineStart.insertText(text);
        ensureCursorVisible();
        return;
    }
    cursor.insertText(text);
    ensureCursorVisible();
}

bool CodeEditor::handleAutoClosing(QKeyEvent* event) {
    if (!autoClosing_ || (event->modifiers() & (Qt::ControlModifier | Qt::AltModifier | Qt::MetaModifier))) {
        return false;
    }
    static const QString openers = "([{";
    static const QString closers = ")]}";
    pruneAutoClosers();
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
        // 自分で打った閉じ括弧は残す(自動で入れたものだけを、開き括弧と一緒に消す。VS Codeと同じ)。
        if (!pair || !isAutoCloser(cursor.position(), after)) {
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
    // 閉じ括弧・閉じ引用符の上書き: 直後に同じ文字があり、それを自動で入れていたら、入れずにカーソルだけ進める
    // (自分で打った閉じ括弧は上書きしない。上書きすると、括弧が1つ足りなくなることがある)。
    if (after == character && (closers.contains(character) || quote) && isAutoCloser(cursor.position(), character)) {
        cursor.movePosition(QTextCursor::NextCharacter);
        setTextCursor(cursor);
        pruneAutoClosers();
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
    // 自動で入れた閉じ括弧を覚える(1文字を選んだカーソル。編集に合わせて位置が動く)。
    QTextCursor closer(document());
    closer.setPosition(cursor.position());
    closer.setPosition(cursor.position() + 1, QTextCursor::KeepAnchor);
    autoClosers_.append(closer);
    return true;
}

bool CodeEditor::isAutoCloser(int position, QChar character) const {
    if (document()->characterAt(position) != character) {
        return false;
    }
    return std::any_of(autoClosers_.begin(), autoClosers_.end(), [position](const QTextCursor& closer) {
        return closer.selectionStart() == position && closer.selectionEnd() == position + 1;
    });
}

void CodeEditor::pruneAutoClosers() {
    if (autoClosers_.isEmpty()) {
        return;
    }
    // 消された(選択が1文字でなくなった)もの・閉じ括弧でなくなったもの・カーソルと別の行のものを捨てる
    // (VS Codeも、カーソルが閉じ括弧の行から離れたら、自動で入れたことを忘れる)。
    static const QString closingCharacters = ")]}\"'";
    const int line = textCursor().blockNumber();
    QTextDocument* doc = document();
    autoClosers_.erase(std::remove_if(autoClosers_.begin(), autoClosers_.end(),
                                      [line, doc](const QTextCursor& closer) {
                                          return closer.selectionEnd() - closer.selectionStart() != 1
                                                 || !closingCharacters.contains(doc->characterAt(closer.selectionStart()))
                                                 || doc->findBlock(closer.selectionStart()).blockNumber() != line;
                                      }),
                       autoClosers_.end());
    if (autoClosers_.size() > 32) {
        autoClosers_.erase(autoClosers_.begin(), autoClosers_.end() - 32);
    }
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

namespace {

/** @brief 行のうち、コメントを除いたコードの部分(末尾の空白も除く)。
 * @param document 文書。
 * @param language 言語。
 * @param block 行。
 * @param text 行の、カーソルより前の部分。
 * @return コードの部分。``if x:  # note`` なら ``if x:``。
 */
QString codePart(const QTextDocument* document, ScriptLanguage language, const QTextBlock& block, const QString& text) {
    const QChar marker = language == ScriptLanguage::Mel ? '/' : '#';
    for (int i = 0; i < text.size(); ++i) {
        // 記号が文字列の中でなく(その位置はまだコメントでない)、直後からコメントになるなら、そこからがコメント。
        if (text[i] == marker && !isInsideStringOrComment(document, language, block.position() + i)
            && isInsideStringOrComment(document, language, block.position() + i + 1)) {
            return text.left(i).trimmed();
        }
    }
    return text.trimmed();
}

/** @brief 行頭の空白の数。 @param text 行。 @return 空白(半角スペース)の数。 */
int leadingSpaces(const QString& text) {
    int count = 0;
    while (count < text.size() && text[count] == ' ') {
        ++count;
    }
    return count;
}

}  // namespace

void CodeEditor::insertNewlineWithIndent() {
    if (!smartIndent_) {
        insertPlainText("\n");
        return;
    }
    QTextCursor cursor = textCursor();
    cursor.beginEditBlock();
    if (cursor.hasSelection()) {
        cursor.removeSelectedText();
    }
    const QTextBlock block = cursor.block();
    const QString line = block.text();
    const int column = cursor.positionInBlock();
    const QString before = line.left(column);
    const QString after = line.mid(column);
    QString indent(leadingSpaces(before), ' ');
    const QString code = codePart(document(), language_, block, before);

    if (isMel()) {
        // MELは「{」で終わる行の次を1段深くする。
        if (code.endsWith('{')) {
            indent += "    ";
        }
        cursor.insertText("\n" + indent);
    } else if (code.isEmpty() && after.trimmed().isEmpty()) {
        // 空白だけの行: その行の空白を消してから改行する(空行にインデントを残さない。次の行は同じ深さ)。
        cursor.movePosition(QTextCursor::StartOfBlock);
        cursor.movePosition(QTextCursor::EndOfBlock, QTextCursor::KeepAnchor);
        cursor.removeSelectedText();
        cursor.insertText("\n" + indent);
    } else {
        static const QString openers = "([{";
        static const QString closers = ")]}";
        const QChar last = code.isEmpty() ? QChar() : code.back();
        const QString rest = after.trimmed();
        const int opener = openers.indexOf(last);
        if (opener >= 0 && !rest.isEmpty() && rest[0] == closers[opener] && code.size() == before.trimmed().size()) {
            // 開き括弧と閉じ括弧の間: 閉じ括弧を次の行へ送り、間の行を1段深くする。
            //   foo(|)  →  foo(
            //                  |
            //              )
            cursor.movePosition(QTextCursor::NextCharacter, QTextCursor::KeepAnchor, after.indexOf(rest[0]));
            cursor.removeSelectedText();
            cursor.insertText("\n" + indent + "    ");
            const int inside = cursor.position();
            cursor.insertText("\n" + indent);
            cursor.setPosition(inside);
        } else if (last == ':' || opener >= 0) {
            // 「:」や開き括弧で終わる行の次は1段深くする。
            cursor.insertText("\n" + indent + "    ");
        } else {
            // return・pass・break・continue・raise の次は、そのブロックを抜けるので1段浅くする。
            static const QRegularExpression exits("^(return|pass|break|continue|raise)\\b");
            if (rest.isEmpty() && exits.match(code).hasMatch() && indent.size() >= 4) {
                indent.chop(4);
            }
            cursor.insertText("\n" + indent);
        }
    }
    cursor.endEditBlock();
    setTextCursor(cursor);
    ensureCursorVisible();
}

void CodeEditor::dedentBlockKeyword() {
    QTextCursor cursor = textCursor();
    if (cursor.hasSelection()) {
        return;
    }
    const QTextBlock block = cursor.block();
    const QString line = block.text();
    const int column = cursor.positionInBlock();
    // 打った「:」が行の最後で、文字列・コメントの中でないときだけ。
    if (column == 0 || line[column - 1] != ':' || !line.mid(column).trimmed().isEmpty()
        || isInsideStringOrComment(document(), language_, cursor.position() - 1)) {
        return;
    }
    static const QRegularExpression keyword("^(else|finally)\\s*:$|^(elif|except)\\b.*:$");
    const QString code = line.trimmed();
    if (!keyword.match(code).hasMatch()) {
        return;
    }
    const int indent = leadingSpaces(line);
    if (indent < 4) {
        return;
    }
    // 前の空でない行と比べる。同じ深さ(まだ前のブロックの中)か、前の行が「:」で終わり1段深い位置にあるときだけ浅くする。
    QTextBlock previous = block.previous();
    while (previous.isValid() && previous.text().trimmed().isEmpty()) {
        previous = previous.previous();
    }
    if (!previous.isValid()) {
        return;
    }
    const int previousIndent = leadingSpaces(previous.text());
    const bool previousOpens = codePart(document(), language_, previous, previous.text()).endsWith(':');
    if (indent != previousIndent && !(previousOpens && indent == previousIndent + 4)) {
        return;
    }
    // 「:」の入力と同じUndoのまとまりにする(Ctrl+Zで両方戻る)。
    QTextCursor edit(block);
    edit.joinPreviousEditBlock();
    edit.movePosition(QTextCursor::NextCharacter, QTextCursor::KeepAnchor, 4);
    edit.removeSelectedText();
    edit.endEditBlock();
}

void CodeEditor::moveToLineHome(bool select) {
    QTextCursor cursor = textCursor();
    const QTextBlock block = cursor.block();
    const int firstText = leadingSpaces(block.text());
    // 行頭の空白の後にいなければそこへ、既にいれば行の先頭へ。空白だけの行は行の先頭へ。
    const int column = cursor.positionInBlock();
    const int target = (column != firstText && firstText < block.text().size()) ? firstText : 0;
    cursor.setPosition(block.position() + target, select ? QTextCursor::KeepAnchor : QTextCursor::MoveAnchor);
    setTextCursor(cursor);
}

}  // namespace hedit
