"""専用Maya GUIでSpline IKの生成とレイヤー操作を検証する。"""

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

    output = Path(output_dir)
    result = {"status": "running", "checks": []}
    editor = None

    def check(value, label):
        """検証結果を保存する。"""
        if not value:
            raise AssertionError(label)
        result["checks"].append(label)
        (output / "progress.json").write_text(json.dumps(result), encoding="utf-8")

    def row(role):
        """選択モジュールの行を返す。"""
        uuid = editor.current()[0].root.uuid()
        return next(
            item
            for item in editor.rows()
            if item.data(0, QtCore.Qt.UserRole)["root"] == uuid
            and item.data(0, QtCore.Qt.UserRole)["role"] == role
        )

    def steps():
        """idleを挟んでUIとChannel Box相当の操作を行う。"""
        nonlocal editor
        cmds.file(new=True, force=True)
        yield
        editor = show_layer_editor()
        editor.module_type.setCurrentIndex(4)
        editor.module_name.setText("spineDemo")
        editor.spline_joints.setValue(9)
        editor.spline_controls.setValue(5)
        check(
            editor.spline_options.isVisible() and not editor.skirt_options.isVisible(),
            "Spline creation options",
        )
        QtTest.QTest.mouseClick(editor.create_button, QtCore.Qt.LeftButton)
        yield
        rig, _ = editor.current()
        check(
            isinstance(rig, SplineRig) and len(rig.joints()) == 9 and len(rig.controls()) == 5,
            "UI spine creation",
        )
        check(
            not editor.add_button.isEnabled() and not editor.bake_button.isEnabled(),
            "Unsupported sample actions disabled",
        )
        rig.controls()[1].plug("tx").set(3)
        yield
        before = cmds.xform(rig.joints()[3], query=True, worldSpace=True, translation=True)
        check(abs(before[0]) > 0.2, "Curve control bends chain")
        editor.tree.setCurrentItem(row("spline:1"))
        editor.select_node()
        check(
            cmds.ls(selection=True, long=True) == [rig.controls()[1].fullName()],
            "Control selection",
        )
        editor.mode.setCurrentIndex(0)
        editor._run(editor.change_mode)
        yield
        after = cmds.xform(rig.joints()[3], query=True, worldSpace=True, translation=True)
        check(max(abs(a - b) for a, b in zip(before, after)) < 0.001, "IK to FK match")
        check(
            rig.graph().member("handle").plug("inCurve").source() is None, "FK disconnects solver"
        )
        cmds.undo()
        yield
        check(
            rig.mode() == "ik"
            and rig.graph().member("handle").plug("inCurve").source() is not None,
            "Mode Undo",
        )
        cmds.redo()
        yield
        check(rig.mode() == "fk", "Mode Redo")
        rig.set_mode("ik")
        yield
        row("spline").setCheckState(0, QtCore.Qt.Unchecked)
        yield
        check(
            not rig.layer_enabled()
            and rig.graph().member("handle").plug("inCurve").source() is None,
            "Layer checkbox",
        )
        cmds.undo()
        yield
        check(rig.layer_enabled(), "Layer Undo")
        cmds.setAttr(rig.root.fullName() + ".lod", 0)
        for _ in range(20):
            yield
            if rig.graph().member("handle").plug("inCurve").source() is None:
                break
        check(
            rig.graph().member("handle").plug("inCurve").source() is None,
            "Channel LOD disables solver",
        )
        cmds.undo()
        yield
        check(rig.lod() == 1, "LOD Undo")
        cmds.file(rename=str(output / "spline.ma"))
        cmds.file(save=True, type="mayaAscii")
        cmds.file(str(output / "spline.ma"), open=True, force=True, executeScriptNodes=False)
        yield
        rig = SplineRig("spineDemo")
        cmds.setAttr(rig.root.fullName() + ".mode", 0)
        for _ in range(20):
            yield
            if rig.graph().member("handle").plug("inCurve").source() is None:
                break
        check(
            rig.graph().member("handle").plug("inCurve").source() is None,
            "Reload restores watchers",
        )
        rig.set_mode("ik")
        editor.module_type.setCurrentIndex(5)
        editor.module_name.setText("tailDemo")
        QtTest.QTest.mouseClick(editor.create_button, QtCore.Qt.LeftButton)
        yield
        tail, _ = editor.current()
        check(
            isinstance(tail, SplineRig)
            and abs(
                cmds.xform(tail.joints()[-1], query=True, worldSpace=True, translation=True)[2] - 10
            )
            < 0.001,
            "UI tail creation",
        )
        editor.grab().save(str(output / "spline-editor.png"))
        editor.close()
        cmds.file(new=True, force=True)
        yield
        check(not SplineRig._jobs, "Scene cleanup releases watchers")

    iterator = steps()

    def advance():
        """次の検証へ進み、完了時に結果を通知する。"""
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
