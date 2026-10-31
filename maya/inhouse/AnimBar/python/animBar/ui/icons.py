"""Anim Bar のアイコンを、画像ファイルを使わずに QPainter で描く。

色は :data:`PALETTE` の独自の配色で、どのアイコンも 24px の正方形に線と面の単純な図形で描く。
"""

import functools
import math

from .qt import QtCore, QtGui

#: バーで使う色。
PALETTE = {
    "background": "#1f2328",
    "panel": "#2a3038",
    "line": "#3a424d",
    "text": "#d8dee6",
    "muted": "#8a95a3",
    "teal": "#37b3a6",
    "amber": "#f0a33a",
    "coral": "#e2624a",
    "violet": "#9a7be0",
    "sky": "#4f9ee8",
    "lime": "#8cc152",
}

#: 選択セットの色(selectSets.COLOR_COUNT と同じ数)。
SET_COLORS = ("#37b3a6", "#f0a33a", "#e2624a", "#9a7be0", "#4f9ee8", "#8cc152", "#e66ea6", "#c7c7c7")

_cache = {}


def color(name):
    """パレットの色を返す。

    Args:
        name (str): :data:`PALETTE` の名前、または ``#rrggbb``。

    Returns:
        QtGui.QColor: 色。
    """
    return QtGui.QColor(PALETTE.get(name, name))


def icon(name, size=24):
    """名前のアイコンを返す(作ったものは使い回す)。

    Args:
        name (str): :data:`_DRAW` の名前。
        size (int): 一辺の大きさ(px)。

    Returns:
        QtGui.QIcon: アイコン。
    """
    key = (name, size)
    if key not in _cache:
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.scale(size / 24.0, size / 24.0)
        _DRAW.get(name, _draw_dot)(painter)
        painter.end()
        _cache[key] = QtGui.QIcon(pixmap)
    return _cache[key]


def _pen(painter, name, width=2.0):
    """線の色と太さを設定する。"""
    pen = QtGui.QPen(color(name), width)
    pen.setCapStyle(QtCore.Qt.RoundCap)
    pen.setJoinStyle(QtCore.Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.NoBrush)


def _fill(painter, name):
    """面の色を設定する(線なし)。"""
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(color(name))


def _draw_dot(painter):
    """不明なアイコンの代わりの点。"""
    _fill(painter, "muted")
    painter.drawEllipse(QtCore.QPointF(12, 12), 3, 3)


def _keys(painter, xs, ys, accent="teal"):
    """キーの菱形を並べて描く。"""
    for x, y in zip(xs, ys):
        _fill(painter, accent)
        painter.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(x, y - 3.5), QtCore.QPointF(x + 3.5, y),
                                             QtCore.QPointF(x, y + 3.5), QtCore.QPointF(x - 3.5, y)]))


