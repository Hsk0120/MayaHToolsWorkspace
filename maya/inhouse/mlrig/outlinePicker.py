"""表示輪郭とクリック領域を個別の線形カーブで指定するXYピッカー。"""

from maya import cmds, OpenMayaUI
from maya.api import OpenMaya as om2

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance


def _outline(node):
    """線形カーブのCVをワールドXY平面に投影した閉パスを返す。"""
    shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True, fullPath=True, type="nurbsCurve") or []
    if len(shapes) != 1 or cmds.getAttr(shapes[0] + ".degree") != 1:
        raise ValueError("輪郭には1本の線形カーブを指定してください")
    coords = cmds.xform(shapes[0] + ".cv[*]", query=True, translation=True, worldSpace=True)
    points = list(zip(coords[::3], coords[1::3]))
    if len(set(points)) < 3:
        raise ValueError("XY平面に異なる3点以上が必要です")
    path = QtGui.QPainterPath()
    path.moveTo(points[0][0], -points[0][1])
    for x, y in points[1:]:
        path.lineTo(x, -y)
    path.closeSubpath()
    return path


class _Region(QtWidgets.QGraphicsPathItem):
    """独立した命中領域を持ち、クリック時に登録対象を選択する。"""

    def __init__(self, display, hit, target):
        super().__init__(display)
        self.hit = hit
        self.target = target
        self.setBrush(QtGui.QColor(70, 120, 145))
        self.setPen(QtGui.QPen(QtCore.Qt.NoPen))

    def shape(self):
        return self.hit

    def boundingRect(self):
        return self.path().boundingRect().united(self.hit.boundingRect())

    def mousePressEvent(self, event):
        if self.target.isValid():
            node = self.target.fullPathName()
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                cmds.select(node, add=True)
            else:
                cmds.select(node, replace=True)
        event.accept()


def show():
    """現在のウィンドウに複数の輪郭を登録し、クリックで対象を選択する。"""
    parent = wrapInstance(int(OpenMayaUI.MQtUtil.mainWindow()), QtWidgets.QWidget)
    window = QtWidgets.QDialog(parent)
    window.setAttribute(QtCore.Qt.WA_DeleteOnClose)
    window.setWindowTitle("輪郭ピッカー")
    layout = QtWidgets.QVBoxLayout(window)
    button = QtWidgets.QPushButton("対象・表示輪郭・クリック輪郭の順に選んで追加")
    layout.addWidget(button)
    scene = QtWidgets.QGraphicsScene(window)
    view = QtWidgets.QGraphicsView(scene)
    layout.addWidget(view)
    status = QtWidgets.QLabel("Shift＋クリックで選択に追加")
    layout.addWidget(status)

    def add():
        nodes = cmds.ls(selection=True, long=True, transforms=True) or []
        try:
            if len(nodes) != 3:
                raise ValueError("対象・表示輪郭・クリック輪郭の3つを選んでください")
            item = _Region(_outline(nodes[1]), _outline(nodes[2]), om2.MSelectionList().add(nodes[0]).getDagPath(0))
        except ValueError as exc:
            status.setText(str(exc))
            return
        scene.addItem(item)
        item.setToolTip(nodes[0])
        view.fitInView(scene.itemsBoundingRect(), QtCore.Qt.KeepAspectRatio)
        status.setText("Shift＋クリックで選択に追加")

    button.clicked.connect(add)
    window.resize(460, 360)
    window.show()
    return window
