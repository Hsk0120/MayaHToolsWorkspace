import maya.cmds as cmds
from maya import OpenMayaUI as omui

from PySide6 import QtCore, QtWidgets
from shiboken6 import wrapInstance


def extrude_face_along_curve_even(face, curve, divisions=3, curve_spans=12):
    # カーブを均一化
    cmds.rebuildCurve(
        curve,
        ch=False,
        rpo=True,
        rt=0,
        end=1,
        kr=0,
        kcp=False,
        kep=True,
        kt=True,
        s=curve_spans,
        d=3
    )

    # 押し出し
    return cmds.polyExtrudeFacet(
        face,
        inputCurve=curve,
        divisions=divisions,
        keepFacesTogether=True,
        ch=True
    )[0]


def _get_selected_face_and_curve():
    sel = cmds.ls(sl=True, long=True) or []
    if not sel:
        cmds.error("1つのフェースと1つのカーブを選択してください。")

    faces = cmds.filterExpand(sel, sm=34) or []
    if not faces:
        cmds.error("フェースが選択されていません。")

    curve_transform = None
    for node in sel:
        if ".f[" in node:
            continue

        node_type = cmds.nodeType(node)
        if node_type == "nurbsCurve":
            parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
            curve_transform = parents[0] if parents else node
            break

        if node_type == "transform":
            shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
            if any(cmds.nodeType(shape) == "nurbsCurve" for shape in shapes):
                curve_transform = node
                break

    if curve_transform is None:
        cmds.error("カーブが選択されていません。")

    return faces[0], curve_transform


def extrude_selected_face_along_curve_even(divisions=3, curve_spans=20):
    face, curve = _get_selected_face_and_curve()
    return extrude_face_along_curve_even(
        face,
        curve,
        divisions=divisions,
        curve_spans=curve_spans,
    )


def _maya_main_window():
    main_window_ptr = omui.MQtUtil.mainWindow()
    if main_window_ptr is None:
        return None
    return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)


class ExtrudeFaceAlongCurveEvenUI(QtWidgets.QDialog):
    WINDOW_TITLE = "Extrude Face Along Curve Even"
    WINDOW_OBJECT_NAME = "extrudeFaceAlongCurveEvenUI"

    def __init__(self, parent=_maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setObjectName(self.WINDOW_OBJECT_NAME)
        self.setWindowFlag(QtCore.Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(280)

        self._build_ui()
        self._create_connections()

    def _build_ui(self):
        self.divisions_spin = QtWidgets.QSpinBox()
        self.divisions_spin.setRange(1, 200)
        self.divisions_spin.setValue(3)

        self.curve_spans_spin = QtWidgets.QSpinBox()
        self.curve_spans_spin.setRange(1, 1000)
        self.curve_spans_spin.setValue(20)

        self.execute_btn = QtWidgets.QPushButton("Execute")
        self.close_btn = QtWidgets.QPushButton("Close")

        form_layout = QtWidgets.QFormLayout()
        form_layout.addRow("divisions", self.divisions_spin)
        form_layout.addRow("curve_spans", self.curve_spans_spin)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addWidget(self.execute_btn)
        btn_layout.addWidget(self.close_btn)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)

    def _create_connections(self):
        self.execute_btn.clicked.connect(self._on_execute)
        self.close_btn.clicked.connect(self.close)

    def _on_execute(self):
        try:
            result = extrude_selected_face_along_curve_even(
                divisions=self.divisions_spin.value(),
                curve_spans=self.curve_spans_spin.value(),
            )
            cmds.select(result, r=True)
            cmds.inViewMessage(amg="Extrude completed", pos="topCenter", fade=True)
        except Exception as exc:
            cmds.warning(str(exc))


_extrude_face_along_curve_even_ui = None


def show_extrude_face_along_curve_even_ui():
    global _extrude_face_along_curve_even_ui

    if _extrude_face_along_curve_even_ui is not None:
        try:
            _extrude_face_along_curve_even_ui.close()
            _extrude_face_along_curve_even_ui.deleteLater()
        except Exception:
            pass

    _extrude_face_along_curve_even_ui = ExtrudeFaceAlongCurveEvenUI()
    _extrude_face_along_curve_even_ui.show()
    _extrude_face_along_curve_even_ui.raise_()
    _extrude_face_along_curve_even_ui.activateWindow()


if __name__ == "__main__":
    show_extrude_face_along_curve_even_ui()