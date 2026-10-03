/** @file output_panel.cpp
 * @brief OutputViewとOutputPanelの実装。
 */
#include "editor/output_panel.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QComboBox>
#include <QKeyEvent>
#include <QMenu>
#include <QScrollBar>
#include <QTextCursor>
#include <QVBoxLayout>

namespace hedit {
namespace {

/// 保持する出力の文字数の上限(1Mi文字)。超えたら古いものから捨てる。
constexpr int kMaximumHistoryCharacters = 1024 * 1024;

/// 出力を取り出す間隔(ミリ秒)。
constexpr int kPollInterval = 25;

/** @brief 出力の種類に対応する文字色。
 * @param kind 出力の種類。
 * @return theme.hの色。
 */
QColor colorFor(OutputKind kind) {
    switch (kind) {
    case OutputKind::Warning:
        return QColor(theme::kOutputWarning);
    case OutputKind::Error:
        return QColor(theme::kOutputError);
    case OutputKind::Result:
        return QColor(theme::kOutputResult);
    case OutputKind::Info:
        return QColor(theme::kOutputInfo);
    case OutputKind::History:
        return QColor(theme::kOutputHistory);
    default:
        return QColor(theme::kOutputNormal);
    }
}

}  // namespace

// ---------------------------------------------------------------------------
// OutputView
// ---------------------------------------------------------------------------

OutputView::OutputView() {
    setObjectName("output");
    setLineNumbersVisible(false);
    setLineWrapMode(NoWrap);
    setReadOnly(true);
    setTextInteractionFlags(Qt::TextSelectableByMouse | Qt::TextSelectableByKeyboard);
    setFocusPolicy(Qt::StrongFocus);
}

bool OutputView::event(QEvent* event) {
    // ShortcutOverrideをacceptすると、同じキーのショートカット(Mayaのメニュー等)より先に
    // keyPressEventでこの欄が受け取れる。
    if (event->type() == QEvent::ShortcutOverride) {
        auto key = static_cast<QKeyEvent*>(event);
        if (key->matches(QKeySequence::Copy) || key->matches(QKeySequence::SelectAll)) {
            event->accept();
            return true;
        }
    }
    return NumberedTextEdit::event(event);
}

void OutputView::keyPressEvent(QKeyEvent* event) {
    if (event->matches(QKeySequence::Copy)) {
        copy();
        event->accept();
        return;
    }
    if (event->matches(QKeySequence::SelectAll)) {
        selectAll();
        event->accept();
        return;
    }
    QPlainTextEdit::keyPressEvent(event);
}

// ---------------------------------------------------------------------------
// OutputPanel
// ---------------------------------------------------------------------------

OutputPanel::OutputPanel(std::function<QList<OutputMessage>()> takeOutput, QWidget* parent)
    : QWidget(parent), takeOutput_(std::move(takeOutput)) {
    setObjectName("outputPanel");

    // レイアウトに追加した部品は、このOutputPanelが所有する。
    view_ = new OutputView;
    QFont font("Consolas");
    font.setPixelSize(scaled(12));
    view_->setFont(font);
    view_->setMaximumBlockCount(5000);  // 表示は最新の5000行まで。
    view_->setPlaceholderText(QString());
    auto layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);
    layout->addWidget(view_);

    // 表示モードの選択欄。選択肢の順番はOutputFilterの値と同じ。
    filterSelector_ = new QComboBox;
    filterSelector_->setObjectName("outputMode");
    filterSelector_->addItems({"Normal", "Output only", "Warnings + Errors", "Errors only"});
    filterSelector_->setToolTip("Output display mode");
    filterSelector_->setFixedWidth(scaled(150));
    // モードを変えたら、保持している出力を新しいモードで出し直す。
    connect(filterSelector_, QOverload<int>::of(&QComboBox::currentIndexChanged), this, [this] {
        view_->clear();
        append(history_);
    });

    view_->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(view_, &QWidget::customContextMenuRequested, this, [this](const QPoint& point) { showContextMenu(point); });

    // タイマーはこの部品のメンバーなので、部品の破棄と一緒に止まる。
    connect(&pollTimer_, &QTimer::timeout, this, [this] { flush(); });
    if (takeOutput_) {
        pollTimer_.start(kPollInterval);
    }
}

void OutputPanel::flush() {
    if (!takeOutput_) {
        return;
    }
    const QList<OutputMessage> messages = takeOutput_();
    if (messages.isEmpty()) {
        return;
    }
    // モードを戻したときに出し直せるよう保持する。ただし1Mi文字を超えて溜めない。
    for (OutputMessage message : messages) {
        message.text = message.text.right(kMaximumHistoryCharacters);
        historySize_ += message.text.size();
        history_.append(message);
    }
    while (historySize_ > kMaximumHistoryCharacters && !history_.isEmpty()) {
        historySize_ -= history_.first().text.size();
        history_.removeFirst();
    }
    append(messages);
}

