"""狭いMayaドックでパスと補助操作へ到達できることを検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback


def main(output_dir, finished):
    """実workspaceControlの幅と倍率を変え、見切れと操作保持を確認する。"""
    # 専用Maya GUI以外からは実行しない。
    from maya import cmds
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    sys.path.insert(0, str(root / "maya/inhouse/QuickPathExplorer/python"))
    from qpeQt import QtCore, QtWidgets
    from qpe_ui_maya import pause
    import qpeHost
    import qpeDock

    out = Path(output_dir)
    os.environ["QPE_SETTINGS_FILE"] = str(out / "settings.json")
    result = {"status": "error", "checks": [], "geometry": [], "input_kind": "Qt programmatic GUI"}
    try:
        e = qpeHost.show(str(out))
        e.setBrowseRoot(str(out))
        cmds.workspaceControl(qpeHost.CONTROL, edit=True, dockToMainWindow=("right", False))
        qpeHost.show()
        pause(700)
        control = qpeDock._control_widget(qpeHost.CONTROL)
        splitter, item = qpeDock._dock_splitter(control)
        index = splitter.indexOf(item)
        other = next(i for i, size in enumerate(splitter.sizes()) if i != index and size > 100)
        area = e._dockViewport
        for cycle, (width, percent) in enumerate(((360, 100), (600, 100), (1000, 100), (600, 150), (360, 100))):
            e.appearance.apply(13, percent, save=False)
            sizes = splitter.sizes()
            sizes[other] += sizes[index] - width
            sizes[index] = width
            splitter.setSizes(sizes)
            area.horizontalScrollBar().setValue(0)
            pause(800)
            viewport = area.viewport()
            points = {}
            for name, widget in (("address", e.address), ("tools", e.organizer.button),
                                 ("details", e.inspectorButton), ("back", e.backButton)):
                point = widget.mapTo(viewport, QtCore.QPoint(widget.width(), 0))
                points[name] = {"right": point.x(), "width": widget.width(), "visible": widget.isVisible()}
            result["geometry"].append({"requested": width, "scale": percent, "viewport": viewport.width(), "controls": points})
            viewport.grab().save(str(out / ("compact-%02d.png" % cycle)))
            for name, geometry in points.items():
                assert geometry["visible"] and geometry["right"] <= viewport.width(), (name, result["geometry"][-1])
            assert e.address.width() >= 100, result["geometry"][-1]
            if not e.saveAsButton.isVisible():
                for repeat in range(3):
                    e.organizer.populateTools()
                    pause(30)
                actions = e.organizer.toolsMenu.actions()
                menu = next(a.menu() for a in actions if a.text() == "Navigation / scene")
                save = next(a for a in menu.actions() if a.text() == "Save Scene As…")
                save.trigger()
                pause(200)
                assert e.operationTabs.currentWidget() is e.savePanel and e.inspectorButton.isChecked()
                e.inspectorButton.setChecked(False)
                pause(200)
                result["checks"].append("hidden Save As opens original inspector without saving")
            result["checks"].append("width %d scale %d: path and controls remain visible" % (width, percent))
        cmds.workspaceControl(qpeHost.CONTROL, edit=True, floating=True)
        pause(300)
        e.window().resize(1400, 900)
        pause(800)
        assert e.newSceneButton.isVisible() and e.saveAsButton.isVisible()
        assert e.organizer.button.text() == "Tools"
        area.viewport().grab().save(str(out / "wide-restored.png"))
        result["checks"].append("wide floating window restores ordinary buttons")
        assert not cmds.file(query=True, sceneName=True)
        result["status"] = "passed"
    except Exception:
        result["error"] = traceback.format_exc()
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    finished(result)
