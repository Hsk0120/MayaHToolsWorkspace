"""専用Maya GUIでレイヤーエディターを操作し、終了時に保存確認を出さない。"""

import json
import traceback
from pathlib import Path


def main(output_dir=None, finished=None):
    """隔離ランナーからUI操作テストを開始する。

    Args:
        output_dir (str): 証跡保存先。
        finished (Callable): 完了時のコールバック。
    """
    from maya import cmds, utils
    from PySide6 import QtCore, QtTest, QtWidgets
    from hrig import show_layer_editor
    from hrig.drivenLayer import DrivenLayer

    output = Path(output_dir)
    result = {"status": "running", "checks": []}
    editor = None
    diagnostic = QtCore.QTimer(QtWidgets.QApplication.instance())

    def inspect_windows():
        """モーダル待ちを含むテスト用GUIの状態を記録する。"""
        windows = [
            {"title": w.windowTitle(), "modal": w.isModal(), "class": w.metaObject().className()}
            for w in QtWidgets.QApplication.topLevelWidgets()
            if w.isVisible()
        ]
        (output / "windows.json").write_text(
            json.dumps(windows, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    diagnostic.timeout.connect(inspect_windows)
    diagnostic.start(5000)

    def check(value, label):
        """確認結果を追記する。"""
        if not value:
            raise AssertionError(label)
        result["checks"].append(label)
        (output / "progress.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def row(role):
        """選択部位の指定レイヤー行を取得する。"""
        rig, _ = editor.current()
        for item in editor.rows():
            data = item.data(0, QtCore.Qt.UserRole)
            if data["root"] == rig.root.uuid() and data["role"] == role:
                return item
        raise AssertionError("Row missing: " + role)

    def steps():
        """クリックとイベント処理を交互に進める。"""
        nonlocal editor
        cmds.file(new=True, force=True)
        editor = show_layer_editor()
        yield
        check(editor.isVisible(), "Editor visible")
        check(show_layer_editor() is editor, "Single window reused")
        QtTest.QTest.mouseClick(editor.create_button, QtCore.Qt.LeftButton)
        yield
        check(editor.tree.topLevelItemCount() == 1, "Create module button")
        rig, _ = editor.current()
        check(rig.mode() == "fk", "Base module starts in FK")
        for kind in ("twist", "bend", "driven", "foot", "soft", "helper"):
            editor.layer_type.setCurrentIndex(editor.layer_type.findData(kind))
            QtTest.QTest.mouseClick(editor.add_button, QtCore.Qt.LeftButton)
            yield
            check(not editor.status.text().startswith("操作できません"), "Add sample " + kind)
        check(len(rig.twist_joints()) == 3 and len(rig.bend_joints()) == 3, "Sample joints created")
        graph = list(DrivenLayer(rig).graphs().values())[0]
        bone = graph.plug("drivenNode").source().node
        cmds.setAttr(rig.controls()["fk1"] + ".rz", 45)
        yield
        check(abs(bone.plug("ty").get() - 0.5) < 0.001, "SDK responds to FK rotation")
        item = row("driven")
        item.setCheckState(0, QtCore.Qt.Unchecked)
        yield
        check(
            not rig.layer_enabled("driven") and bone.plug("ty").source() is None,
            "Layer checkbox disconnects SDK",
        )
        cmds.undo()
        yield
        check(
            rig.layer_enabled("driven") and row("driven").checkState(0) == QtCore.Qt.Checked,
            "Undo refreshes checkbox",
        )
        rig.set_lod(0)
        yield
        check(
            editor.lod.currentIndex() == 0 and "停止" in row("driven").text(2),
            "External LOD refreshes editor",
        )
        rig.set_lod(1)
        yield
        row("twist").setExpanded(False)
        editor.refresh()
        check(not row("twist").isExpanded(), "Refresh preserves collapsed layer")
        editor.tree.setCurrentItem(row("driven:sdk1"))
        editor.open_curve()
        yield
        check(
            bool(cmds.ls(selection=True, type="animCurveUL")), "SDK curve selected in Graph Editor"
        )
        editor.open_graph()
        yield
        check(bool(cmds.getPanel(scriptType="nodeEditorPanel")), "Node Editor opens")
        editor.raise_()
        editor.grab().save(str(output / "layer-editor.png"))
        path = str(output / "sample.ma")
        cmds.file(rename=path)
        cmds.file(save=True, type="mayaAscii")
        cmds.file(path, open=True, force=True, executeScriptNodes=False)
        yield
        check(
            editor.tree.topLevelItemCount() == 1 and row("driven:sdk1") is not None,
            "Saved scene repopulates rows",
        )
        editor.module_name.setText("second")
        QtTest.QTest.mouseClick(editor.create_button, QtCore.Qt.LeftButton)
        (output / "second-immediate.json").write_text(
            json.dumps(
                {
                    "roots": cmds.ls("*.hrigDefinition"),
                    "count": editor.tree.topLevelItemCount(),
                    "status": editor.status.text(),
                    "scene": cmds.file(query=True, sceneName=True),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        yield
        (output / "second-idle.json").write_text(
            json.dumps(
                {
                    "roots": cmds.ls("*.hrigDefinition"),
                    "count": editor.tree.topLevelItemCount(),
                    "status": editor.status.text(),
                    "scene": cmds.file(query=True, sceneName=True),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        check(
            editor.tree.topLevelItemCount() == 2 and editor.current()[0].root.name() == "second",
            "Second module selected",
        )
        jobs = editor._jobs
        attrs = editor._attributes
        editor.close()
        yield
        check(not jobs.exists() and not attrs.exists(), "Closing removes owned jobs")
        editor = show_layer_editor()
        yield
        check(editor.tree.topLevelItemCount() == 2, "Reopen restores scene modules")
        cmds.file(new=True, force=True)
        yield
        check(
            editor.tree.topLevelItemCount() == 0 and not editor.add_button.isEnabled(),
            "New scene clears panel",
        )
        editor.close()

    iterator = steps()

    def advance():
        """Mayaのidle後に次の操作を実行する。"""
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
            diagnostic.stop()
            finished(result)

    QtCore.QTimer.singleShot(0, advance)
