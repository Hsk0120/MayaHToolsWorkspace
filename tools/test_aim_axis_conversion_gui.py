"""隔離したMaya GUIでAim変換画面の3方式・復元・診断を検証する。"""

import datetime
import json
import os
from pathlib import Path
import sys
import traceback


ROOT = Path(__file__).resolve().parents[1]


def main(output_dir=None, finished=None):
    """専用GUIランナーだけでシーンを作り、操作結果と画面を保存する。

    Args:
        output_dir (str | Path): ランナーの証跡保存先。
        finished (Callable): ランナーへ渡す終了通知。
    """
    if os.environ.get("HLIB_DISPOSABLE_GUI") != "1":
        raise RuntimeError("このテストは専用の使い捨てGUIでだけ実行できます。")
    import maya.cmds as cmds
    import maya.OpenMayaUI as omui
    from HTools.rigging.convertAimAxes import run
    from hrig.setups.aimAxisConversion import AimAxisConversion
    try:
        from PySide6 import QtWidgets
        from shiboken6 import wrapInstance
    except ImportError:
        from PySide2 import QtWidgets
        from shiboken2 import wrapInstance
    output = Path(output_dir)
    result = {"status": "running", "checks": [], "outputs": {}}
    try:
        cmds.file(new=True, force=True)
        target = cmds.createNode("transform", name="aimTarget")
        driven = cmds.createNode("transform", name="aimDriven")
        cmds.setAttr(target + ".translate", 10, 7, 5)
        constraint = cmds.aimConstraint(target, driven, worldUpType="vector")[0]
        cmds.select(constraint)
        ui = run()
        assert ui.constraint.getName() == constraint
        cmds.optionMenuGrp(ui.axes, edit=True, value="XY")
        cmds.optionMenuGrp(ui.direction, edit=True, value="Z")
        cmds.checkBox(ui.preserve, edit=True, value=False)
        for mode in (1, 2, 3):
            cmds.optionMenuGrp(ui.mode, edit=True, select=mode)
            ui.convert()
            graph = AimAxisConversion.find(constraint)
            assert graph is not None, cmds.scrollField(ui.status, query=True, text=True)
            assert json.loads(graph.container.getPlug("settings").get())["mode"] == ("euler", "direction", "twist")[mode - 1]
            result["outputs"][str(mode)] = cmds.getAttr(driven + ".rotate")[0]
            result["checks"].append("mode{}".format(mode))
            ui.refresh()
            QtWidgets.QApplication.processEvents()
            widget = wrapInstance(int(omui.MQtUtil.findWindow(ui.window)), QtWidgets.QWidget)
            assert widget.grab().save(str(output / "mode{}.png".format(mode)))
        cmds.select(constraint)
        ui.loadSelection()
        assert cmds.optionMenuGrp(ui.mode, query=True, select=True) == 3
        assert cmds.optionMenuGrp(ui.axes, query=True, value=True) == "XY"
        result["checks"].append("reload_settings")
        cmds.checkBox(ui.useContainer, edit=True, value=False)
        ui.convert()
        graph = AimAxisConversion.find(constraint)
        assert graph.container.getType() == "network"
        assert not cmds.ls(type="container")
        cmds.select(graph.container.getFullName())
        cmds.checkBox(ui.useContainer, edit=True, value=True)
        ui.loadSelection()
        assert not cmds.checkBox(ui.useContainer, query=True, value=True)
        result["checks"].append("direct_connection_reload")
        cmds.checkBox(ui.useContainer, edit=True, value=True)
        ui.convert()
        assert AimAxisConversion.find(constraint).container.getType() == "container"
        result["checks"].append("container_switch")
        ui.restore()
        assert AimAxisConversion.find(constraint) is None
        result["checks"].append("restore")
        cmds.optionMenuGrp(ui.mode, edit=True, select=2)
        cmds.optionMenuGrp(ui.direction, edit=True, value="X")
        ui.convert()
        assert AimAxisConversion.find(constraint) is None
        assert "回転軸以外" in cmds.scrollField(ui.status, query=True, text=True)
        result["checks"].append("invalid_direction")
        result["status"] = "passed"
    except Exception:
        result.update(status="failed", error=traceback.format_exc())
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    finished(result)


if __name__ == "__main__":
    from run_hlib_gui_versions import run_version
    output = ROOT / ".maya-output/aim-axis-gui" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    result = run_version("2027", output, Path("C:/Program Files/Autodesk"), 180,
                         suite_path=Path(__file__).resolve(), environment={"HLIB_DISPOSABLE_GUI": "1"})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["status"] == "passed" else 1)
