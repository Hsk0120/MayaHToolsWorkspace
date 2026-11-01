"""専用Mayaでドック最小寸法と他Qtへの入力境界を確認する。OS入力とは区別する。"""

import json
import os
from pathlib import Path


def main(out, request):
    """専用ハーネス内のQPEだけを調べ、シーンやユーザー設定は変更しない。"""
    from maya import cmds
    try:
        from PySide6 import QtCore, QtTest, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtTest, QtWidgets
    out = Path(out)
    if ".maya-output" not in out.parts or "persistent-" not in str(out.parent):
        raise ValueError("Dedicated validation output is required")
    if os.environ.get("QPE_NATIVE_KEEP_LOADED") != "1":
        raise RuntimeError("Dedicated persistent Maya is required")
    app = QtWidgets.QApplication.instance()
    control = "QuickPathExplorerWorkspaceControl"
    window = next(w for w in app.allWidgets() if w.objectName() == "qpeNativeWindow")

    def settle(milliseconds=150):
        """実際のQt/Mayaイベントループへ制御を戻す。"""
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        (loop.exec if hasattr(loop, "exec") else loop.exec_)()

    def geometry(widget):
        """保持せず、その時点のQt寸法を値として記録する。"""
        return {"class": widget.metaObject().className(), "name": widget.objectName(),
                "nativeWindow": widget.testAttribute(QtCore.Qt.WA_NativeWindow),
                "size": [widget.width(), widget.height()],
                "minimum": [widget.minimumWidth(), widget.minimumHeight()],
                "minimumHint": [widget.minimumSizeHint().width(), widget.minimumSizeHint().height()],
                "hint": [widget.sizeHint().width(), widget.sizeHint().height()]}

    def floating_surface(content):
        """Mayaが再生成した浮動親を、現在の親連鎖から取り直す。

        Qt5のQWidget.window()が破棄済みPySideラッパーを返す場合があるため、
        そのラッパーやHWNDを保持しない。Maya本体のサイズは変更しない。
        """
        surface = content
        while not surface.isWindow():
            parent = surface.parentWidget()
            if parent is None:
                break
            surface = parent
        if surface.objectName() == "MayaWindow":
            raise RuntimeError("QPE has not detached into its own floating surface")
        return surface

    parents = []
    current = window
    while current:
        parents.append(geometry(current))
        current = current.parentWidget()
    # HWNDの取得目的でwinId()を呼ぶと、Qt5/Mayaがフロート親を再生成することがある。
    # 検証対象の寿命を測定側で変えず、録画対象はOSのウィンドウ一覧で別途選ぶ。
    result = {"pid": os.getpid(), "maya": cmds.about(version=True), "parents": parents,
              "evidence": "Qt programmatic; not OS input", "checks": []}
    (out / "geometry-before.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if request.get("phase") == "inspect":
        result["instances"] = [geometry(w) for w in app.allWidgets()
                               if w.objectName() in ("qpeNativeWindow", "qpeNativeDockViewport")]
        window.grab().save(str(out / "content.png"))
        if cmds.workspaceControl(control, query=True, floating=True):
            floating_surface(window).grab().save(str(out / "surface.png"))
        return dict(result, status="inspected")
    if request.get("phase") == "sharedTabs":
        other_control = "QPEDedicatedSiblingControl"
        if cmds.workspaceControl(other_control, exists=True):
            raise RuntimeError("Previous sibling probe still exists")
        palette = app.palette().cacheKey()
        undo = cmds.undoInfo(query=True, state=True)
        panels = sorted(cmds.getPanel(type="modelPanel"))
        scene = cmds.file(query=True, sceneName=True)
        cmds.workspaceControl(other_control, label="QPE dedicated sibling", retain=False,
                              dockToMainWindow=("right", False), initialWidth=320)
        layout = cmds.columnLayout(parent=other_control)
        field = cmds.textField(parent=layout, text="Keep sibling input")
        try:
            for cycle in range(8):
                cmds.workspaceControl(control, edit=True, tabToControl=(other_control, -1))
                settle()
                if cycle % 2:
                    cmds.deleteUI(control)
                else:
                    cmds.workspaceControl(control, edit=True, close=True)
                settle()
                cmds.quickPathExplorer()
                settle()
                assert cmds.workspaceControl(other_control, exists=True)
                assert cmds.textField(field, query=True, text=True) == "Keep sibling input"
                assert app.palette().cacheKey() == palette
                assert sorted(cmds.getPanel(type="modelPanel")) == panels
                assert cmds.file(query=True, sceneName=True) == scene
                assert cmds.undoInfo(query=True, state=True) == undo
            result["checks"].append("8 shared-tab close/delete/recreate cycles; sibling text, model panels, scene, Undo state and application palette preserved")
        finally:
            if cmds.workspaceControl(control, exists=True):
                cmds.workspaceControl(control, edit=True, floating=True)
            if cmds.workspaceControl(other_control, exists=True):
                cmds.deleteUI(other_control)
        settle()
        current = next(w for w in app.allWidgets() if w.objectName() == "qpeNativeWindow")
        surface = floating_surface(current)
        surface.resize(1000, 700)
        surface.move(surface.screen().availableGeometry().topLeft() + QtCore.QPoint(40, 80))
        settle()
        surface.grab().save(str(out / "shared-tabs-final.png"))
        return dict(result, status="passed")
    if request.get("phase") != "resize":
        raise ValueError("Unsupported GUI validation phase")
    cmds.workspaceControl(control, edit=True, floating=True)
    settle()
    # 浮動親はMayaが所有・再生成する。サイズ変更もMayaの正式入口で行う。
    cmds.workspaceControl(control, edit=True, resizeWidth=420, resizeHeight=600)
    settle()
    window = next(w for w in app.allWidgets() if w.objectName() == "qpeNativeWindow")
    result["narrow"] = {"width": cmds.workspaceControl(control, query=True, width=True),
                        "height": cmds.workspaceControl(control, query=True, height=True),
                        "floating": cmds.workspaceControl(control, query=True, floating=True)}
    result["contentNarrow"] = geometry(window)
    (out / "geometry-narrow.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    window.grab().save(str(out / "narrow.png"))
    assert result["narrow"]["floating"] and result["narrow"]["width"] <= 500, result["narrow"]
    details = window.findChild(QtWidgets.QWidget, "inspector")
    if details.isHidden():
        window.findChild(QtWidgets.QToolButton, "detailsPaneButton").click()
    settle()
    assert details.isVisible()
    assert not window.findChild(QtWidgets.QTreeView, "files").isVisible()
    selector = details.findChild(QtWidgets.QComboBox, "inspectorOperation")
    tabs = details.findChild(QtWidgets.QTabWidget, "readOptions")
    for index in range(4):
        selector.setCurrentIndex(index)
        settle(40)
        assert tabs.currentIndex() == index
    cmds.workspaceControl(control, edit=True, resizeWidth=1200, resizeHeight=800)
    settle()
    assert window.findChild(QtWidgets.QTreeView, "files").isVisible()
    result["checks"].append("420 px floating width, full-width details, four operations, return to wide view")
    before = app.palette().cacheKey()
    other = QtWidgets.QLineEdit()
    other.setObjectName("qpeDedicatedOtherInput")
    try:
        other.show()
        other.activateWindow()
        other.setFocus()
        QtTest.QTest.keyClicks(other, "external Qt")
        QtTest.QTest.keyClick(other, QtCore.Qt.Key_Plus, QtCore.Qt.ControlModifier)
        assert other.text() == "external Qt"
        assert app.palette().cacheKey() == before
        result["checks"].append("external QLineEdit text and application palette preserved")
    finally:
        other.close()
        other.deleteLater()
    result["status"] = "passed"
    return result
