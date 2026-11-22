"""Skin Weight Kit のアイコンを、画像ファイルを使わずに QPainter で描く。

絵は、紫の角丸四角の上に、腕の形(カプセル)を関節を境に明るい色から濃い色へ4段に塗り分けたもの
(ウェイトの色分け)。元データは ``SkinWeightKit/icons/skinWeightKit.svg`` で、同じ 24×24 の座標で描く。
"""

from .qt import QtCore, QtGui

#: アイコンの色。BANDS は腕の塗り分け(左から右)。
BACKGROUND = "#9b7fe6"
OUTLINE = "#241a45"
BANDS = ("#f3edff", "#cdbdf7", "#5a43a8", "#241a45")

_cache = {}


def _draw(painter):
    """24×24 の座標にアイコンを描く。"""
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QColor(BACKGROUND))
    painter.drawRoundedRect(QtCore.QRectF(1, 1, 22, 22), 4, 4)
    capsule = QtGui.QPainterPath()
    capsule.addRoundedRect(QtCore.QRectF(4, 8, 16, 8), 4, 4)
    painter.save()
    painter.setClipPath(capsule)
    for index, name in enumerate(BANDS):
        painter.fillRect(QtCore.QRectF(4 + index * 4, 8, 4, 8), QtGui.QColor(name))
    painter.restore()
    painter.setPen(QtGui.QPen(QtGui.QColor(OUTLINE), 1.4))
    painter.setBrush(QtCore.Qt.NoBrush)
    painter.drawPath(capsule)
    # 関節(塗り分けの中央)。
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QColor(OUTLINE))
    painter.drawEllipse(QtCore.QPointF(12, 12), 1.7, 1.7)


def pixmap(size=24):
    """アイコンの画像を返す。

    Args:
        size (int): 一辺の大きさ(px)。

    Returns:
        QtGui.QPixmap: 画像。
    """
    result = QtGui.QPixmap(size, size)
    result.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(result)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.scale(size / 24.0, size / 24.0)
    _draw(painter)
    painter.end()
    return result


def icon():
    """Skin Weight Kit のアイコンを返す(作ったものは使い回す)。

    Returns:
        QtGui.QIcon: 16〜48px の画像を持つアイコン。
    """
    if "icon" not in _cache:
        result = QtGui.QIcon()
        for size in (16, 20, 24, 32, 48):
            result.addPixmap(pixmap(size))
        _cache["icon"] = result
    return _cache["icon"]
