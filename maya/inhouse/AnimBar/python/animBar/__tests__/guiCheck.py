"""使い捨ての Maya GUI で Anim Bar を表示し、ドックの位置・部品・操作を確かめて画像を残す。

mlib の ``runGui.run_version`` の suite として実行する(作業中の Maya GUI では実行しない)::

    python maya\\inhouse\\AnimBar\\python\\animBar\\__tests__\\run_gui.py --versions 2027
"""

import json
import os
import sys
import traceback
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.dirname(os.path.dirname(HERE))


def main(output_dir=None, finished=None):
    """バーを表示し、確認の結果を ``result.json`` に書いて finished を呼ぶ。

    Args:
        output_dir (str | Path | None): 結果と画像の保存先。
        finished (Callable | None): 結果の辞書を受け取る終了処理。

    Returns:
        None: 値を返さない。
    """
    import maya.cmds as cmds
    import maya.utils

    if PYTHON not in sys.path:
        sys.path.insert(0, PYTHON)
    output = Path(output_dir or os.path.join(HERE, "_output"))
    output.mkdir(parents=True, exist_ok=True)
    result = {"status": "error", "checks": {}, "screenshots": []}

    def finish():
        """結果を書いて終了処理へ渡す。"""
        (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        if finished is not None:
            finished(result)

    def check():
        """表示の後、イベントを処理してから確かめる。"""
        try:
            from animBar.ui import bar
            from animBar.ui.qt import QtWidgets
            import animBar

            import maya.OpenMayaUI as omui
            from animBar.ui.qt import wrapInstance
            widget = bar._bar["widget"]
            checks = result["checks"]
            checks["control_exists"] = bool(cmds.workspaceControl(bar.CONTROL, exists=True))
            checks["widget_built"] = widget is not None and widget.isVisible()
            checks["docked"] = not cmds.workspaceControl(bar.CONTROL, query=True, floating=True)
            sections = [child for child in widget.findChildren(QtWidgets.QFrame) if child.objectName() == "AnimBarSection"]
            checks["sections"] = len(sections)
            control = wrapInstance(int(omui.MQtUtil.findControl(bar.CONTROL)), QtWidgets.QWidget)
            checks["bars_in_control"] = len(control.findChildren(bar.AnimBar))
            checks["buttons"] = len(widget.findChildren(QtWidgets.QToolButton))
            checks["height"] = widget.height()
            # 画面の上でのバーとタイムスライダーの位置(バーがタイムスライダーより上にあるか)。
            slider = wrapInstance(int(omui.MQtUtil.findControl("TimeSlider")), QtWidgets.QWidget)
            checks["above_time_slider"] = widget.mapToGlobal(widget.rect().topLeft()).y() < \
                slider.mapToGlobal(slider.rect().topLeft()).y()
            # 操作: キーを打ったノードでツイーンのスライダーを動かす。
            node = cmds.createNode("transform", name="animBarGuiCheck", skipSelect=True)
            cmds.setKeyframe(node, attribute="tx", time=1, value=0)
            cmds.setKeyframe(node, attribute="tx", time=11, value=10)
            cmds.select(node)
            cmds.currentTime(6)
            sliders = widget.findChildren(bar.UndoSlider)
            sliders[0].setValue(75)
            checks["tween_slider_value"] = cmds.keyframe(node + ".tx", query=True, time=(6, 6), valueChange=True)
            # 選択セットのボタンが増えること。
            from animBar.core import selectSets
            selectSets.createSet("Gui", [node], colorIndex=2)
            widget.refreshSets()
            checks["set_buttons"] = [button.text() for button in widget.findChildren(QtWidgets.QToolButton)
                                     if button.objectName() == "AnimBarSet"]
            QtWidgets.QApplication.processEvents()
            image = output / "animBar.png"
            widget.grab().save(str(image))
            result["screenshots"].append(str(image))
            window = widget.window()
            whole = output / "animBar_window.png"
            window.grab().save(str(whole))
            result["screenshots"].append(str(whole))
            animBar.toggle()
            checks["toggle_hides"] = not cmds.workspaceControl(bar.CONTROL, exists=True)
            animBar.toggle()
            checks["toggle_shows"] = bool(cmds.workspaceControl(bar.CONTROL, exists=True))
            from animBar.core import commands
            from animBar.ui import startup
            checks["runtime_commands"] = all(cmds.runTimeCommand(name, exists=True) for name in commands.register())
            from animBar.core import viewTools
            viewTools.setMicroTransform(True)
            jobs = " ".join(cmds.scriptJob(listJobs=True))
            checks["micro_rebaseline_jobs"] = all(event in jobs for event in ("timeChanged", "Undo", "Redo"))
            viewTools.setMicroTransform(False)
            checks["micro_stopped"] = not viewTools.isMicroTransform()
            animBar.toggle()
            checks["startup_respects_hidden"] = startup.install() is False
            checks["startup_shows"] = (cmds.optionVar(intValue=(bar.VISIBLE_OPTION, 1)) or True) and startup.install()
            expected = {"control_exists": True, "runtime_commands": True, "startup_respects_hidden": True,
                        "startup_shows": True, "widget_built": True, "docked": True, "above_time_slider": True,
                        "toggle_hides": True, "toggle_shows": True, "micro_rebaseline_jobs": True,
                        "micro_stopped": True}
            failed = [name for name, value in expected.items() if checks.get(name) != value]
            if checks["tween_slider_value"] != [7.5]:
                failed.append("tween_slider_value")
            if checks["bars_in_control"] != 1:
                failed.append("bars_in_control")
            if checks["set_buttons"] != ["Gui"]:
                failed.append("set_buttons")
            result["failed"] = failed
            result["status"] = "passed" if not failed else "failed"
        except Exception:
            result["error"] = traceback.format_exc()
        finish()

    try:
        import animBar
        animBar.show()
        maya.utils.executeDeferred(lambda: cmds.evalDeferred(check, lowestPriority=True))
    except Exception:
        result["error"] = traceback.format_exc()
        finish()
