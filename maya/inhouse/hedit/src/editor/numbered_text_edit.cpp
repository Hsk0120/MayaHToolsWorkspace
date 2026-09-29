/** @file numbered_text_edit.cpp
 * @brief NumberedTextEditの実装。
 */
#include "editor/numbered_text_edit.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QPainter>
#include <QTextBlock>

namespace hedit {

NumberedTextEdit::NumberedTextEdit(QWidget* parent) : QPlainTextEdit(parent) {
    // connectの3番目の引数(this)は「接続の持ち主」。thisが破棄されると接続も自動で外れる。
    // 行数が変われば桁数が変わるので幅を計算し直す。
    connect(this, &QPlainTextEdit::blockCountChanged, this, [this] { updateGutter(); });
    // スクロールや入力で本文が描き直されるとき、行番号も描き直す。
    connect(this, &QPlainTextEdit::updateRequest, this, [this] { update(); });
    updateGutter();
}

void NumberedTextEdit::setLineNumbersVisible(bool visible) {
    showLineNumbers_ = visible;
    updateGutter();
}

bool NumberedTextEdit::event(QEvent* event) {
    if (event->type() == QEvent::FontChange) {
        // 先に基底クラスで新しいフォントを反映してから、その文字幅で計算し直す。
        const bool handled = QPlainTextEdit::event(event);
        updateGutter();
        return handled;
    }
    if (event->type() == QEvent::Paint && showLineNumbers_) {
        paintLineNumbers();
    }
    return QPlainTextEdit::event(event);
}

void NumberedTextEdit::updateGutter() {
    if (showLineNumbers_) {
        const int digits = QString::number(qMax(1, blockCount())).size();
        const int textWidth = fontMetrics().horizontalAdvance('9') * digits + scaled(20);
        gutterWidth_ = qMax(scaled(44), textWidth);
    } else {
        gutterWidth_ = 0;
    }
    setViewportMargins(gutterWidth_, 0, 0, 0);
    // タブ文字の幅は空白4文字分。
    setTabStopDistance(fontMetrics().horizontalAdvance(' ') * 4);
    update();
}

void NumberedTextEdit::paintLineNumbers() {
    // 本文の描画(viewport)とは別に、このウィジェット自身の左端の余白へ描く。
    QPainter painter(this);
    painter.fillRect(0, 0, gutterWidth_, height(), QColor(theme::kBackground));
    painter.setPen(QColor(theme::kLineNumber));
    painter.setFont(font());
    QTextBlock block = firstVisibleBlock();
    while (block.isValid()) {
        const QRectF rect = blockBoundingGeometry(block).translated(contentOffset());
        if (rect.top() > height()) {
            break;
        }
        if (block.isVisible()) {
            const QRectF numberArea(0, rect.top(), gutterWidth_ - scaled(10), fontMetrics().height());
            painter.drawText(numberArea, Qt::AlignRight, QString::number(block.blockNumber() + 1));
        }
        block = block.next();
    }
}

}  // namespace hedit
