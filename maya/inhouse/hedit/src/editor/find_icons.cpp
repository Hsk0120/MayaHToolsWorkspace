/** @file find_icons.cpp
 * @brief 検索バーのアイコンを描く。
 * @details どのアイコンも、16×16の方眼に描いてから指定の大きさへ拡大する(VS Codeのcodiconと同じ16の方眼)。
 * 線の太さは1目盛り。QPainterPathやdrawLineの座標は、この方眼の上での位置。
 */
#include "editor/find_icons.h"
#include <QFont>
#include <QPainter>
#include <QPainterPath>
#include <QPixmap>

namespace hedit {
namespace {

/** @brief 方眼の中の四角い範囲に、文字を中央そろえで描く。
 * @param painter 描く先。
 * @param rect 方眼の上の範囲。
 * @param text 文字。
 * @param pixels 方眼の上での文字の大きさ。
 * @param bold trueなら太字。
 */
void drawLabel(QPainter& painter, const QRectF& rect, const QString& text, int pixels, bool bold = false) {
    QFont font("Segoe UI");
    font.setPixelSize(pixels);
    font.setBold(bold);
    painter.setFont(font);
    painter.drawText(rect, Qt::AlignCenter, text);
}

/** @brief 折れ線を描く。 @param painter 描く先。 @param points 方眼の上の点。 */
void drawPolyline(QPainter& painter, std::initializer_list<QPointF> points) {
    QPainterPath path;
    bool first = true;
    for (const QPointF& point : points) {
        if (first) {
            path.moveTo(point);
            first = false;
        } else {
            path.lineTo(point);
        }
    }
    painter.drawPath(path);
}

/** @brief 置換のアイコンに共通の、右上の文字から左へ伸びて下の箱を指す矢印を描く。
 * @param painter 描く先。
 * @param right 横線の右端(方眼の上のx)。
 */
void drawReplaceArrow(QPainter& painter, double right) {
    drawPolyline(painter, {{right, 4.5}, {3.5, 4.5}, {3.5, 7.5}});
    drawPolyline(painter, {{2.0, 6.0}, {3.5, 7.5}, {5.0, 6.0}});
}

/** @brief 塗りつぶした箱を描き、文字の形に穴をあける(VS Codeの置換アイコンの下の箱)。
 * @param painter 描く先。
 * @param box 方眼の上の箱の範囲。
 * @param color 箱の色。
 * @param text 穴にする文字。
 * @param pixels 方眼の上での文字の大きさ。
 */
void drawKnockoutBox(QPainter& painter, const QRectF& box, const QColor& color, const QString& text, int pixels) {
    painter.save();
    painter.setPen(Qt::NoPen);
    painter.setBrush(color);
    painter.drawRoundedRect(box, 1.0, 1.0);
    // Clearで描いた部分は透明になる。アイコンの後ろの背景が文字の形に見える。
    painter.setCompositionMode(QPainter::CompositionMode_Clear);
    painter.setPen(Qt::black);
    drawLabel(painter, box.adjusted(0, -0.5, 0, -0.5), text, pixels, true);
    painter.restore();
}

}  // namespace

QIcon findIcon(FindIcon icon, const QColor& color, int size) {
    QPixmap pixmap(size, size);
    pixmap.fill(Qt::transparent);
    QPainter painter(&pixmap);
    painter.setRenderHint(QPainter::Antialiasing, true);
    painter.setRenderHint(QPainter::TextAntialiasing, true);
    painter.scale(size / 16.0, size / 16.0);
    // 線の太さは1目盛り(16pxのとき1px)。拡大すると、線も同じ割合で太くなる。
    QPen pen(color, 1.0, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin);
    painter.setPen(pen);
    painter.setBrush(Qt::NoBrush);

    switch (icon) {
    case FindIcon::ChevronRight:
        drawPolyline(painter, {{6.0, 3.5}, {10.5, 8.0}, {6.0, 12.5}});
        break;
    case FindIcon::ChevronDown:
        drawPolyline(painter, {{3.5, 6.0}, {8.0, 10.5}, {12.5, 6.0}});
        break;
    case FindIcon::ArrowUp:
        painter.drawLine(QPointF(8.0, 3.0), QPointF(8.0, 13.5));
        drawPolyline(painter, {{3.5, 7.5}, {8.0, 3.0}, {12.5, 7.5}});
        break;
    case FindIcon::ArrowDown:
        painter.drawLine(QPointF(8.0, 2.5), QPointF(8.0, 13.0));
        drawPolyline(painter, {{3.5, 8.5}, {8.0, 13.0}, {12.5, 8.5}});
        break;
    case FindIcon::Selection:
        painter.drawLine(QPointF(2.0, 4.5), QPointF(14.0, 4.5));
        painter.drawLine(QPointF(2.0, 8.0), QPointF(14.0, 8.0));
        painter.drawLine(QPointF(2.0, 11.5), QPointF(10.0, 11.5));
        break;
    case FindIcon::Close:
        painter.drawLine(QPointF(3.5, 3.5), QPointF(12.5, 12.5));
        painter.drawLine(QPointF(12.5, 3.5), QPointF(3.5, 12.5));
        break;
    case FindIcon::MatchCase:
        painter.setPen(color);
        drawLabel(painter, QRectF(0, -0.5, 16, 16), "Aa", 12);
        break;
    case FindIcon::WholeWord:
        painter.setPen(color);
        drawLabel(painter, QRectF(0, -2.0, 16, 14), "ab", 12);
        painter.setPen(pen);
        drawPolyline(painter, {{1.0, 11.0}, {1.0, 13.5}, {15.0, 13.5}, {15.0, 11.0}});
        break;
    case FindIcon::Regex:
        painter.setPen(Qt::NoPen);
        painter.setBrush(color);
        painter.drawRect(QRectF(2.5, 10.5, 2.5, 2.5));  // 点
        painter.setBrush(Qt::NoBrush);
        painter.setPen(pen);
        // 星(*): 縦線と、斜めの2本。
        painter.drawLine(QPointF(10.5, 2.0), QPointF(10.5, 9.0));
        painter.drawLine(QPointF(7.5, 3.75), QPointF(13.5, 7.25));
        painter.drawLine(QPointF(13.5, 3.75), QPointF(7.5, 7.25));
        break;
    case FindIcon::PreserveCase:
        painter.setPen(color);
        drawLabel(painter, QRectF(0, -0.5, 16, 16), "AB", 11);
        break;
    case FindIcon::Replace:
        // 右上の「b」を、左下の箱「c」へ置き換える、という絵。
        painter.setPen(color);
        drawLabel(painter, QRectF(8.5, -0.5, 7.0, 8.0), "b", 9);
        painter.setPen(pen);
        drawReplaceArrow(painter, 8.0);
        drawKnockoutBox(painter, QRectF(1.5, 9.0, 7.5, 6.5), color, "c", 8);
        break;
    case FindIcon::ReplaceAll:
        // 置換と同じ絵で、箱を2つ重ねて「全て」を表す。
        painter.setPen(color);
        drawLabel(painter, QRectF(6.5, -0.5, 9.5, 8.0), "ab", 8);
        painter.setPen(pen);
        drawReplaceArrow(painter, 6.5);
        // 奥の箱は、手前の箱に隠れない上と右の辺だけを描く。
        drawPolyline(painter, {{4.5, 7.5}, {14.5, 7.5}, {14.5, 13.5}});
        drawKnockoutBox(painter, QRectF(1.5, 9.0, 11.0, 6.5), color, "ac", 7);
        break;
    }
    painter.end();
    return QIcon(pixmap);
}

}  // namespace hedit
