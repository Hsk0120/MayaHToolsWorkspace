"""専用GUIで回転追従サンプルと監視・永続化を検証する。"""

import json
from pathlib import Path
import traceback


def main(output_dir=None, finished=None):
    """隔離GUIランナーからテストを開始する。

    Args:
        output_dir (str): 証跡保存先。
        finished (Callable): 終了通知。
    """
    from maya import cmds, utils
    from PySide6 import QtCore, QtTest
    import hlib
    from hrig import show_layer_editor
    from hrig.skirtRig import SkirtRig

    output = Path(output_dir)
    result = {"status": "running", "checks": []}
    editor = None

    def check(value, label):
        """検証結果を記録する。"""
        if not value:
            raise AssertionError(label)
        result["checks"].append(label)
        (output / "progress.json").write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8"
        )

    def follow_row():
        """現在モジュールの追従レイヤー行を返す。"""
        uuid = editor.current()[0].root.uuid()
        return next(
            item
            for item in editor.rows()
            if item.data(0, QtCore.Qt.UserRole)["root"] == uuid
            and item.data(0, QtCore.Qt.UserRole)["role"] == "follow"
        )

    def steps():
        """イベント処理を挟んでUIとChannel Box相当の操作を実行する。"""
        nonlocal editor
        cmds.file(new=True, force=True)
        yield
        editor = show_layer_editor()
        yield
        QtTest.QTest.mouseClick(editor.create_button, QtCore.Qt.LeftButton)
        yield
        rig, _ = editor.current()
        for kind in ("followTwist", "followSwing", "followHalf"):
            editor.layer_type.setCurrentIndex(editor.layer_type.findData(kind))
            editor.ratio.setValue(50)
            editor.axis.setCurrentText("x")
            QtTest.QTest.mouseClick(editor.add_button, QtCore.Qt.LeftButton)
            yield
            check(not editor.status.text().startswith("操作できません"), "Create " + kind)
        check(len(rig.follow_joints()) == 3 and follow_row().childCount() == 3, "Three follow rows")
        cmds.setAttr(rig.controls()["fk1"] + ".rx", 60)
        settings = rig.follow_settings("followHalf1")
        graph = settings.plug("graph").source().node
        original = graph.plug("matrix").get()
        settings.plug("ratio").set(0)
        yield
        check(graph.plug("matrix").get() != original, "Ratio live DG control")
        settings.plug("ratio").set(0.5)
        channel = rig._member("channel_follow")
        cmds.setAttr(channel + ".enabled", False)
        yield
        for _ in range(20):
            if hlib.getPlug(rig.follow_joints()[0] + ".offsetParentMatrix").source() is None:
                break
            yield
        (output / "channel-state.json").write_text(
            json.dumps(
                {
                    "channel": cmds.getAttr(channel + ".enabled"),
                    "root": rig.layer_enabled("follow"),
                    "jobs": [
                        str(job)
                        for job in cmds.scriptJob(listJobs=True)
                        if "follow" in str(job) or "_changed" in str(job)
                    ],
                    "undo": cmds.undoInfo(query=True, undoName=True),
                }
            ),
            encoding="utf-8",
        )
        check(
            hlib.getPlug(rig.follow_joints()[0] + ".offsetParentMatrix").source() is None,
            "Limb Channel disabled",
        )
        cmds.undo()
        yield
        check(
            rig.layer_enabled("follow")
            and hlib.getPlug(rig.follow_joints()[0] + ".offsetParentMatrix").source() is not None,
            "Limb Channel Undo",
        )
        cmds.redo()
        yield
        check(not rig.layer_enabled("follow"), "Limb Channel Redo")
        rig.set_layer_enabled("follow", True)
        editor.module_type.setCurrentIndex(2)
        editor.module_name.setText("skirtFollow")
        editor.skirt_count.setValue(8)
        QtTest.QTest.mouseClick(editor.create_button, QtCore.Qt.LeftButton)
        yield
        rig, _ = editor.current()
        editor.layer_type.setCurrentIndex(editor.layer_type.findData("followTwist"))
        editor.axis.setCurrentText("y")
        editor.ratio.setValue(25)
        check(editor.add_button.isEnabled(), "Skirt supports follow sample")
        QtTest.QTest.mouseClick(editor.add_button, QtCore.Qt.LeftButton)
        yield
        check(len(rig.follow_joints()) == 1, "Skirt follow created")
        check(rig.follow_settings("followTwist1").plug("ratio").get() == 0.25, "UI ratio forwarded")
        follow_row().setCheckState(0, QtCore.Qt.Unchecked)
        yield
        check(not rig.layer_enabled("follow"), "Skirt follow checkbox")
        rig.set_layer_enabled("follow", True)
        yield
        cmds.setAttr(rig.root.fullName() + ".hrigEnabled_follow", False)
        yield
        check(
            hlib.getPlug(rig.follow_joints()[0] + ".offsetParentMatrix").source() is None,
            "Skirt Channel disabled",
        )
        cmds.undo()
        yield
        check(rig.layer_enabled("follow"), "Skirt Channel Undo")
        cmds.redo()
        yield
        check(not rig.layer_enabled("follow"), "Skirt Channel Redo")
        rig.set_layer_enabled("follow", True)
        rig.root.plug("lod").set(0)
        yield
        check(
            hlib.getPlug(rig.follow_joints()[0] + ".offsetParentMatrix").source() is None,
            "Skirt LOD disconnects follow",
        )
        rig.set_lod(1)
        cmds.file(rename=str(output / "follow.ma"))
        cmds.file(save=True, type="mayaAscii")
        cmds.file(str(output / "follow.ma"), open=True, force=True, executeScriptNodes=False)
        yield
        rig = SkirtRig("skirtFollow")
        check(len(rig.follow_joints()) == 1, "Save reload keeps follow references")
        cmds.setAttr(rig.root.fullName() + ".hrigEnabled_follow", False)
        yield
        check(
            hlib.getPlug(rig.follow_joints()[0] + ".offsetParentMatrix").source() is None,
            "Save reload restores jobs",
        )
        rig.set_layer_enabled("follow", True)
        for item in editor.rows():
            if item.data(0, QtCore.Qt.UserRole)["root"] == rig.root.uuid():
                editor.tree.setCurrentItem(item)
                break
        yield
        editor.grab().save(str(output / "follow-editor.png"))
        editor.close()
        cmds.file(new=True, force=True)
        yield
        check(not SkirtRig._jobs, "Scene clear removes jobs")

    iterator = steps()

    def advance():
        """GUI idleごとに次の検証を実行する。"""
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

    QtCore.QTimer.singleShot(5000, advance)
