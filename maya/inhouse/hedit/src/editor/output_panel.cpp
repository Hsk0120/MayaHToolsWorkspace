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
#include <QShowEvent>
#include <QTextCursor>
#include <QVBoxLayout>

namespace hedit {
namespace {

/// 保持する出力の文字数の上限(1Mi文字)。超えたら古いものから捨てる。
constexpr int kMaximumHistoryCharacters = 1024 * 1024;

/// 出力が貯まったと知らされてから取り出すまでの時間(ミリ秒)。続けて届く出力を1回の描画にまとめる。
constexpr int kFlushDelay = 25;

/// Mayaの処理の途中(ファイルの読み込みなど、タイマーが動かない間)に、その場で描き直す最短の間隔(ミリ秒)。
/// 描き直しは同期で重いので、出力が続くほど間を空ける(進み具合は見える程度)。
/// 続いた時間が1秒未満なら100ms、3秒未満なら500ms、それ以上は1秒ごと。
constexpr int kImmediateRefreshInterval = 100;
constexpr int kBusyRefreshInterval = 500;
constexpr int kFloodRefreshInterval = 1000;

/// この時間より間を空けずに出力が来たら、「出力が続いている」とみなす(ミリ秒)。
constexpr int kBurstGap = 300;

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
    // タイマーが動いた = Mayaの処理が終わってイベントループへ戻った、なので「出力が続いている」状態を終える。
    flushTimer_.setSingleShot(true);
    flushTimer_.setInterval(kFlushDelay);
    connect(&flushTimer_, &QTimer::timeout, this, [this] {
        lastRequest_.invalidate();
        flush();
    });
}

void OutputPanel::scheduleFlush() {
    if (!takeOutput_ || !isVisible() || flushTimer_.isActive()) {
        return;  // 非表示ならshowEventで取り出す。予約済みなら、そのときにまとめて取り出す。
    }
    // 前回の取り出しから25ms以上経っていれば、すぐ取り出す(ドックの切り替えなどでイベントループが
    // 混んでいても、表示を遅らせない)。続けて届いている間は、残りの時間だけ待ってまとめる。
    const qint64 since = lastFlush_.isValid() ? lastFlush_.elapsed() : kFlushDelay;
    if (since >= kFlushDelay) {
        lastRequest_.invalidate();
        flush();
    } else {
        flushTimer_.start(int(kFlushDelay - since));
    }
}

void OutputPanel::showEvent(QShowEvent* event) {
    QWidget::showEvent(event);
    // 閉じている間の出力は取り込み側のキューに貯まっている(上限あり)。表示したときに1回で描く。
    lastRequest_.invalidate();
    flush();
}

void OutputPanel::flush() {
    if (!takeOutput_) {
        return;
    }
    const QList<OutputMessage> messages = takeOutput_();
    if (messages.isEmpty()) {
        return;
    }
    lastFlush_.restart();
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

int OutputPanel::immediateRefreshInterval() {
    // 前の出力から間が空いていれば、新しく続き始めたとみなす。
    if (!lastRequest_.isValid() || lastRequest_.elapsed() > kBurstGap) {
        burst_.restart();
    }
    lastRequest_.restart();
    const qint64 lasting = burst_.elapsed();
    if (lasting < 1000) {
        return kImmediateRefreshInterval;
    }
    return lasting < 3000 ? kBusyRefreshInterval : kFloodRefreshInterval;
}

void OutputPanel::refreshNow() {
    if (!isVisible()) {
        return;  // 出力欄を隠している間は描かない(表示したときにshowEventでまとめて取り出す)。
    }
    // 描画中に同じ関数が呼ばれた場合と、前回の描き直しから間隔(出力が続くほど長い)が経っていない場合は描かない
    // (その間の出力はキューに残り、次の描き直しか、イベントループへ戻った後の取り出しで反映される)。
    const int interval = immediateRefreshInterval();
    const bool tooSoon = lastRefresh_.isValid() && lastRefresh_.elapsed() < interval;
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

QList<OutputMessage> OutputPanel::shownTail(const QList<OutputMessage>& messages, bool* replaces) const {
    QList<OutputMessage> shown;
    for (const OutputMessage& message : messages) {
        if (accepts(message.kind)) {
            shown.append(message);
        }
    }
    *replaces = false;
    const int limit = view_->maximumBlockCount();
    if (limit <= 0) {
        return shown;
    }
    // 後ろから行を数え、表示の上限(5000行)を超える古い行を捨てる。どうせ追記の直後に消える行なので、
    // 最初から入れない(大量のエラーでは、文書への追記と上限での削除が出力欄の時間の大半を占めるため)。
    // 末尾の改行の後ろの空の行も1行(ブロック)に数えられるので、入れられる行は上限より1つ少ない。
    const int capacity = limit - 1;
    int lines = 0;
    for (int i = shown.size() - 1; i >= 0; --i) {
        const QString& text = shown[i].text;
        const int count = text.count('\n');
        if (lines + count < capacity) {
            lines += count;
            continue;
        }
        // この項目の、末尾から(入れられる行数 - 数えた行数)行だけを残す。
        const int keep = capacity - lines;
        int found = 0;
        int cut = 0;
        for (int position = text.size() - 1; position >= 0; --position) {
            if (text[position] == '\n' && found++ == keep) {
                cut = position + 1;
                break;
            }
        }
        shown[i].text = text.mid(cut);
        *replaces = true;
        return shown.mid(i);
    }
    return shown;
}

void OutputPanel::append(const QList<OutputMessage>& input) {
    // 新しい出力だけで上限の行数を超えるなら、今の表示は全て押し出される。古い行を1行ずつ消す代わりに先に空にする。
    bool replaces = false;
    const QList<OutputMessage> messages = shownTail(input, &replaces);
    if (replaces) {
        view_->clear();
    }
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