void OutputPanel::refreshNow() {
    // 描画中に同じ関数が呼ばれた場合と、前回から25ms経っていない場合は描かない。
    const bool tooSoon = lastRefresh_.isValid() && lastRefresh_.elapsed() < kPollInterval;
    if (refreshing_ || tooSoon) {
        return;
    }
    refreshing_ = true;
    lastRefresh_.restart();
    flush();
    if (view_->isVisible()) {
        // repaintは、イベントループを待たずにその場で描く(Mayaの処理中でも表示が進む)。
        view_->viewport()->repaint();
    }
    refreshing_ = false;
}

void OutputPanel::clear() {
    // まだ描いていない出力も一緒に消す。
    if (takeOutput_) {
        takeOutput_();
    }
    history_.clear();
    historySize_ = 0;
    view_->clear();
}

void OutputPanel::appendNote(const QString& text) {
    view_->appendPlainText(text);
}

void OutputPanel::setWrap(bool wrap) {
    view_->setLineWrapMode(wrap ? QPlainTextEdit::WidgetWidth : QPlainTextEdit::NoWrap);
}

bool OutputPanel::accepts(OutputKind kind) const {
    switch (static_cast<OutputFilter>(filterSelector_->currentIndex())) {
    case OutputFilter::OutputOnly:
        return kind != OutputKind::History;
    case OutputFilter::WarningsAndErrors:
        return kind == OutputKind::Warning || kind == OutputKind::Error;
    case OutputFilter::ErrorsOnly:
        return kind == OutputKind::Error;
    default:
        return true;
    }
}

void OutputPanel::append(const QList<OutputMessage>& messages) {
    QScrollBar* vertical = view_->verticalScrollBar();
    QScrollBar* horizontal = view_->horizontalScrollBar();
    const int oldVertical = vertical->value();
    const int oldHorizontal = horizontal->value();
    const bool hasSelection = view_->textCursor().hasSelection();

    // 利用者の選択範囲を覚えておく。setKeepPositionOnInsertで、追記しても位置がずれないようにする。
    QTextCursor anchor(view_->document());
    QTextCursor caret(view_->document());
    anchor.setPosition(view_->textCursor().anchor());
    caret.setPosition(view_->textCursor().position());
    anchor.setKeepPositionOnInsert(true);
    caret.setKeepPositionOnInsert(true);

    // 表示用のカーソルとは別のカーソルで末尾へ追記する。
    QTextCursor writer(view_->document());
    writer.movePosition(QTextCursor::End);
    bool added = false;  // 表示モードで隠す種類だけなら、何も追加されない。
    for (const OutputMessage& message : messages) {
        if (!accepts(message.kind)) {
            continue;
        }
        QTextCharFormat format;
        format.setForeground(colorFor(message.kind));
        writer.insertText(message.text, format);
        added = added || !message.text.isEmpty();
    }
    // 以後の追記(appendNote等)が直前の色を引き継がないよう、通常の色へ戻す。
    QTextCharFormat normal;
    normal.setForeground(QColor(theme::kOutputNormal));
    writer.setCharFormat(normal);

    if (hasSelection) {
        QTextCursor selection = anchor;
        selection.setPosition(caret.position(), QTextCursor::KeepAnchor);
        view_->setTextCursor(selection);
    }
    // 新しいログが表示されたら、スクロール位置にかかわらず必ず最下部へ移る(途中を見ていても、
    // 更新に気づけるように)。選択範囲は上で戻してあるので、コピーしたい範囲は保たれる。
    vertical->setValue(added ? vertical->maximum() : oldVertical);
    horizontal->setValue(oldHorizontal);
}

void OutputPanel::showContextMenu(const QPoint& point) {
    // 標準のメニュー(コピー・全選択)に「Clear output」を足す。
    // createStandardContextMenuのメニューは呼出側の所有なので、閉じた後にdeleteする。
    QMenu* menu = view_->createStandardContextMenu();
    menu->setObjectName("outputContextMenu");
    menu->addSeparator();
    QAction* clearAction = menu->addAction("Clear output", this, [this] { clear(); });
    clearAction->setObjectName("clearOutputAction");
    menu->exec(view_->mapToGlobal(point));  // メニューが閉じるまでここで待つ。
    delete menu;
}

}  // namespace hedit
