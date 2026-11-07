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


def dock_and_settings(bar, preferences, settingsDialog, startup, QtCore, QtGui, QtWidgets, wrapInstance, omui,
                      output, result):
    """つまみでのドックの付け外し・Windows メニュー・設定の画面を確かめる。

    Returns:
        dict: 確認の結果。
    """
    import maya.cmds as cmds

    checks = {}

    def settle():
        """遅延実行(evalDeferred)とイベントを処理する。"""
        for _ in range(3):
            # processIdleEvents は evalDeferred の処理を進めないため、Mayaの暇なときの処理を流す。
            cmds.flushIdleQueue()
            QtWidgets.QApplication.processEvents()

    def mouse(widget, kind, point, buttons=QtCore.Qt.LeftButton):
        """部品へマウスのイベントを送る(point は部品の中の座標)。"""
        local = QtCore.QPointF(point)
        event = QtGui.QMouseEvent(kind, local, QtCore.QPointF(widget.mapToGlobal(point)), QtCore.Qt.LeftButton,
                                  buttons, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.sendEvent(widget, event)

    def tabs():
        """バーが入っているタブの部品。"""
        control = wrapInstance(int(omui.MQtUtil.findControl(bar.CONTROL)), QtWidgets.QWidget)
        return control.parentWidget().parentWidget()

    widget = bar._bar["widget"]
    checks["grip_and_settings_button"] = bool(widget.findChildren(bar.DockGrip)) and \
        bool([button for button in widget.findChildren(QtWidgets.QToolButton)
              if button.objectName() == "AnimBarSettings"])
    # Windows メニュー: Maya の項目が作られたうえで、末尾に1つだけ足されていること。
    startup.addWindowMenu()
    items = cmds.menu(startup.WINDOW_MENU, query=True, itemArray=True) or []
    checks["window_menu"] = len(items) > 5 and items[-1] == startup.WINDOW_MENU_ITEM
    checks["window_menu_once"] = items.count(startup.WINDOW_MENU_ITEM) == 1
    action_type = getattr(QtGui, "QAction", None) or QtWidgets.QAction
    pointer = omui.MQtUtil.findMenuItem(startup.WINDOW_MENU + "|" + startup.WINDOW_MENU_ITEM)
    action = wrapInstance(int(pointer), action_type) if pointer else None
    checks["window_menu_icon"] = action is not None and not action.icon().isNull() and action.isIconVisibleInMenu()
    if checks["window_menu_icon"]:
        preview = output / "animBar_menu_icon.png"
        action.icon().pixmap(32, 32).save(str(preview))
        result["screenshots"].append(str(preview))
    # 表示中に show を呼んでも作り直さない(Windows メニューから選んだとき)。
    bar.show()
    settle()
    checks["show_keeps_bar"] = bar._bar["widget"] is widget
    # つまみをドラッグすると浮動の窓になり、マウスに付いて動く。
    grip = widget.findChildren(bar.DockGrip)[0]
    center = QtCore.QPoint(grip.width() // 2, grip.height() // 2)
    mouse(grip, QtCore.QEvent.MouseButtonPress, center)
    mouse(grip, QtCore.QEvent.MouseMove, center + QtCore.QPoint(0, -40))
    settle()
    checks["drag_floats"] = bar.isFloating()
    window = grip.window()
    before = window.pos()
    mouse(grip, QtCore.QEvent.MouseMove, center + QtCore.QPoint(30, -60))
    QtWidgets.QApplication.processEvents()
    checks["drag_moves_window"] = window.pos() != before
    mouse(grip, QtCore.QEvent.MouseButtonRelease, center + QtCore.QPoint(30, -60), QtCore.Qt.NoButton)
    settle()
    window.grab().save(str(output / "animBar_floating.png"))
    result["screenshots"].append(str(output / "animBar_floating.png"))
    # ダブルクリックでタイムスライダーの上へ戻り、タブの行が隠れる。
    mouse(grip, QtCore.QEvent.MouseButtonDblClick, center)
    settle()
    slider = wrapInstance(int(omui.MQtUtil.findControl("TimeSlider")), QtWidgets.QWidget)
    checks["double_click_docks"] = not bar.isFloating() and \
        widget.mapToGlobal(QtCore.QPoint(0, 0)).y() < slider.mapToGlobal(QtCore.QPoint(0, 0)).y()
    docked = tabs()
    checks["redocked_tab_bar"] = [docked.tabBar().isVisible(), docked.height()]
    checks["docked_tab_hidden"] = not docked.tabBar().isVisible() and docked.height() <= preferences.barHeight() + 6
    widget.window().grab().save(str(output / "animBar_redocked.png"))
    result["screenshots"].append(str(output / "animBar_redocked.png"))
    # 設定の画面: 区切りを隠す・大きさを変えて作り直す・既定へ戻す。
    dialog = settingsDialog.showDialog()
    settle()
    dialog.grab().save(str(output / "animBar_settings.png"))
    result["screenshots"].append(str(output / "animBar_settings.png"))
    dialog.sectionBoxes["Tangents"].setChecked(False)
    checks["settings_hide_section"] = not widget.sections["Tangents"].isVisible() and \
        preferences.hiddenSections() == ["Tangents"]
    dialog.size.setCurrentIndex(dialog.size.findData("large"))
    settle()
    rebuilt = bar._bar["widget"]
    large = [button.iconSize().width() for button in rebuilt.findChildren(QtWidgets.QToolButton)
             if button.objectName() != "AnimBarSet"]
    checks["settings_size_rebuild"] = rebuilt is not widget and set(large) == {28} and \
        not rebuilt.sections["Tangents"].isVisible()
    preferences.resetAll()
    dialog.refresh()
    bar.rebuild()
    settle()
    widget = bar._bar["widget"]
    checks["settings_reset"] = preferences.size() == "medium" and preferences.hiddenSections() == [] and \
        widget.sections["Tangents"].isVisible() and dialog.sectionBoxes["Tangents"].isChecked() and \
        dialog.size.currentData() == "medium"
    dialog.close()
    return checks


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
            from animBar.ui import bar, preferences, settingsDialog
            from animBar.ui.qt import QtCore, QtGui, QtWidgets
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
            # 見出しのタブの行が隠れ、ドック全体の高さがバーの高さ(とタブの枠)に収まること。
            tabs = control.parentWidget().parentWidget()
            checks["tab_bar_hidden"] = not tabs.tabBar().isVisible()
            checks["dock_height"] = tabs.height()
            checks["buttons"] = len(widget.findChildren(QtWidgets.QToolButton))
            checks["height"] = widget.height()
            # どの部品にも、見出しと使い方の2行以上のツールチップがあること。
            parts = widget.findChildren(QtWidgets.QToolButton) + widget.findChildren(bar.UndoSlider) + \
                widget.findChildren(QtWidgets.QComboBox) + widget.findChildren(QtWidgets.QDoubleSpinBox)
            checks["tooltips_missing"] = [part.objectName() or type(part).__name__ for part in parts
                                          if len(part.toolTip().splitlines()) < 2]
            checks["mode_item_tooltips"] = all(widget.mode.itemData(index, QtCore.Qt.ToolTipRole)
                                               for index in range(widget.mode.count()))
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
            # 目視の確認用に、ツールチップを出した状態の画像を残す。
            for index, name in enumerate(("transformAll", "align")):
                button = getattr(widget, name, None) or next(
                    part for part in widget.findChildren(QtWidgets.QToolButton) if part.toolTip().startswith("Align"))
                QtWidgets.QToolTip.showText(button.mapToGlobal(button.rect().bottomLeft()), button.toolTip(), button)
                QtWidgets.QApplication.processEvents()
                labels = [top for top in QtWidgets.QApplication.topLevelWidgets()
                          if top.inherits("QTipLabel") and top.isVisible()]
                if labels:
                    tip = output / "animBar_tooltip_{}.png".format(index + 1)
                    labels[0].grab().save(str(tip))
                    result["screenshots"].append(str(tip))
                QtWidgets.QToolTip.hideText()
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
            untipped = []

            def collect_untipped(menu, path):
                """説明の無い項目を、サブメニューもたどって集める。"""
                for action in menu.actions():
                    if action.isSeparator():
                        continue
                    if not action.toolTip() or action.toolTip() == action.text().replace("&", ""):
                        untipped.append(path + "/" + action.text())
                    if action.menu() is not None:
                        collect_untipped(action.menu(), path + "/" + action.text())

            from animBar.core import timeline as timeline_module
            timeline_module.saveRange("guiCheckRange")
            for name, build in (("playblast", widget._playblast_menu), ("mirror", widget._mirror_menu),
                                ("tangent", lambda menu: widget._tangent_menu("flat", menu)),
                                ("transformAll", widget._transform_all_menu), ("tween", widget._tween_menu),
                                ("frame", widget._frame_menu), ("nudge", lambda menu: widget._nudge_menu(1, menu)),
                                ("range", widget._range_menu), ("reset", widget._reset_menu),
                                ("paste", widget._paste_menu), ("align", widget._align_menu),
                                ("micro", widget._micro_menu), ("recovery", widget._recovery_menu),
                                ("sets", widget._sets_menu)):
                menu = QtWidgets.QMenu(widget)
                build(menu)
                menus[name] = len(menu.actions())
                collect_untipped(menu, name)
                menu.deleteLater()
            timeline_module.removeRange("guiCheckRange")
            # ボタンに直接書いた右クリックのメニュー(Share・Jump・Copy・Pivot・Follow・Trail)も含め、全ボタンのメニュー。
            for button in widget.findChildren(QtWidgets.QToolButton):
                build = getattr(button, "menuBuilder", None)
                if build is None:
                    continue
                menu = QtWidgets.QMenu(widget)
                build(menu)
                collect_untipped(menu, button.toolTip().splitlines()[0])
                menu.deleteLater()
                checks["button_menus"] = checks.get("button_menus", 0) + 1
            checks["menus"] = menus
            checks["menu_items_without_tips"] = untipped
            cmds.delete(moved)
            checks.update(dock_and_settings(bar, preferences, settingsDialog, startup, QtCore, QtGui, QtWidgets,
                                            wrapInstance, omui, output, result))
            animBar.toggle()
            checks["startup_respects_hidden"] = startup.install() is False
            checks["startup_shows"] = (cmds.optionVar(intValue=(bar.VISIBLE_OPTION, 1)) or True) and startup.install()
            expected = {"control_exists": True, "runtime_commands": True, "startup_respects_hidden": True,
                        "startup_shows": True, "widget_built": True, "docked": True, "above_time_slider": True,
                        "tab_bar_hidden": True,
                        "toggle_hides": True, "toggle_shows": True, "micro_rebaseline_jobs": True,
                        "micro_stopped": True, "jump_follow": True, "playblast_settings": True,
                        "timeline_range_none": True, "recovery_open_job": True, "transform_all_toggle": True,
                        "session_mode_default": True, "tooltips_missing": [], "mode_item_tooltips": True,
                        "menu_items_without_tips": [],
                        "recovery_toggle": True, "tumble_toggle": True, "playblast_file": True,
                        "closed_editor_ignores_keys": True, "open_editor_uses_keys": True,
                        "grip_and_settings_button": True, "window_menu": True, "window_menu_once": True,
                        "window_menu_icon": True,
                        "show_keeps_bar": True, "drag_floats": True, "drag_moves_window": True,
                        "double_click_docks": True, "docked_tab_hidden": True, "settings_hide_section": True,
                        "settings_size_rebuild": True, "settings_reset": True}
            failed = [name for name, value in expected.items() if checks.get(name) != value]
            if checks["tween_slider_value"] != [7.5]:
                failed.append("tween_slider_value")
            if checks["bars_in_control"] != 1:
                failed.append("bars_in_control")
            if checks["dock_height"] > preferences.barHeight() + 6:
                failed.append("dock_height")
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
