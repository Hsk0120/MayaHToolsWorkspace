"""隔離Mayaで揺れベイクとポーズ補正のUIを検証する。"""

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
    from hrig.skirtRig import SkirtRig
    from hrig.secondaryLayer import SecondaryLayer

    output = Path(output_dir)
    result = {"status": "running", "checks": []}
    editor = None

    def check(value, label):
        """進捗を保存し、失敗を検出する。"""
        if not value:
            raise AssertionError(label)
        result["checks"].append(label)
        (output / "progress.json").write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8"
        )

    def row(kind):
        """選択モジュールの指定行を返す。"""
        uuid = editor.getCurrent()[0].root.getUuid()
        return next(
            item
            for item in editor.rows()
            if item.data(0, QtCore.Qt.UserRole)["root"] == uuid
            and item.data(0, QtCore.Qt.UserRole)["role"] == kind
        )

    def steps():
        """GUI idleを挟んで操作する。"""
        nonlocal editor
        cmds.file(new=True, force=True)
        cmds.playbackOptions(minTime=1, maxTime=24)
        yield
        editor = show_layer_editor()
        yield
        editor.module_type.setCurrentIndex(2)
        editor.module_name.setText("secondaryDemo")
        editor.skirt_count.setValue(8)
        QtTest.QTest.mouseClick(editor.create_button, QtCore.Qt.LeftButton)
        yield
        rig, _ = editor.getCurrent()
        source = rig.driver_chains()[0][0]
        for time, value in ((1, 0), (8, 60), (24, 60)):
            cmds.setKeyframe(source.getFullName(), attribute="rx", time=time, value=value)
        cmds.currentTime(8)
        editor.layer_type.setCurrentIndex(editor.layer_type.findData("spring"))
        check(editor.addButton.isEnabled(), "Spring sample available")
        QtTest.QTest.mouseClick(editor.addButton, QtCore.Qt.LeftButton)
        yield
        group = SecondaryLayer(rig).groups()[0]
        check(group.getPlug("baked").get(), "UI creates baked spring")
        check(cmds.currentTime(query=True) == 8, "Bake restores current frame")
        target = SecondaryLayer._members(group, "targets")[0]
        check(abs(target.getPlug("rx").get() - 60) > 1, "Spring lag visible")
        group.getPlug("frequency").set(6)
        old = target.getPlug("rx").get()
        QtTest.QTest.mouseClick(editor.bake_button, QtCore.Qt.LeftButton)
        yield
        check(abs(target.getPlug("rx").get() - old) > 0.1, "Rebake uses settings")
        row("spring").setCheckState(0, QtCore.Qt.Unchecked)
        yield
        check(not rig.layer_enabled("spring"), "Spring checkbox")
        check(
            abs(rig.chains()[0][0].getPlug("rx").get() - 60) < 0.001, "Disabled routes original driver"
        )
        cmds.undo()
        yield
        check(rig.layer_enabled("spring"), "Spring Undo")
        editor.layer_type.setCurrentIndex(editor.layer_type.findData("pose"))
        QtTest.QTest.mouseClick(editor.addButton, QtCore.Qt.LeftButton)
        yield
        graph = group.getPlug("poseGraph").getSourceWithConversion().getNode()
        check(abs(graph.getPlug("outputs[2]").get() - 20) < 0.001, "Pose registered value")
        source.getPlug("rz").set(60)
        yield
        check(abs(graph.getPlug("outputs[0]").get() + 20) < 0.001, "Two-input pose combination")
        cmds.setAttr(rig.root.getFullName() + ".hrigEnabled_pose", False)
        yield
        for _ in range(20):
            if SecondaryLayer._members(group, "poses")[0].getPlug("inputRotateX").getSourceWithConversion() is None:
                break
            yield
        check(
            SecondaryLayer._members(group, "poses")[0].getPlug("inputRotateX").getSourceWithConversion() is None,
            "Pose Channel disable",
        )
        cmds.undo()
        yield
        check(rig.layer_enabled("pose"), "Pose Channel Undo")
        cmds.redo()
        yield
        check(not rig.layer_enabled("pose"), "Pose Channel Redo")
        rig.set_layer_enabled("pose", True)
        rig.set_lod(0)
        yield
        check(
            SecondaryLayer._members(group, "blends")[0].getPlug("inRotateX2").getSourceWithConversion() is None,
            "LOD drops spring input",
        )
        check(
            SecondaryLayer._members(group, "poses")[0].getPlug("inputRotateX").getSourceWithConversion() is None,
            "LOD drops pose input",
        )
        rig.set_lod(1)
        cmds.file(rename=str(output / "secondary.ma"))
        cmds.file(save=True, type="mayaAscii")
        cmds.file(str(output / "secondary.ma"), open=True, force=True, executeScriptNodes=False)
        yield
        rig = SkirtRig("secondaryDemo")
        group = SecondaryLayer(rig).groups()[0]
        check(
            group.getPlug("baked").get() and group.getPlug("poseGraph").getSourceWithConversion() is not None,
            "Reload cache and pose data",
        )
        cmds.setAttr(rig.root.getFullName() + ".hrigEnabled_spring", False)
        yield
        check(
            SecondaryLayer._members(group, "blends")[0].getPlug("inRotateX2").getSourceWithConversion() is None,
            "Reload watchers",
        )
        rig.set_layer_enabled("spring", True)
        editor.tree.scrollToItem(row("spring"))
        editor.grab().save(str(output / "secondary-editor.png"))
        editor.close()
        cmds.file(new=True, force=True)
        yield
        check(not SkirtRig._jobs, "Scene clear releases watchers")

    iterator = steps()

    def advance():
        """次の検証へ進み、結果をランナーへ返す。"""
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
