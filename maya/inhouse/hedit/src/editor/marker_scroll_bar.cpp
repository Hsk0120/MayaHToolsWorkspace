/** @file marker_scroll_bar.cpp
 * @brief MarkerScrollBarの実装。
 */
#include "editor/marker_scroll_bar.h"
#include "editor/ui_scale.h"
#include <QPainter>
#include <QStyle>
#include <QStyleOptionSlider>

namespace hedit {

MarkerScrollBar::MarkerScrollBar(QWidget* parent) : QScrollBar(Qt::Vertical, parent) {
    setObjectName("markerScrollBar");
}

void MarkerScrollBar::setMarkers(const QList<Marker>& markers, int lineCount) {
    markers_ = markers;
    lineCount_ = qMax(1, lineCount);
    update();
}

void MarkerScrollBar::paintEvent(QPaintEvent* event) {
    QScrollBar::paintEvent(event);
    if (markers_.isEmpty()) {
        return;
    }
    // 溝(つまみが動く範囲)の中に、行の割合で印を置く。
    QStyleOptionSlider option;
    initStyleOption(&option);
    QRect groove = style()->subControlRect(QStyle::CC_ScrollBar, &option, QStyle::SC_ScrollBarGroove, this);
    if (groove.height() <= 0) {
        groove = rect();
    }
    QPainter painter(this);
    const int width = groove.width();
    const int laneWidth = qMax(2, width / 3);
    const int height = qMax(2, scaled(2));
    for (const Marker& marker : markers_) {
        const int y = groove.top() + int(qint64(groove.height() - height) * marker.line / qMax(1, lineCount_ - 1));
        QRect mark;
        switch (marker.lane) {
        case 0:
            mark = QRect(groove.left(), y, laneWidth, height);
            break;
        case 2:
            mark = QRect(groove.right() - laneWidth + 1, y, laneWidth, height);
            break;
        case 3:
            mark = QRect(groove.left(), y, width, qMax(1, height / 2));
            break;
        default:
            mark = QRect(groove.left() + laneWidth, y, qMax(2, width - laneWidth * 2), height);
            break;
        }
        painter.fillRect(mark, marker.color);
    }
}

}  // namespace hedit
