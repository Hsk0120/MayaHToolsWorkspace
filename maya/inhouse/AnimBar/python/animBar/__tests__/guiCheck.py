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
            from animBar.core import crashRecovery, keys, timeline
            keyed = cmds.createNode("transform", name="guiKeyed", skipSelect=True)
            cmds.setKeyframe(keyed, attribute="tx", time=1, value=0)
            cmds.setKeyframe(keyed, attribute="tx", time=5, value=1)
            cmds.selectKey(keyed + ".tx", time=(5, 5))
            checks["closed_editor_ignores_keys"] = keys.graphEditorKeys() == {}
            cmds.GraphEditor()
            maya.utils.processIdleEvents()
            checks["open_editor_uses_keys"] = [len(value) for value in keys.graphEditorKeys().values()] == [1]
            for window in cmds.lsUI(windows=True) or []:
                if window.startswith("graphEditor"):
                    cmds.deleteUI(window)
            cmds.delete(keyed)
            checks["recovery_toggle"] = crashRecovery.setEnabled(True) and crashRecovery.isEnabled() and                 not crashRecovery.setEnabled(False) and not crashRecovery.isEnabled()
            tumble = viewTools.isTumbleOnObjects()
            viewTools.setTumbleOnObjects(not tumble)
            checks["tumble_toggle"] = viewTools.isTumbleOnObjects() == (not tumble)
            viewTools.setTumbleOnObjects(tumble)
            playblast_folder = str(Path(output) / "playblast")
            os.makedirs(playblast_folder, exist_ok=True)
            from mlib.common import Time
            Time.setPlaybackRange(1, 3)
            movie = timeline.playblast(play=False, folder=playblast_folder)
            checks["playblast_file"] = bool(movie) and any(Path(playblast_folder).iterdir())
            checks["jump_follow"] = timeline.setJumpToSelectedKey(True) and not timeline.setJumpToSelectedKey(False)
            # プレイブラストの設定: 大きさ・音声なし・オーバースキャンで撮り、カメラのオーバースキャンを元へ戻す。
            camera = cmds.modelPanel(cmds.getPanel(type="modelPanel")[0], query=True, camera=True)
            shape = (cmds.listRelatives(camera, shapes=True) or [camera])[0]
            overscan = cmds.getAttr(shape + ".overscan")
            timeline.setPlayblastSettings(sound=False, overscan=1.3, percent=50, showOrnaments=False)
            try:
                movie = timeline.playblast(play=False, folder=playblast_folder)
            finally:
                timeline.resetPlayblastSettings()
            checks["playblast_settings"] = bool(movie) and abs(cmds.getAttr(shape + ".overscan") - overscan) < 1e-9
            checks["timeline_range_none"] = keys.timelineRange() is None
            # 退避を有効にすると、シーンを開いたときに確かめる scriptJob も作る。
            crashRecovery.setEnabled(True, remember=False)
            jobs = " ".join(cmds.scriptJob(listJobs=True))
            checks["recovery_open_job"] = "SceneOpened" in jobs and crashRecovery.checkOnOpen(ask=lambda path: "keep")                 in (None, "keep")
            crashRecovery.setEnabled(False, remember=False)
            # transformAll のトグルのボタン: 押して値を変え、もう一度押すと全キーへ差を足す。
            from animBar.core import timing
            moved = cmds.createNode("transform", name="guiTransformAll", skipSelect=True)
            cmds.setKeyframe(moved, attribute="ty", time=1, value=0)
            cmds.setKeyframe(moved, attribute="ty", time=5, value=2)
            cmds.select(moved)
            cmds.currentTime(5)
            widget = bar._bar["widget"]
            widget.transformAll.setChecked(True)
            started = timing.isTransformAllActive()
            cmds.setAttr(moved + ".ty", 3)
            widget.transformAll.setChecked(False)
            checks["transform_all_toggle"] = started and not timing.isTransformAllActive() and                 cmds.keyframe(moved + ".ty", query=True, valueChange=True) == [1.0, 3.0]
            checks["session_mode_default"] = widget._session_mode() == widget.mode.currentData()
            # 右クリックのメニューが今の状態で作れること。
            menus = {}
            for name, build in (("playblast", widget._playblast_menu), ("mirror", widget._mirror_menu),
                                ("tangent", lambda menu: widget._tangent_menu("flat", menu)),
                                ("transformAll", widget._transform_all_menu)):
                menu = QtWidgets.QMenu(widget)
                build(menu)
                menus[name] = len(menu.actions())
                menu.deleteLater()
            checks["menus"] = menus
            cmds.delete(moved)
            animBar.toggle()
            checks["startup_respects_hidden"] = startup.install() is False
            checks["startup_shows"] = (cmds.optionVar(intValue=(bar.VISIBLE_OPTION, 1)) or True) and startup.install()
            expected = {"control_exists": True, "runtime_commands": True, "startup_respects_hidden": True,
                        "startup_shows": True, "widget_built": True, "docked": True, "above_time_slider": True,
                        "toggle_hides": True, "toggle_shows": True, "micro_rebaseline_jobs": True,
                        "micro_stopped": True, "jump_follow": True, "playblast_settings": True,
                        "timeline_range_none": True, "recovery_open_job": True, "transform_all_toggle": True,
                        "session_mode_default": True,
                        "recovery_toggle": True, "tumble_toggle": True, "playblast_file": True,
                        "closed_editor_ignores_keys": True, "open_editor_uses_keys": True}
            failed = [name for name, value in expected.items() if checks.get(name) != value]
            if checks["tween_slider_value"] != [7.5]:
                failed.append("tween_slider_value")
            if checks["bars_in_control"] != 1:
                failed.append("bars_in_control")
            if not all(checks["menus"].values()):
                failed.append("menus")
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
