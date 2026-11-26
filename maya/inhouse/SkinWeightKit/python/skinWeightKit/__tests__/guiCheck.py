"""使い捨ての Maya GUI で Skin Weight Kit を表示し、ドックの位置・部品・操作を確かめて画像を残す。

mlib の ``runGui.run_version`` の suite として実行する(作業中の Maya GUI では実行しない)::

    python maya\\inhouse\\SkinWeightKit\\python\\skinWeightKit\\__tests__\\run_gui.py --versions 2027
"""

import json
import os
import sys
import traceback
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.dirname(os.path.dirname(HERE))


def _check_weight_previews(widget, geo, skin, joints):
    """実際の確認ダイアログで取り消し・適用・貼り付けを比較する。"""
    import maya.cmds as cmds
    from skinWeightKit.ui.qt import QtCore, QtWidgets

    def select(index):
        cmds.select(f"{geo}.vtx[{index}]")
        widget.refresh()

    def rows():
        return [cmds.skinPercent(skin, f"{geo}.vtx[{index}]", query=True, value=True)
                for index in (19, 20, 21)]

    def dialog_text(show, button_name=None):
        messages = []

        def close_dialog():
            dialog = QtWidgets.QApplication.activeModalWidget()
            if isinstance(dialog, QtWidgets.QMessageBox):
                messages.append((dialog.text(), dialog.detailedText()))
                for button in dialog.buttons():
                    if button.text() == button_name:
                        button.click()
                        return
                dialog.reject()

        QtCore.QTimer.singleShot(0, close_dialog)
        show()
        return messages[0]

    buttons = {button.text(): button for button in widget.findChildren(QtWidgets.QPushButton)}
    select(0)
    buttons["Copy"].click()
    select(20)
    original = rows()
    title, details = dialog_text(buttons["Preview Paste"].click)
    paste_preview = title == "1 changed vertices\nLocked influences: None" and "vtx[20]" in details and rows() == original
    buttons["Paste"].click()
    pasted = rows()
    cmds.undo()
    paste_ok = paste_preview and pasted[1] != original[1] and pasted[::2] == original[::2] and rows() == original

    def preview_move():
        widget._preview_move(joints[0], joints[1])

    title, details = dialog_text(preview_move)
    move_preview = "1 changed vertices" in title and "vtx[20]" in details and rows() == original
    dialog_text(preview_move, "Apply")
    moved = rows()
    cmds.undo()
    move_ok = (move_preview and moved[1][0] == 0 and abs(moved[1][1] - sum(original[1][:2])) < 1e-6
               and moved[::2] == original[::2] and rows() == original)

    cmds.setAttr(joints[2] + ".liw", True)
    title, details = dialog_text(buttons["Preview Paste"].click)
    locked_preview = title.endswith("Locked influences: " + joints[2]) and joints[2] not in details and rows() == original
    buttons["Paste"].click()
    locked_rows = rows()
    cmds.undo()
    locked_ok = (locked_preview and locked_rows[1] != original[1] and locked_rows[1][2] == original[1][2]
                 and locked_rows[::2] == original[::2] and rows() == original)
    cmds.setAttr(joints[2] + ".liw", False)

    cmds.setAttr(joints[0] + ".rotateZ", 20)
    cmds.setAttr(joints[1] + ".rotateX", 35)
    buttons["Record Posed Mesh"].click()
    cmds.skinPercent(skin, geo + ".vtx[21]", transformValue=[(joints[1], 1.0)], zeroRemainingInfluences=True)
    title, details = dialog_text(buttons["Compare Posed Mesh"].click)
    pose_ok = title == "Changed vertices: 1. Outside edit range: 1" and "vtx[21]" in details and "outside" in details
    cmds.undo()
    title, _ = dialog_text(buttons["Compare Posed Mesh"].click)
    pose_ok = pose_ok and title == "Changed vertices: 0. Outside edit range: 0"
    cmds.setAttr(joints[0] + ".rotateZ", 0)
    cmds.setAttr(joints[1] + ".rotateX", 0)

    buttons["Record Settings"].click()
    cmds.setAttr(joints[2] + ".liw", True)
    title, details = dialog_text(buttons["Compare Settings"].click)
    buttons["Restore Settings"].click()
    restored = not cmds.getAttr(joints[2] + ".liw") and rows() == original
    cmds.undo()
    bind_ok = restored and cmds.getAttr(joints[2] + ".liw") and title == "Differences: 1" and joints[2] in details and "locked: False → True" in details
    cmds.setAttr(joints[2] + ".liw", False)

    widget._item_clicked(widget.tree.topLevelItem(0), 1)
    buttons["Cluster from Influence"].click()
    created = cmds.ls(type="cluster")
    cluster_ok = len(created) == 1 and abs(cmds.percent(created[0], geo + ".vtx[20]", query=True, value=True)[0] - original[1][0]) < 1e-6
    cmds.undo()
    cluster_ok = cluster_ok and not cmds.ls(type="cluster") and rows() == original
    select(20)

    # コピー元と名前が一致しないスケルトンでは、警告と全行の保持を確認する。
    from maya.api import OpenMaya as om
    buttons["Pick Source"].click()
    other = cmds.duplicate(geo, name="swkGuiOther")[0]
    cmds.move(30, 0, 0, other + ".vtx[21]", relative=True, worldSpace=True)
    cmds.select(clear=True)
    other_joint = cmds.joint(name="swkOtherJoint")
    other_skin = cmds.skinCluster(other_joint, other, toSelectedBones=True)[0]
    cmds.select(other + ".vtx[20]", other + ".vtx[21]")
    widget.refresh()

    def other_rows():
        return [cmds.skinPercent(other_skin, f"{other}.vtx[{i}]", query=True, value=True)
                for i in range(cmds.polyEvaluate(other, vertex=True))]

    before = other_rows()
    warnings = []

    def capture(message, kind, _data):
        if kind == om.MCommandMessage.kWarning:
            warnings.append(message)

    callback = om.MCommandMessage.addCommandOutputCallback(capture)
    try:
        for name in ("Preview Paste", "Paste"):
            buttons[name].click()
    finally:
        om.MMessage.removeCallback(callback)
    missing_ok = sum("Not influences of" in warning and joints[0] in warning for warning in warnings) == 2 and other_rows() == before

    # 距離上限を実際の入力画面で確定し、続く結果画面を読む。
    match_ok = True
    for method in ("index", "position"):
        widget.import_method.setCurrentIndex(widget.import_method.findData(method))
        messages = []
        def inspect_modal():
            dialog = QtWidgets.QApplication.activeModalWidget()
            if isinstance(dialog, QtWidgets.QInputDialog):
                dialog.setDoubleValue(0.001)
                dialog.accept()
                QtCore.QTimer.singleShot(0, inspect_modal)
            elif isinstance(dialog, QtWidgets.QMessageBox):
                messages.append((dialog.text(), dialog.detailedText()))
                dialog.accept()
        QtCore.QTimer.singleShot(0, inspect_modal)
        buttons["Preview Source Matches..."].click()
        match_ok = match_ok and bool(messages) and messages[0][0] == "1 of 2 vertices unmatched" and "vtx[21]  unmatched" in messages[0][1] and "vtx[20]  vtx[20]" in messages[0][1]
    match_ok = match_ok and other_rows() == before
    def enter_pairs():
        dialog = QtWidgets.QApplication.activeModalWidget()
        if isinstance(dialog, QtWidgets.QInputDialog):
            dialog.setTextValue("20 20\n21 21")
            dialog.accept()

    QtCore.QTimer.singleShot(0, enter_pairs)
    buttons["Record Seam..."].click()
    cmds.move(1, 0, 0, other + ".vtx[20]", relative=True, worldSpace=True)
    title, details = dialog_text(buttons["Compare Seam"].click)
    seam_ok = ("Worsened pairs: 1" in title and "Maximum:" in title and
               any("vtx[20] / vtx[20]" in line and "(worsened)" in line for line in details.splitlines()) and
               any("vtx[21] / vtx[21]" in line and "(worsened)" not in line for line in details.splitlines()))
    cmds.select(geo, other)
    widget.refresh()
    title, _ = dialog_text(buttons["Compare Bind Meshes"].click)
    bind_mesh_ok = "Topology matches" in title and "Local maximum:" in title and "World maximum:" in title and "vtx[21]" in title
    title, details = dialog_text(buttons["Compare Cage Output"].click)
    cage_ok = "Open boundary:" in title and "vtx[21]" in details
    cmds.delete(other, other_joint)
    select(20)

    return dict(cage_output=cage_ok, bind_mesh_comparison=bind_mesh_ok, move_preview=move_ok, paste_preview=paste_ok, locked_paste=locked_ok, missing_paste=missing_ok,
                posed_mesh=pose_ok, source_matches=match_ok, seam_distances=seam_ok, bind_settings=bind_ok, cluster_transfer=cluster_ok)


