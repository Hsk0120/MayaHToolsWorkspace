"""専用Maya GUIで指・Aim・Tweak・Splineフィット・ポーズ登録を検証する。"""

from maya import cmds

import json
from pathlib import Path
import traceback


def main(output_dir=None, finished=None):
    """専用GUIランナーから実行する。

    Args:
        output_dir (str): 証跡保存先。
        finished (Callable): 完了通知。
    """
    from maya import cmds, utils
    from PySide6 import QtCore, QtTest
    from hrig import show_layer_editor
    from hrig.splineRig import SplineRig
    from hrig.limb import LimbRig
    from hrig import channel_controls

    output = Path(output_dir)
    result = {"status": "running", "checks": []}
    editor = None

    def check(value, label):
        """結果を記録する。"""
        if not value:
            raise AssertionError(label)
        result["checks"].append(label)
        result["undo"] = dict(
            enabled=cmds.undoInfo(query=True, state=True),
            empty=cmds.undoInfo(query=True, undoQueueEmpty=True),
            name=cmds.undoInfo(query=True, undoName=True),
        )
        (output / "progress.json").write_text(json.dumps(result), encoding="utf-8")

    def row(role):
        """選択モジュールの行を返す。"""
        uuid = editor.getCurrent()[0].root.getUuid()
        return next(
            i
            for i in editor.rows()
            if i.data(0, QtCore.Qt.UserRole)["root"] == uuid
            and i.data(0, QtCore.Qt.UserRole)["role"] == role
        )

    def steps():
        """各UI操作の間にidleを挟む。"""
        nonlocal editor
        from hrig.fingerRig import FingerRig
        from hrig.aimRig import AimRig
        from hrig.tweakLayer import TweakLayer
        from hrig.poseEditor import PoseEditor
        from hrig.moduleRegistry import ModuleRegistry
        from PySide6 import QtWidgets

        import hlib

        called = []
        hlib.executeDeferred(lambda value: called.append(value), "deferred")
        yield
        check(called == ["deferred"], "Deferred callback via hlib")
        item = cmds.menu(
            "typedCommandTestMenu", label="Typed test", parent=hlib.common.MainWindow.getName()
        )
        check(isinstance(item, str) and cmds.menu(item, exists=True), "Native menu reference")
        child = cmds.menuItem(label="Test", parent=item)
        check(cmds.menuItem(child, exists=True), "Native menuItem parent")
        cmds.deleteUI(item, menu=True)
        check(not cmds.menu(item, exists=True), "Delete native UI")

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True, infinity=True)
        yield
        from hrig.menu import Menu

        Menu.install()
        Menu.install()
        check(cmds.menu(Menu.NAME, exists=True), "Top hrig menu exists")
        items = cmds.menu(Menu.NAME, query=True, itemArray=True)
        check(len(items) == 5, "Repeated menu install is unique")
        editor = Menu.run("editor")
        editor.module_type.setCurrentIndex(6)
        editor.module_name.setText("uiHand")
        QtTest.QTest.mouseClick(editor.create_button, QtCore.Qt.LeftButton)
        yield
        finger = editor.getCurrent()[0]
        check(isinstance(finger, FingerRig), "Create finger UI")
        finger.group("layer").getPlug("curl").set(35)
        yield
        check(abs(finger.getMembers("targets")[0].getPlug("rz").get() - 35) < 1e-4, "Curl live")
        row("finger").setCheckState(0, QtCore.Qt.Unchecked)
        yield
        check(
            abs(finger.getMembers("targets")[0].getPlug("rz").get()) < 1e-4,
            "Layer checkbox disables curl",
        )
        cmds.undo()
        yield
        check(finger.layer_enabled("finger"), "Finger Undo")
        cmds.redo()
        yield
        check(not finger.layer_enabled("finger"), "Finger Redo")
        cmds.setAttr(finger.root.getFullName() + ".enabled", True)
        for _ in range(20):
            yield
            if finger.getMembers("targets")[0].getPlug("rx").getSourceWithConversion() is not None:
                break
        check(
            abs(finger.getMembers("targets")[0].getPlug("rz").get() - 35) < 1e-4,
            "Channel Box restores curl",
        )
        editor.layer_type.setCurrentIndex(editor.layer_type.findData("tweak"))
        QtTest.QTest.mouseClick(editor.addButton, QtCore.Qt.LeftButton)
        yield
        tweaks = TweakLayer(finger)
        check(len(tweaks.groups()) == 1, "Tweak added through UI")
        group = next(iter(tweaks.groups().values()))
        control = group.getPlug("control").getSourceWithConversion().getNode()
        control.getPlug("ty").set(0.5)
        row("tweak:" + group.getPlug("tweakId").get()).setCheckState(0, QtCore.Qt.Unchecked)
        yield
        check(
            group.getPlug("joint").getSourceWithConversion().getNode().getPlug("offsetParentMatrix").getSourceWithConversion() is None,
            "Tweak checkbox stops input",
        )
        cmds.undo()
        yield
        check(
            group.getPlug("joint").getSourceWithConversion().getNode().getPlug("offsetParentMatrix").getSourceWithConversion() is not None,
            "Tweak Undo restores input",
        )
        Menu.run("aim")
        yield
        aim = editor.getCurrent()[0]
        check(isinstance(aim, AimRig), "Create Aim UI")
        aim.getMembers("controls")[1].getPlug("tx").set(4)
        check(abs(aim.getMembers("targets")[0].getPlug("ry").get()) > 20, "Aim target follows")
        editor.module_type.setCurrentIndex(4)
        editor.module_name.setText("uiSpine")
        QtTest.QTest.mouseClick(editor.create_button, QtCore.Qt.LeftButton)
        yield
        spline = editor.getCurrent()[0]
        editor.mode.setCurrentIndex(0)
        editor._run(editor.change_mode)
        spline.getMembers("fk")[2].getPlug("rz").set(10)
        editor.mode.setCurrentIndex(1)
        editor._run(editor.change_mode)
        yield
        check(
            spline.mode() == "ik" and "最大位置誤差" in editor.status.text(),
            "Spline FK to IK reports approximation",
        )
        editor.module_type.setCurrentIndex(2)
        editor.module_name.setText("uiSkirt")
        QtTest.QTest.mouseClick(editor.create_button, QtCore.Qt.LeftButton)
        yield
        skirt = editor.getCurrent()[0]
        QtTest.QTest.mouseClick(editor.pose_button, QtCore.Qt.LeftButton)
        yield
        pose = editor._pose_editor
        check(isinstance(pose, PoseEditor), "Open pose registration UI")
        pose.capture()
        skirt.driver_chains()[0][0].getPlug("rx").set(30)
        pose.capture()
        pose.table.setItem(1, 4, QtWidgets.QTableWidgetItem("15"))
        pose.apply()
        yield
        check(
            abs(pose.graph().container.getPlug("outputs[2]").get() - 15) < 1e-3,
            "Register poses and correction",
        )
        skirt.driver_chains()[0][0].getPlug("rx").set(60)
        pose.capture()
        pose.table.setItem(2, 4, QtWidgets.QTableWidgetItem("25"))
        pose.apply()
        yield
        check(len(pose.graph().data()["poses"]) == 3, "Add registration preserves graph")
        pose.table.setItem(2, 4, QtWidgets.QTableWidgetItem("28"))
        pose.apply()
        check(abs(pose.graph().container.getPlug("outputs[2]").get() - 28) < 1e-3, "Edit pose output")
        pose.table.selectRow(2)
        pose.remove()
        pose.apply()
        check(len(pose.graph().data()["poses"]) == 2, "Delete registration")
        cmds.undo()
        yield
        pose.reload()
        check(pose.table.rowCount() == 3, "Pose edit Undo and reload")
        pose.grab().save(str(output / "pose-editor.png"))
        pose.close()
        cmds.file(rename=str(output / "controls.ma"))
        cmds.file(save=True, type="mayaAscii")
        cmds.file(str(output / "controls.ma"), open=True, force=True, executeScriptNodes=False)
        yield
        finger = ModuleRegistry.get("uiHand")
        cmds.setAttr(finger.root.getFullName() + ".enabled", False)
        for _ in range(20):
            yield
            if finger.getMembers("targets")[0].getPlug("rx").getSourceWithConversion() is None:
                break
        check(
            finger.getMembers("targets")[0].getPlug("rx").getSourceWithConversion() is None,
            "Reload restores finger watcher",
        )
        group = next(iter(TweakLayer(finger).groups().values()))
        cmds.setAttr(group.getFullName() + ".enabled", False)
        for _ in range(20):
            yield
            if group.getPlug("joint").getSourceWithConversion().getNode().getPlug("offsetParentMatrix").getSourceWithConversion() is None:
                break
        check(
            group.getPlug("joint").getSourceWithConversion().getNode().getPlug("offsetParentMatrix").getSourceWithConversion() is None,
            "Reload restores Tweak watcher",
        )
        editor.grab().save(str(output / "layers.png"))
        editor.close()
        cmds.file(new=True, force=True)
        yield
        from hrig.controlRig import ControlRig

        check(not ControlRig._jobs and not TweakLayer._jobs, "Scene cleanup releases new watchers")

        # 標準エディターのidle処理を、シーン読込の監視検証から分離する。
        from hlib.common import MainWindow
        from hlib.common import NodeEditor
        from hlib.common import GraphEditor

        check(cmds.window(MainWindow.getName(), exists=True), "Main window name")
        NodeEditor.show()
        yield
        check(bool(cmds.getPanel(scriptType="nodeEditorPanel")), "Open standard Node Editor")
        GraphEditor.show()
        yield
        check(bool(cmds.getPanel(scriptType="graphEditor")), "Open standard Graph Editor")

    iterator = steps()

    def advance():
        """検証を進めて終了を通知する。"""
        try:
            utils.processIdleEvents()
            next(iterator)
            QtCore.QTimer.singleShot(300, advance)
            return
        except StopIteration:
            result["status"] = "passed"
        except Exception:
            result.update(status="failed", error=traceback.format_exc())
            if editor is not None:
                editor.grab().save(str(output / "failure.png"))
        (output / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if finished:
            finished(result)

    # 遅延したMaya起動処理とUndo検証を分離する。検証途中でUndoを再有効化しない。
    QtCore.QTimer.singleShot(15000, advance)
