/** @file numbered_text_edit.cpp
 * @brief NumberedTextEditと、行番号専用の部品LineNumberAreaの実装。
 */
#include "editor/numbered_text_edit.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QMouseEvent>
#include <QPainter>
#include <QTextBlock>

namespace hedit {

/** @brief 行番号だけを描く部品。描く中身はNumberedTextEditに任せる。
 * @details このファイルの中だけで使う。NumberedTextEditの子として作り、一緒に破棄される。
 */
class LineNumberArea : public QWidget {
public:
    /** @brief 行番号の部品を作る。 @param editor 行番号を描く対象の欄(親)。 */
    explicit LineNumberArea(NumberedTextEdit* editor) : QWidget(editor), editor_(editor) {}

    /** @brief 望ましい大きさ。 @return 行番号の欄の幅。 */
    QSize sizeHint() const override { return QSize(editor_->gutterWidth(), 0); }

protected:
    /** @brief 行番号を描く。 @param event 描き直す範囲。 */
    void paintEvent(QPaintEvent* event) override { editor_->paintLineNumbers(event); }

    /** @brief クリックを欄の持ち主へ知らせる(折りたたみの矢印)。 @param event マウスの操作。 */
    void mousePressEvent(QMouseEvent* event) override { editor_->gutterPressed(event->pos()); }

private:
    NumberedTextEdit* editor_;  ///< 親の欄。
};

NumberedTextEdit::NumberedTextEdit(QWidget* parent) : QPlainTextEdit(parent) {
    lineNumberArea_ = new LineNumberArea(this);
    // connectの3番目の引数(this)は「接続の持ち主」。thisが破棄されると接続も自動で外れる。
    // 行数が変われば桁数が変わるので幅を計算し直す。
    connect(this, &QPlainTextEdit::blockCountChanged, this, [this] { updateGutter(); });
    // 本文の描き直し(スクロール・入力・カーソルの点滅)に合わせて、行番号の必要な範囲だけ描き直す。
    connect(this, &QPlainTextEdit::updateRequest, this, [this](const QRect& rect, int dy) { onUpdateRequest(rect, dy); });
    updateGutter();
}

QWidget* NumberedTextEdit::gutter() const {
    return lineNumberArea_;
}

void NumberedTextEdit::paintGutterBlock(QPainter&, const QTextBlock&, const QRectF&) {}

void NumberedTextEdit::paintGutterOverlay(QPainter&, const QRect&) {}

void NumberedTextEdit::gutterPressed(const QPoint&) {}

void NumberedTextEdit::setLineNumbersVisible(bool visible) {
    showLineNumbers_ = visible;
    lineNumberArea_->setVisible(visible);
    updateGutter();
}

bool NumberedTextEdit::event(QEvent* event) {
    if (event->type() == QEvent::FontChange) {
        // 先に基底クラスで新しいフォントを反映してから、その文字幅で計算し直す。
        const bool handled = QPlainTextEdit::event(event);
        updateGutter();
        return handled;
    }
    return QPlainTextEdit::event(event);
}

void NumberedTextEdit::resizeEvent(QResizeEvent* event) {
    QPlainTextEdit::resizeEvent(event);
    const QRect area = contentsRect();
    lineNumberArea_->setGeometry(QRect(area.left(), area.top(), gutterWidth_, area.height()));
}

void NumberedTextEdit::updateGutter() {
    if (showLineNumbers_) {
        const int digits = QString::number(qMax(1, blockCount())).size();
        const int textWidth = fontMetrics().horizontalAdvance('9') * digits + scaled(20);
        numberWidth_ = qMax(scaled(44), textWidth);
        gutterWidth_ = numberWidth_ + extraGutterWidth();
    } else {
        numberWidth_ = 0;
        gutterWidth_ = 0;
    }
    setViewportMargins(gutterWidth_, 0, 0, 0);
    // タブ文字の幅は空白4文字分。
    setTabStopDistance(fontMetrics().horizontalAdvance(' ') * 4);
    const QRect area = contentsRect();
    lineNumberArea_->setGeometry(QRect(area.left(), area.top(), gutterWidth_, area.height()));
    lineNumberArea_->update();
}

void NumberedTextEdit::onUpdateRequest(const QRect& rect, int dy) {
    if (!showLineNumbers_) {
        return;
    }
    if (dy != 0) {
        lineNumberArea_->scroll(0, dy);  // スクロールした分だけ、描いた番号をずらす(描き直しを減らす)。
    } else {
        lineNumberArea_->update(0, rect.y(), lineNumberArea_->width(), rect.height());
    }
}

void NumberedTextEdit::paintLineNumbers(QPaintEvent* event) {
    QPainter painter(lineNumberArea_);
    painter.fillRect(event->rect(), QColor(theme::kBackground));
    painter.setPen(QColor(theme::kLineNumber));
    painter.setFont(font());
    QTextBlock block = firstVisibleBlock();
    while (block.isValid()) {
        const QRectF rect = blockBoundingGeometry(block).translated(contentOffset());
        if (rect.top() > event->rect().bottom()) {
            break;  // 描き直す範囲より下は描かない。
        }
        if (block.isVisible() && rect.bottom() >= event->rect().top()) {
            const QRectF numberArea(0, rect.top(), numberWidth_ - scaled(10), fontMetrics().height());
            painter.setPen(QColor(theme::kLineNumber));
            painter.drawText(numberArea, Qt::AlignRight, QString::number(block.blockNumber() + 1));
            paintGutterBlock(painter, block, QRectF(0, rect.top(), gutterWidth_, rect.height()));
        }
        block = block.next();
    }
    paintGutterOverlay(painter, event->rect());
}

}  // namespace hedit