def _curve(painter, points, name="muted", width=1.6):
    """点を結ぶ折れ線を描く。"""
    _pen(painter, name, width)
    path = QtGui.QPainterPath(QtCore.QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(QtCore.QPointF(*point))
    painter.drawPath(path)


def _arrow(painter, x1, y1, x2, y2, name="text"):
    """矢印を描く。"""
    _pen(painter, name, 2)
    painter.drawLine(QtCore.QPointF(x1, y1), QtCore.QPointF(x2, y2))
    angle = math.atan2(y2 - y1, x2 - x1)
    for side in (-0.6, 0.6):
        painter.drawLine(QtCore.QPointF(x2, y2), QtCore.QPointF(x2 - 4 * math.cos(angle + side),
                                                               y2 - 4 * math.sin(angle + side)))


def _tangent(painter, shape):
    """接線の形を描く(曲線の上にキー)。"""
    shapes = {
        "auto": [(3, 18), (8, 9), (12, 7), (16, 9), (21, 18)],
        "spline": [(3, 17), (7, 10), (12, 6), (17, 10), (21, 17)],
        "linear": [(3, 19), (12, 6), (21, 19)],
        "flat": [(3, 12), (21, 12)],
        "step": [(3, 17), (12, 17), (12, 7), (21, 7)],
        "clamped": [(3, 18), (9, 8), (12, 7), (15, 8), (21, 18)],
        "plateau": [(3, 18), (8, 7), (16, 7), (21, 18)],
        "flow": [(3, 19), (8, 13), (12, 11), (16, 9), (21, 4)],
        "bounce": [(3, 18), (7, 7), (11, 18), (15, 9), (21, 18)],
    }
    _curve(painter, shapes[shape], "sky", 2)
    _keys(painter, [12], [shapes[shape][len(shapes[shape]) // 2][1]], "amber")


def _draw_tween(painter):
    """前後のキーと中間のキー。"""
    _curve(painter, [(4, 17), (20, 7)])
    _keys(painter, [4, 20], [17, 7], "muted")
    _keys(painter, [12], [12], "teal")


def _draw_key_previous(painter):
    """前のキーを写す。"""
    _keys(painter, [6, 18], [12, 12], "muted")
    _arrow(painter, 10, 12, 15, 12, "teal")


def _draw_key_next(painter):
    """後ろのキーを写す。"""
    _keys(painter, [6, 18], [12, 12], "muted")
    _arrow(painter, 14, 12, 9, 12, "teal")


def _draw_nudge_left(painter):
    """キーを前へ。"""
    _keys(painter, [16], [12], "amber")
    _arrow(painter, 11, 12, 3, 12)


def _draw_nudge_right(painter):
    """キーを後ろへ。"""
    _keys(painter, [8], [12], "amber")
    _arrow(painter, 13, 12, 21, 12)


def _draw_insert(painter):
    """間を空ける。"""
    _pen(painter, "muted", 2)
    painter.drawLine(QtCore.QPointF(12, 4), QtCore.QPointF(12, 20))
    _arrow(painter, 10, 12, 3, 12, "teal")
    _arrow(painter, 14, 12, 21, 12, "teal")


def _draw_remove(painter):
    """間を詰める。"""
    _pen(painter, "muted", 2)
    painter.drawLine(QtCore.QPointF(12, 4), QtCore.QPointF(12, 20))
    _arrow(painter, 3, 12, 9, 12, "coral")
    _arrow(painter, 21, 12, 15, 12, "coral")


def _draw_share(painter):
    """キーをそろえる。"""
    _keys(painter, [6, 12, 18], [8, 8, 8], "teal")
    _keys(painter, [6, 12, 18], [16, 16, 16], "violet")


def _draw_reset(painter):
    """既定値へ戻す。"""
    _pen(painter, "amber", 2)
    painter.drawArc(QtCore.QRectF(5, 5, 14, 14), 40 * 16, 280 * 16)
    _arrow(painter, 17, 6, 18, 10, "amber")


def _draw_mirror(painter):
    """左右へ写す。"""
    _pen(painter, "muted", 1.5)
    painter.drawLine(QtCore.QPointF(12, 3), QtCore.QPointF(12, 21))
    _fill(painter, "violet")
    painter.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(10, 6), QtCore.QPointF(10, 18), QtCore.QPointF(4, 12)]))
    _pen(painter, "violet", 1.5)
    painter.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(14, 6), QtCore.QPointF(14, 18), QtCore.QPointF(20, 12)]))


def _draw_flip(painter):
    """左右を入れ替える。"""
    _arrow(painter, 4, 9, 20, 9, "violet")
    _arrow(painter, 20, 15, 4, 15, "violet")


def _draw_transform_all(painter):
    """全キーへ反映。"""
    _keys(painter, [5, 12, 19], [15, 15, 15], "muted")
    _keys(painter, [5, 12, 19], [8, 8, 8], "teal")


def _draw_copy(painter):
    """コピー。"""
    _pen(painter, "text", 1.6)
    painter.drawRoundedRect(QtCore.QRectF(4, 7, 11, 13), 2, 2)
    painter.drawRoundedRect(QtCore.QRectF(9, 3, 11, 13), 2, 2)


def _draw_paste(painter):
    """貼付け。"""
    _pen(painter, "text", 1.6)
    painter.drawRoundedRect(QtCore.QRectF(5, 5, 14, 16), 2, 2)
    _fill(painter, "teal")
    painter.drawRect(QtCore.QRectF(9, 3, 6, 4))


def _draw_align(painter):
    """位置合わせ。"""
    _pen(painter, "sky", 2)
    painter.drawEllipse(QtCore.QPointF(15, 12), 5, 5)
    _fill(painter, "amber")
    painter.drawEllipse(QtCore.QPointF(7, 12), 3, 3)
    _arrow(painter, 9, 12, 13, 12, "text")


def _draw_space(painter):
    """スペース切替。"""
    _pen(painter, "muted", 1.5)
    painter.drawRect(QtCore.QRectF(3, 4, 8, 8))
    painter.drawRect(QtCore.QRectF(13, 12, 8, 8))
    _arrow(painter, 8, 15, 12, 15, "teal")
    _fill(painter, "teal")
    painter.drawEllipse(QtCore.QPointF(7, 8), 2, 2)


def _draw_pivot(painter):
    """仮のピボット。"""
    _pen(painter, "coral", 2)
    painter.drawLine(QtCore.QPointF(12, 4), QtCore.QPointF(12, 20))
    painter.drawLine(QtCore.QPointF(4, 12), QtCore.QPointF(20, 12))
    painter.drawEllipse(QtCore.QPointF(12, 12), 4, 4)


