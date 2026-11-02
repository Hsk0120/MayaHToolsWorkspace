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
    if request.get("phase") == "bottomDock":
        from maya import OpenMayaUI
        try:
            from shiboken6 import isValid, wrapInstance
        except ImportError:
            from shiboken2 import isValid, wrapInstance

        def control_widget(name):
            """Mayaが作り直したQt親をその時点で取得する。"""
            pointer = OpenMayaUI.MQtUtil.findControl(name)
            return wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None

        def dock_geometry():
            """ドックと固定行の位置、共有splitterを読み取る。"""
            item = control_widget(control)
            slider = control_widget("TimeSlider")
            rows = []
            splitters = []
            current = item
            while current and current.objectName() != "MayaWindow":
                rows.append(geometry(current))
                if isinstance(current, QtWidgets.QSplitter):
                    splitters.append({"orientation": str(current.orientation()), "sizes": current.sizes(),
                                      "rows": [{"name": current.widget(i).objectName(), "minimum": current.widget(i).minimumSizeHint().height(),
                                                "maximum": current.widget(i).maximumHeight(), "size": current.widget(i).height(),
                                                "handle": [current.handle(i).mapToGlobal(QtCore.QPoint()).x(), current.handle(i).mapToGlobal(QtCore.QPoint()).y(), current.handle(i).width(), current.handle(i).height()],
                                                "enabled": current.handle(i).isEnabled()} for i in range(current.count())]})
                current = current.parentWidget()
            return {"dock": geometry(item), "parents": rows, "splitters": splitters,
                    "dockTop": item.mapToGlobal(QtCore.QPoint()).y(),
                    "dockBottom": item.mapToGlobal(QtCore.QPoint(0, item.height())).y(),
                    "sliderTop": slider.mapToGlobal(QtCore.QPoint()).y()}

        def resize_dock(height):
            """Mayaの境界をQtで動かす。最小寸法や伸縮方針は変更しない。"""
            item = control_widget(control)
            # Qt5では再ドック後のparentWidget()が破棄済みラッパーを返す場合がある。
            # 生存するsplitterの子から現在の配置を照合し、古い親ラッパーをたどらない。
            matches = []
            for candidate in app.allWidgets():
                if not isValid(candidate) or not isinstance(candidate, QtWidgets.QSplitter):
                    continue
                if candidate.orientation() != QtCore.Qt.Vertical:
                    continue
                for index in range(candidate.count()):
                    row = candidate.widget(index)
                    if isValid(row) and (row == item or row.isAncestorOf(item)):
                        matches.append((candidate, row, index))
            assert matches
            splitter, row, index = min(matches, key=lambda value: value[0].width() * value[0].height())
            assert index > 0
            sizes = splitter.sizes()
            target = height + row.height() - item.height()
            sizes[index - 1] += sizes[index] - target
            sizes[index] = target
            splitter.setSizes(sizes)
            settle(1000)

        cmds.workspaceControl(control, edit=True, floating=True)
        settle()
        cmds.workspaceControl(control, edit=True, dockToMainWindow=("bottom", False))
        settle(1600)
        result["bottomDock"] = dock_geometry()
        (out / "bottom-dock.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        control_widget(control).grab().save(str(out / "bottom-dock.png"))
        assert result["bottomDock"]["dockBottom"] <= result["bottomDock"]["sliderTop"], result["bottomDock"]
        resize_dock(100)
        result["compact"] = dock_geometry()
        (out / "bottom-compact.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        assert result["compact"]["dock"]["size"][1] <= 130, result["compact"]
        result["checks"].append("bottom docking repaired above fixed rows and reduced to <=130px")
        palette = app.palette().cacheKey()
        scene = cmds.file(query=True, sceneName=True)
        panels = sorted(cmds.getPanel(type="modelPanel"))
        result["cycles"] = []
        for operation in ("sidebars", "close", "delete", "float"):
            resize_dock(400)
            assert control_widget(control).height() >= 300
            if operation == "sidebars":
                current = next(w for w in app.allWidgets() if w.objectName() == "qpeNativeWindow")
                for name in ("navigationPaneButton", "detailsPaneButton"):
                    button = current.findChild(QtWidgets.QToolButton, name)
                    button.click()
                    settle()
                    button.click()
            elif operation == "close":
                cmds.workspaceControl(control, edit=True, close=True)
                cmds.quickPathExplorer()
            elif operation == "delete":
                cmds.deleteUI(control)
                cmds.quickPathExplorer()
            else:
                cmds.workspaceControl(control, edit=True, floating=True)
            settle()
            cmds.workspaceControl(control, edit=True, dockToMainWindow=("bottom", False))
            settle(1600)
            resize_dock(100)
            value = dock_geometry()
            result["cycles"].append({"operation": operation, "geometry": value})
            assert value["dockBottom"] <= value["sliderTop"] and value["dock"]["size"][1] <= 130, value
            assert app.palette().cacheKey() == palette
            assert cmds.file(query=True, sceneName=True) == scene
            assert sorted(cmds.getPanel(type="modelPanel")) == panels
        result["checks"].append("expand/compact after sidebars, close, delete/recreate, float/redock; scene/panels/palette preserved")
        sibling = "QPEBottomSiblingControl"
        if cmds.workspaceControl(sibling, exists=True):
            raise RuntimeError("Previous bottom sibling probe still exists")
        cmds.workspaceControl(sibling, label="QPE bottom sibling", retain=False,
                              dockToMainWindow=("bottom", False))
        layout = cmds.columnLayout(parent=sibling)
        field = cmds.textField(parent=layout, text="Keep bottom sibling")
        try:
            cmds.workspaceControl(control, edit=True, tabToControl=(sibling, -1))
            settle(1800)
            item = control_widget(control)
            sibling_item = control_widget(sibling)
            shared = [widget for widget in app.allWidgets() if isValid(widget)
                      and isinstance(widget, QtWidgets.QTabWidget) and widget.count() >= 2
                      and widget.isAncestorOf(item) and widget.isAncestorOf(sibling_item)]
            assert shared, "QPE was detached from the bottom sibling tab"
            assert cmds.textField(field, query=True, text=True) == "Keep bottom sibling"
            result["checks"].append("bottom shared tab preserved across repair timer; sibling input unchanged")
        finally:
            cmds.workspaceControl(control, edit=True, floating=True)
            cmds.deleteUI(sibling)
        cmds.workspaceControl(control, edit=True, dockToMainWindow=("bottom", False))
        settle(1600)
        resize_dock(100)
        (out / "bottom-final.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return dict(result, status="passed")
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
