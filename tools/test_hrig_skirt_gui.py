"""隔離GUIでスカート作成とチャンネル・レイヤー監視を検証する。"""

import json
from pathlib import Path
import traceback


def main(output_dir=None, finished=None):
    """専用テストGUIで操作し、結果をランナーへ返す。

    Args:
        output_dir (str): 証跡出力先。
        finished (Callable): 完了通知。
    """
    from maya import cmds, utils
    from PySide6 import QtCore, QtTest
    from hrig import show_layer_editor
    from hrig.skirtRig import SkirtRig

    output = Path(output_dir)
    result = {"status": "running", "checks": []}
    editor = None

    def check(value, label):
        """失敗箇所と進捗を記録する。"""
        if not value:
            raise AssertionError(label)
        result["checks"].append(label)
        (output / "progress.json").write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8"
        )

    def steps():
        """UI操作の間にidleを挟み、監視の更新も確認する。"""
        nonlocal editor
        cmds.file(new=True, force=True)
        yield
        editor = show_layer_editor()
        yield
        editor.module_type.setCurrentIndex(2)
        editor.module_name.setText("skirtDemo")
        QtTest.QTest.mouseClick(editor.create_button, QtCore.Qt.LeftButton)
        yield
        check(editor.tree.topLevelItemCount() == 1, "Create four-direction module")
        rig, _ = editor.getCurrent()
        check(isinstance(rig, SkirtRig) and len(rig.getJoints()) == 48, "Sixteen chains created")
        check(
            not editor.mode.isEnabled() and not editor.addButton.isEnabled(),
            "Limb-only controls disabled",
        )
        rig.driver_chains()[0][0].getPlug("rotateX").set(50)
        yield
        check(abs(rig.chains()[0][0].getPlug("rotateX").get() - 50) < 0.001, "Driver moves follower")
        rig.root.getPlug("blend").set(0.5)
        yield
        check(0 < rig.chains()[0][0].getPlug("rotateX").get() < 50, "Blend adjusts pose")
        cmds.setAttr(rig.root.getFullName() + ".enabled", False)
        yield
        (output / "jobs-state.json").write_text(
            json.dumps(
                {
                    "jobs": cmds.scriptJob(listJobs=True),
                    "owners": {key: value.exists() for key, value in SkirtRig._jobs.items()},
                    "busy": SkirtRig._busy,
                    "enabled": rig.layer_enabled(),
                    "undo": cmds.undoInfo(query=True, undoName=True),
                }
            ),
            encoding="utf-8",
        )
        check(
            rig.chains()[0][0].getPlug("rotateX").getSourceWithConversion() is None, "Channel Box disabled disconnects"
        )
        cmds.undo()
        yield
        (output / "undo-state.json").write_text(
            json.dumps(
                {
                    "enabled": rig.layer_enabled(),
                    "source": str(rig.chains()[0][0].getPlug("rotateX").getSourceWithConversion()),
                    "undo": cmds.undoInfo(query=True, undoName=True),
                    "redo": cmds.undoInfo(query=True, redoName=True),
                }
            ),
            encoding="utf-8",
        )
        check(
            rig.layer_enabled() and rig.chains()[0][0].getPlug("rotateX").getSourceWithConversion() is not None,
            "Channel Undo restores output",
        )
        cmds.redo()
        yield
        check(
            not rig.layer_enabled() and rig.chains()[0][0].getPlug("rotateX").getSourceWithConversion() is None,
            "Channel Redo restores disabled state",
        )
        rig.set_layer_enabled("radial", True)
        yield
        for row in editor.rows():
            if row.data(0, QtCore.Qt.UserRole)["role"] == "radial":
                row.setCheckState(0, QtCore.Qt.Unchecked)
                break
        yield
        check(not rig.layer_enabled(), "Layer checkbox changes enabled")
        rig.set_layer_enabled("radial", True)
        cmds.setAttr(rig.root.getFullName() + ".lod", 0)
        yield
        check(rig.chains()[0][0].getPlug("rotateX").getSourceWithConversion() is None, "Channel LOD stops output")
        rig.set_lod(1)
        rig.root.rename("renamedSkirt")
        yield
        cmds.file(rename=str(output / "skirt.ma"))
        cmds.file(save=True, type="mayaAscii")
        cmds.file(str(output / "skirt.ma"), open=True, force=True, executeScriptNodes=False)
        yield
        rig = SkirtRig("renamedSkirt")
        cmds.setAttr(rig.root.getFullName() + ".enabled", False)
        yield
        check(rig.chains()[0][0].getPlug("rotateX").getSourceWithConversion() is None, "Reload restores attribute jobs")
        rig.set_layer_enabled("radial", True)
        editor.module_type.setCurrentIndex(3)
        editor.module_name.setText("skirtEight")
        QtTest.QTest.mouseClick(editor.create_button, QtCore.Qt.LeftButton)
        yield
        check(len(editor.getCurrent()[0].driver_chains()) == 8, "Eight-direction UI sample")
        editor.module_type.setCurrentIndex(0)
        editor.module_name.setText("limbSample")
        QtTest.QTest.mouseClick(editor.create_button, QtCore.Qt.LeftButton)
        yield
        check(
            editor.tree.topLevelItemCount() == 3 and editor.mode.isEnabled(),
            "Limb and skirts coexist",
        )
        editor.grab().save(str(output / "skirt-editor.png"))
        editor.close()
        cmds.file(new=True, force=True)
        yield
        check(not SkirtRig._jobs, "New scene removes skirt watchers")

    iterator = steps()

    def advance():
        """次のidleで検証を進める。"""
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

    # 描画開始後もArnold/HIKの遅延登録が続くため、起動のUndo編集と操作を分離する。
    QtCore.QTimer.singleShot(5000, advance)