def _draw_follow(painter):
    """仮のコンストレイント。"""
    _pen(painter, "violet", 1.8)
    painter.drawEllipse(QtCore.QPointF(7, 12), 4, 4)
    painter.drawEllipse(QtCore.QPointF(17, 12), 4, 4)
    painter.drawLine(QtCore.QPointF(11, 12), QtCore.QPointF(13, 12))


def _draw_trail(painter):
    """モーショントレイル。"""
    _pen(painter, "sky", 1.5)
    path = QtGui.QPainterPath(QtCore.QPointF(3, 18))
    path.cubicTo(QtCore.QPointF(8, 3), QtCore.QPointF(15, 21), QtCore.QPointF(21, 6))
    painter.drawPath(path)
    for x, y in ((3, 18), (9, 10), (15, 13), (21, 6)):
        _fill(painter, "amber")
        painter.drawEllipse(QtCore.QPointF(x, y), 1.6, 1.6)


def _draw_micro(painter):
    """細かい移動。"""
    _arrow(painter, 6, 18, 12, 12, "lime")
    _pen(painter, "lime", 1.2)
    painter.drawRect(QtCore.QRectF(13, 5, 6, 6))


def _draw_tumble(painter):
    """選んだものの周りで回す。"""
    _pen(painter, "sky", 1.8)
    painter.drawArc(QtCore.QRectF(4, 6, 16, 12), 20 * 16, 300 * 16)
    _fill(painter, "amber")
    painter.drawEllipse(QtCore.QPointF(12, 12), 2.5, 2.5)


def _draw_recovery(painter):
    """アニメーションの退避。"""
    _pen(painter, "lime", 1.8)
    painter.drawRoundedRect(QtCore.QRectF(5, 4, 14, 16), 2, 2)
    painter.drawLine(QtCore.QPointF(9, 9), QtCore.QPointF(15, 9))
    _keys(painter, [12], [15], "lime")


def _draw_range(painter):
    """再生範囲。"""
    _pen(painter, "muted", 2)
    painter.drawLine(QtCore.QPointF(3, 16), QtCore.QPointF(21, 16))
    _fill(painter, "amber")
    painter.drawRect(QtCore.QRectF(6, 12, 12, 4))


def _draw_jump_previous(painter):
    """前のキーへ。"""
    _keys(painter, [6], [12], "teal")
    _arrow(painter, 20, 12, 11, 12)


def _draw_jump_next(painter):
    """後ろのキーへ。"""
    _keys(painter, [18], [12], "teal")
    _arrow(painter, 4, 12, 13, 12)


def _draw_playblast(painter):
    """プレイブラスト。"""
    _pen(painter, "text", 1.6)
    painter.drawRoundedRect(QtCore.QRectF(3, 6, 14, 12), 2, 2)
    _fill(painter, "coral")
    painter.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(17, 9), QtCore.QPointF(21, 6), QtCore.QPointF(21, 18),
                                         QtCore.QPointF(17, 15)]))


def _draw_add(painter):
    """足す。"""
    _pen(painter, "teal", 2.4)
    painter.drawLine(QtCore.QPointF(12, 6), QtCore.QPointF(12, 18))
    painter.drawLine(QtCore.QPointF(6, 12), QtCore.QPointF(18, 12))


def _draw_minus(painter):
    """引く。"""
    _pen(painter, "coral", 2.4)
    painter.drawLine(QtCore.QPointF(6, 12), QtCore.QPointF(18, 12))


def _draw_menu(painter):
    """メニュー。"""
    _fill(painter, "muted")
    for y in (7, 12, 17):
        painter.drawEllipse(QtCore.QPointF(12, y), 1.8, 1.8)


#: アイコンの名前と描く関数。
_DRAW = {
    "tween": _draw_tween, "keyPrevious": _draw_key_previous, "keyNext": _draw_key_next,
    "nudgeLeft": _draw_nudge_left, "nudgeRight": _draw_nudge_right, "insert": _draw_insert,
    "remove": _draw_remove, "share": _draw_share, "reset": _draw_reset, "mirror": _draw_mirror,
    "flip": _draw_flip, "transformAll": _draw_transform_all, "copy": _draw_copy, "paste": _draw_paste,
    "align": _draw_align, "space": _draw_space, "pivot": _draw_pivot, "follow": _draw_follow,
    "trail": _draw_trail, "micro": _draw_micro, "tumble": _draw_tumble, "recovery": _draw_recovery,
    "range": _draw_range, "jumpPrevious": _draw_jump_previous, "jumpNext": _draw_jump_next,
    "playblast": _draw_playblast, "add": _draw_add, "minus": _draw_minus, "menu": _draw_menu,
}
for _shape in ("auto", "spline", "linear", "flat", "step", "clamped", "plateau", "flow", "bounce"):
    _DRAW["tangent_" + _shape] = functools.partial(_tangent, shape=_shape)