def main(output_dir=None, finished=None):
    """パネルを表示し、確認の結果を ``result.json`` に書いて finished を呼ぶ。

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

    state = {}

    def check():
        """表示の後、バインドした円柱を用意して部品を確かめ、頂点を選ぶ。"""
        try:
            import maya.OpenMayaUI as omui

            import skinWeightKit
            from skinWeightKit.ui import panel
            from skinWeightKit.ui.qt import QtWidgets, wrapInstance

            checks = result["checks"]
            # バインドした円柱を用意する。
            geo = cmds.polyCylinder(name="swkGui", height=8, subdivisionsY=8, subdivisionsX=8)[0]
            cmds.move(0, 4, 0, geo)
            cmds.makeIdentity(geo, apply=True, translate=True)
            cmds.select(clear=True)
            joints = [cmds.joint(name="swkGuiJnt{}".format(index), position=(0, index * 4, 0)) for index in range(3)]
            skin_name = cmds.skinCluster(joints, geo, toSelectedBones=True, maximumInfluences=3)[0]
            widget = panel._panel["widget"]
            checks["control_exists"] = bool(cmds.workspaceControl(panel.CONTROL, exists=True))
            # Windows メニューの項目: 2回登録しても1つだけで、Maya の項目(Outliner 等)も残っていること。
            from skinWeightKit.ui import startup
            startup.addWindowMenu()
            startup.addWindowMenu()
            items = cmds.menu(startup.WINDOW_MENU, query=True, itemArray=True) or []
            checks["window_menu_item"] = items.count(startup.WINDOW_MENU_ITEM) == 1 and len(items) > 5
            from skinWeightKit.ui import icons
            from skinWeightKit.ui.qt import QtGui
            pointer = omui.MQtUtil.findMenuItem(startup.WINDOW_MENU + "|" + startup.WINDOW_MENU_ITEM)
            action = wrapInstance(int(pointer), getattr(QtGui, "QAction", None) or QtWidgets.QAction)
            checks["window_menu_icon"] = not action.icon().isNull()
            icons.pixmap(256).save(str(output / "icon.png"))
            icons.pixmap(18).save(str(output / "icon18.png"))
            checks["widget_built"] = widget is not None and widget.isVisible()
            checks["docked"] = not cmds.workspaceControl(panel.CONTROL, query=True, floating=True)
            # 画面の右側にあるか(メインウィンドウの中央より右)。
            window = widget.window()
            left = widget.mapToGlobal(widget.rect().topLeft()).x()
            checks["on_right_side"] = left > window.mapToGlobal(window.rect().center()).x()
            control = wrapInstance(int(omui.MQtUtil.findControl(panel.CONTROL)), QtWidgets.QWidget)
            checks["panels_in_control"] = len(control.findChildren(panel.SkinWeightKitPanel))
            # どの部品にも、見出しと使い方の2行以上のツールチップがあること。
            parts = widget.findChildren(QtWidgets.QPushButton) + widget.findChildren(QtWidgets.QComboBox) + \
                widget.findChildren(QtWidgets.QAbstractSpinBox) + widget.findChildren(QtWidgets.QCheckBox) + \
                widget.findChildren(QtWidgets.QLineEdit) + widget.findChildren(QtWidgets.QTreeWidget)
            parts = [part for part in parts if not isinstance(part.parent(), (QtWidgets.QAbstractSpinBox,
                                                                                 QtWidgets.QComboBox))]
            checks["tooltips_missing"] = [type(part).__name__ + ":" + (getattr(part, "text", lambda: "")() or "")
                                          for part in parts if len(part.toolTip().splitlines()) < 2]
            # 選択に合わせて一覧が変わること(SelectionChanged はアイドル時に届くため、確認を次へ遅らせる)。
            cmds.select("{}.vtx[20]".format(geo), "{}.vtx[21]".format(geo))
            state.update(geo=geo, joints=joints, skin_name=skin_name, widget=widget, window=window)
            cmds.evalDeferred(verify, lowestPriority=True)
            return
        except Exception:
            result["error"] = traceback.format_exc()
        finish()

    def verify():
        """選択の変更が届いた後に、一覧と操作を確かめる。"""
        try:
            import skinWeightKit
            from skinWeightKit.ui import panel
            from skinWeightKit.ui.qt import QtWidgets

            checks = result["checks"]
            geo, joints, skin_name = state["geo"], state["joints"], state["skin_name"]
            widget, window = state["widget"], state["window"]
            QtWidgets.QApplication.processEvents()
            checks["title"] = widget.title.text()
            checks["influence_rows"] = widget.tree.topLevelItemCount()
            # アクティブにしてプリセットのボタンで値を設定する。
            item = widget.tree.topLevelItem(1)
            widget._item_clicked(item, 1)
            widget._preset(0.5)
            values = cmds.skinPercent(skin_name, "{}.vtx[20]".format(geo), query=True, value=True)
            checks["preset_value"] = round(values[1], 4)
            checks["preset_sum"] = round(sum(values), 4)
            cmds.undo()
            values = cmds.skinPercent(skin_name, "{}.vtx[20]".format(geo), query=True, value=True)
            checks["undo_restored"] = abs(values[1] - 0.5) > 1e-4
            checks.update(_check_weight_previews(widget, geo, skin_name, joints))
            cmds.select(f"{geo}.vtx[20]", f"{geo}.vtx[21]")
            widget.refresh()
            widget._item_clicked(widget.tree.topLevelItem(1), 1)
            # Slide のドラッグ: 押して量を変え、離すと1回の Undo で書く。
            start = cmds.skinPercent(skin_name, "{}.vtx[20]".format(geo), query=True, value=True)[1]
            checks["slide_started"] = widget._slide_start()
            widget._slide_drag(0.3)
            widget._slide_drag(0.1)
            widget._slide_finish()
            slid = cmds.skinPercent(skin_name, "{}.vtx[20]".format(geo), query=True, value=True)
            checks["slide_value"] = round(slid[1] - start, 4)
            checks["slide_sum"] = round(sum(slid), 4)
            cmds.undo()
            checks["slide_undo"] = round(cmds.skinPercent(skin_name, "{}.vtx[20]".format(geo), query=True,
                                                          value=True)[1] - start, 4)
            # 右クリック・ランプ・値のメニューの全項目に説明があること(メニューは出さずに項目を集める)。
            from skinWeightKit.ui import commands, popup
            original_exec = QtWidgets.QMenu.exec_
            captured = {}

            def capture(self, *args):
                """メニューを出さずに、サブメニューも含めて項目を集める。"""
                captured.setdefault("items", []).extend(
                    (action.text(), action.toolTip()) for action in self.actions()
                    if not action.isSeparator() and action.isEnabled())

            QtWidgets.QMenu.exec_ = capture
            try:
                # 値を変えると一覧を作り直すため、行を取り直す(アクティブでない行で、移動・ランプの項目も出す)。
                other = widget.tree.topLevelItem(0)
                widget._influence_menu(widget.tree.visualItemRect(other).center())
                widget._ramp_menu(widget.slider)
                checks["value_menu"] = popup.showValueMenu()
            finally:
                QtWidgets.QMenu.exec_ = original_exec
            items = captured.get("items", [])
            checks["menu_items"] = len(items)
            checks["menu_items_without_tips"] = [text for text, tip in items if not tip or tip == text]
            checks["has_move_and_ramp"] = all(any(text.startswith(prefix) for text, _tip in items)
                                              for prefix in ("Move active", "Ramp from", "Set 0.5"))
            checks["runtime_commands"] = all(cmds.runTimeCommand(name, exists=True) for name in commands.register())
            # Game Cleanup: メッシュ全体を診断し、最大2・8bit に整理して、1回の Undo で戻ること。
            cmds.select(geo)
            widget.refresh()
            widget.game_max.setCurrentIndex(widget.game_max.findData(2))
            widget._analyze()
            checks["analyze_report"] = "max influences used" in widget.report.text()
            widget._game_cleanup()
            counts = [sum(1 for value in cmds.skinPercent(skin_name, "{}.vtx[{}]".format(geo, index), query=True,
                                                          value=True) if value > 0.0) for index in range(0, 80, 7)]
            checks["cleanup_max_used"] = max(counts)
            checks["cleanup_report"] = widget.report.text().startswith("Cleaned")
            value = cmds.skinPercent(skin_name, "{}.vtx[40]".format(geo), query=True, value=True)
            checks["cleanup_on_grid"] = all(abs(item * 255 - round(item * 255)) < 1e-3 for item in value)
            cmds.undo()
            counts = [sum(1 for value in cmds.skinPercent(skin_name, "{}.vtx[{}]".format(geo, index), query=True,
                                                          value=True) if value > 0.0) for index in range(0, 80, 7)]
            checks["cleanup_undo"] = max(counts) > 2
            # Vertex Table: 開くと選んだ頂点の行が出て、セルを書き換えると値が入ること。
            cmds.select("{}.vtx[20]".format(geo), "{}.vtx[21]".format(geo))
            widget.refresh()
            widget.table_section.header.setChecked(True)
            checks["table_rows"] = widget.table.rowCount()
            column = [widget.table.horizontalHeaderItem(index).text()
                      for index in range(widget.table.columnCount())].index(joints[1])
            widget.table.item(0, column).setText("0.4")
            checks["table_edit"] = round(cmds.skinPercent(skin_name, "{}.vtx[{}]".format(geo, widget.table_vertices[0]),
                                                          transform=joints[1], query=True), 4)
            cmds.undo()
            widget.table_section.header.setChecked(False)
            # ジョイントだけを選ぶと、対象のメッシュを保ったまま、そのジョイントがアクティブになること。
            cmds.select("{}.vtx[20]".format(geo))
            widget.refresh()
            cmds.select(joints[2])
            widget.refresh()
            checks["joint_keeps_target"] = "swkGui" in widget.title.text()
            checks["joint_becomes_active"] = widget.active == joints[2]
            # Remove Selected Joints: 末端のジョイントを外し、ウェイトが親へ移ること。1回の Undo で戻ること。
            cmds.select(joints[2])
            widget._remove_joints()
            checks["remove_joints"] = joints[2] not in cmds.skinCluster(skin_name, query=True, influence=True)
            checks["remove_joints_sum"] = round(sum(cmds.skinPercent(skin_name, "{}.vtx[60]".format(geo), query=True,
                                                                     value=True)), 4)
            cmds.undo()
            checks["remove_joints_undo"] = joints[2] in cmds.skinCluster(skin_name, query=True, influence=True)
            cmds.select("{}.vtx[20]".format(geo), "{}.vtx[21]".format(geo))
            widget.refresh()
            QtWidgets.QApplication.processEvents()
            image = output / "skinWeightKit.png"
            widget.grab().save(str(image))
            result["screenshots"].append(str(image))
            whole = output / "skinWeightKit_window.png"
            window.grab().save(str(whole))
            result["screenshots"].append(str(whole))
            # 独自のブラシ: Remove のブラシにして、Maya のペイントが呼ぶ MEL の関数で1ストロークを塗る。
            import maya.mel as mel
            from skinWeightKit.ui import paint as paint_ui
            cmds.select(geo)
            widget.refresh()
            widget._item_clicked(widget.tree.topLevelItem(0), 1)
            widget._start_brush("remove")
            checks["brush_context"] = cmds.currentCtx() == paint_ui.CONTEXT
            shape = cmds.listRelatives(geo, shapes=True, fullPath=True)[0]
            before = cmds.skinPercent(skin_name, "{}.vtx[20]".format(geo), transform=joints[0], query=True)
            mel.eval('{}("{}")'.format(paint_ui.INITIALIZE, shape))
            mel.eval("{}(0, 20, 1.0)".format(paint_ui.SET_VALUE))
            mel.eval("{}(0)".format(paint_ui.FINALIZE))
            checks["brush_removed"] = before > 0.0 and cmds.skinPercent(
                skin_name, "{}.vtx[20]".format(geo), transform=joints[0], query=True) < 1e-6
            cmds.undo()
            checks["brush_undo"] = abs(cmds.skinPercent(skin_name, "{}.vtx[20]".format(geo), transform=joints[0],
                                                        query=True) - before) < 1e-5
            cmds.setToolTo("selectSuperContext")
            cmds.select("{}.vtx[20]".format(geo), "{}.vtx[21]".format(geo))
            widget.refresh()
            widget._item_clicked(widget.tree.topLevelItem(1), 1)
            # Paint のボタンで Maya の Paint Skin Weights ツールになり、アクティブなインフルエンスを塗ること。
            widget._paint()
            context = cmds.currentCtx()
            checks["paint_context"] = cmds.contextInfo(context, c=True)
            checks["paint_influence"] = cmds.artAttrSkinPaintCtx(context, query=True, influence=True)
            cmds.setToolTo("selectSuperContext")
            skinWeightKit.toggle()
            checks["toggle_hides"] = not cmds.workspaceControl(panel.CONTROL, exists=True)
            skinWeightKit.toggle()
            checks["toggle_shows"] = bool(cmds.workspaceControl(panel.CONTROL, exists=True))
            expected = {"posed_mesh": True, "bind_settings": True, "cluster_transfer": True, "seam_distances": True, "locked_paste": True, "missing_paste": True, "source_matches": True, "move_preview": True, "paste_preview": True, "control_exists": True, "window_menu_item": True, "window_menu_icon": True, "widget_built": True, "docked": True, "on_right_side": True,
                        "panels_in_control": 1, "tooltips_missing": [], "influence_rows": 3, "preset_value": 0.5,
                        "preset_sum": 1.0, "undo_restored": True, "menu_items_without_tips": [],
                        "paint_context": "artAttrSkin", "toggle_hides": True, "toggle_shows": True,
                        "slide_started": True, "slide_value": 0.1, "slide_sum": 1.0, "slide_undo": 0.0,
                        "value_menu": True, "has_move_and_ramp": True, "runtime_commands": True,
                        "analyze_report": True, "cleanup_max_used": 2, "cleanup_report": True,
                        "cleanup_on_grid": True, "cleanup_undo": True, "remove_joints": True,
                        "remove_joints_sum": 1.0, "remove_joints_undo": True, "table_rows": 2, "table_edit": 0.4,
                        "brush_context": True, "brush_removed": True, "brush_undo": True,
                        "joint_keeps_target": True, "joint_becomes_active": True}
            failed = [name for name, value in expected.items() if checks.get(name) != value]
            if not str(checks.get("paint_influence", "")).endswith(joints[1]):
                failed.append("paint_influence")
            if "2 verts" not in checks.get("title", ""):
                failed.append("title")
            result["failed"] = failed
            result["status"] = "passed" if not failed else "failed"
        except Exception:
            result["error"] = traceback.format_exc()
        finish()

    try:
        import skinWeightKit
        skinWeightKit.show()
        maya.utils.executeDeferred(lambda: cmds.evalDeferred(check, lowestPriority=True))
    except Exception:
        result["error"] = traceback.format_exc()
        finish()
