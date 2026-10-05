"""専用Maya GUIで伸縮レイヤーの追加・編集・切替を検証する。"""

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
        uuid = editor.current()[0].root.uuid()
        return next(
            i
            for i in editor.rows()
            if i.data(0, QtCore.Qt.UserRole)["root"] == uuid
            and i.data(0, QtCore.Qt.UserRole)["role"] == role
        )

    def steps():
        """idleを挟んで作成とチャンネル操作を行う。"""
        nonlocal editor
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True, infinity=True)
        yield
        editor = show_layer_editor()
        editor.module_type.setCurrentIndex(4)
        editor.module_name.setText("stretchSpine")
        QtTest.QTest.mouseClick(editor.create_button, QtCore.Qt.LeftButton)
        yield
        editor.layer_type.setCurrentIndex(editor.layer_type.findData("stretch"))
        check(editor.addButton.isEnabled(), "Spline stretch available")
        QtTest.QTest.mouseClick(editor.addButton, QtCore.Qt.LeftButton)
        yield
        spline, _ = editor.current()
        check(spline.root.hasAttr("stretchGroup"), "UI adds spline layer")
        editor.tree.setCurrentItem(row("stretch"))
        editor.select_node()
        settings = spline.root.plug("stretchGroup").sourceWithConversion().node()
        check(
            cmds.ls(selection=True, long=True) == [settings.fullName()],
            "Spline settings selection",
        )
        spline.controls()[-1].plug("ty").set(10)
        yield
        check(
            abs(cmds.xform(spline.joints()[-1], q=True, ws=True, t=True)[1] - 20) < 0.001,
            "Spline reaches stretched endpoint",
        )
        settings.plug("volume").set(0)
        check(
            abs(cmds.getAttr(spline.joints()[2] + ".scaleY") - 1) < 0.001, "Volume adjustment live"
        )
        row("stretch").setCheckState(0, QtCore.Qt.Unchecked)
        yield
        check(spline.members("ik")[1].plug("tx").sourceWithConversion() is None, "Spline layer stops calculation")
        cmds.undo()
        yield
        check(spline.layer_enabled("stretch"), "Spline layer Undo")
        cmds.redo()
        yield
        check(not spline.layer_enabled("stretch"), "Spline layer Redo")
        spline.set_layer_enabled("stretch", True)
        editor.module_type.setCurrentIndex(0)
        editor.module_name.setText("stretchArm")
        QtTest.QTest.mouseClick(editor.create_button, QtCore.Qt.LeftButton)
        yield
        QtTest.QTest.mouseClick(editor.addButton, QtCore.Qt.LeftButton)
        yield
        limb, _ = editor.current()
        check(isinstance(limb, LimbRig) and limb.root.hasAttr("stretchGroup"), "UI adds arm layer")
        limb.set_mode("ik")
        limb.set_layer_enabled("soft", False)
        cmds.setAttr(limb.controls()["target"] + ".tx", 7)
        yield
        check(
            abs(cmds.xform(limb.joints()[2], q=True, ws=True, t=True)[0] - 15) < 0.001,
            "Arm reaches stretched endpoint",
        )
        settings = limb.root.plug("stretchGroup").sourceWithConversion().node()
        cmds.setAttr(settings.fullName() + ".enabled", False)
        for _ in range(20):
            yield
            if not limb.layer_enabled("stretch"):
                break
        check(
            not limb.layer_enabled("stretch") and cmds.getAttr(limb._member("ik1") + ".tx") == 5,
            "Channel Box disables arm layer",
        )
        cmds.undo()
        yield
        check(limb.layer_enabled("stretch"), "Arm Channel Undo")
        cmds.redo()
        yield
        check(not limb.layer_enabled("stretch"), "Arm Channel Redo")
        limb.set_layer_enabled("stretch", True)
        limb.set_lod(0)
        check(
            cmds.listConnections(limb._member("ik1") + ".tx", s=True, d=False) is None,
            "Arm LOD cuts length input",
        )
        limb.set_lod(1)
        cmds.file(rename=str(output / "stretch.ma"))
        cmds.file(save=True, type="mayaAscii")
        cmds.file(str(output / "stretch.ma"), open=True, force=True, executeScriptNodes=False)
        yield
        limb = LimbRig("stretchArm")
        settings = limb.root.plug("stretchGroup").sourceWithConversion().node()
        cmds.setAttr(settings.fullName() + ".enabled", False)
        for _ in range(20):
            yield
            if not limb.layer_enabled("stretch"):
                break
        check(not limb.layer_enabled("stretch"), "Reload restores arm watcher")
        limb.set_layer_enabled("stretch", True)
        editor.tree.scrollToItem(row("stretch"))
        editor.grab().save(str(output / "stretch-editor.png"))
        editor.close()
        cmds.file(new=True, force=True)
        yield
        check(not SplineRig._jobs and not channel_controls._jobs, "Scene cleanup releases watchers")

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
