/** @file marker_scroll_bar.cpp
 * @brief MarkerScrollBarの実装。
 */
#include "editor/marker_scroll_bar.h"
#include "editor/theme.h"
#include "editor/ui_scale.h"
#include <QPainter>
#include <QStyle>
#include <QStyleOptionSlider>

namespace hedit {

MarkerScrollBar::MarkerScrollBar(QWidget* parent) : QScrollBar(Qt::Vertical, parent) {
    setObjectName("markerScrollBar");
}

void MarkerScrollBar::setMarkers(const QList<Marker>& markers, int lineCount) {
    const int count = qMax(1, lineCount);
    bool same = count == lineCount_ && markers.size() == markers_.size();
    for (int i = 0; same && i < markers.size(); ++i) {
        same = markers[i].line == markers_[i].line && markers[i].lane == markers_[i].lane
               && markers[i].color == markers_[i].color;
    }
    if (same) {
        return;  // 同じ印なら、画像を作り直さない。
    }
    markers_ = markers;
    lineCount_ = count;
    cache_ = QPixmap();
    update();
}

void MarkerScrollBar::setCursorLine(int line) {
    if (line == cursorLine_) {
        return;
    }
    cursorLine_ = line;
    update();
}

void MarkerScrollBar::resizeEvent(QResizeEvent* event) {
    QScrollBar::resizeEvent(event);
    cache_ = QPixmap();  // 溝の高さが変わると、印の位置も変わる。
}

QRect MarkerScrollBar::groove() const {
    QStyleOptionSlider option;
    initStyleOption(&option);
    const QRect area = style()->subControlRect(QStyle::CC_ScrollBar, &option, QStyle::SC_ScrollBarGroove, this);
    return area.height() > 0 ? area : rect();
}

int MarkerScrollBar::markerY(int line, const QRect& area, int height) const {
    return area.top() + int(qint64(area.height() - height) * line / qMax(1, lineCount_ - 1));
}

void MarkerScrollBar::paintEvent(QPaintEvent* event) {
    QScrollBar::paintEvent(event);
    if (markers_.isEmpty() && cursorLine_ < 0) {
        return;
    }
    // 溝(つまみが動く範囲)の中に、行の割合で印を置く。
    const QRect area = groove();
    const int width = area.width();
    const int laneWidth = qMax(2, width / 3);
    const int height = qMax(2, scaled(2));
    QPainter painter(this);
    if (!markers_.isEmpty()) {
        if (cache_.isNull()) {
            // 部品と同じ大きさの透明な画像に、カーソル以外の印を描いておく(スクロールのたびに数千個を描かない)。
            const qreal ratio = devicePixelRatioF();
            cache_ = QPixmap(size() * ratio);
            cache_.setDevicePixelRatio(ratio);
            cache_.fill(Qt::transparent);
            QPainter cachePainter(&cache_);
            for (const Marker& marker : markers_) {
                const int y = markerY(marker.line, area, height);
                QRect mark;
                switch (marker.lane) {
                case 0:
                    mark = QRect(area.left(), y, laneWidth, height);
                    break;
                case 2:
                    mark = QRect(area.right() - laneWidth + 1, y, laneWidth, height);
                    break;
                case 3:
                    mark = QRect(area.left(), y, width, qMax(1, height / 2));
                    break;
                default:
                    mark = QRect(area.left() + laneWidth, y, qMax(2, width - laneWidth * 2), height);
                    break;
                }
                cachePainter.fillRect(mark, marker.color);
            }
        }
        painter.drawPixmap(0, 0, cache_);
    }
    if (cursorLine_ >= 0) {
        static const QColor cursorColor(theme::kScrollMarkerCursor);
        painter.fillRect(QRect(area.left(), markerY(cursorLine_, area, height), width, qMax(1, height / 2)), cursorColor);
    }
}

}  // namespace hedit
