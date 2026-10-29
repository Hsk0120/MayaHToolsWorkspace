"""起動中のMaya GUIへ送信する専用スイート。通常の一括テストは呼ばない。"""
import datetime
import io
import json
from pathlib import Path
import sys
import traceback
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = Path(__file__).resolve().parents[1]


def main(output_dir=None, finished=None):
    import maya.cmds as cmds
    import maya.OpenMaya as om
    import maya.OpenMayaUI as omui
    try:
        from PySide6 import QtCore, QtWidgets
        from shiboken6 import wrapInstance
    except ImportError:
        from PySide2 import QtCore, QtWidgets
        from shiboken2 import wrapInstance
    import mlib

    if cmds.about(batch=True):
        raise RuntimeError("Run this file in an interactive Maya GUI")
    if cmds.play(query=True, state=True):
        raise RuntimeError("Stop playback before running GUI tests")
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError("Enable Undo before running GUI tests")
    output = Path(output_dir) if output_dir else TESTS_DIR / "_output/gui-visual" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output.mkdir(parents=True, exist_ok=True)
    selection = mlib.common.Selection.capture()
    original_time = cmds.currentTime(query=True)
    original_focus = cmds.getPanel(withFocus=True)
    original_scene = cmds.file(query=True, sceneName=True)
    prefix = "mlibGui_" + uuid.uuid4().hex[:10]
    window = connection = channel_connection = None
    evidence = []
    result = {"maya_version": cmds.about(version=True), "python": sys.version,
              "status_scope": "automated assertions and cleanup only; visual review is separate",
              "status": "error", "screenshots": evidence,
              "manual_checks": {
                  "logger_fade": "pending: fade timing and Script Editor visual appearance",
                  "attribute_presentation": "pending: lock/keyable/channelBox flags and attribute order",
                  "mesh_selection_modes": "pending: vertex/edge/face/UV highlight restoration",
                  "other_maya_versions": "pending: run this suite in each installed GUI"}}
    scheduled = False

    def cleanup():
        cleanup_errors = []
        for action in (
                lambda: cmds.deleteUI(window, window=True) if window and cmds.window(window, exists=True) else None,
                lambda: cmds.deleteUI(connection) if connection else None,
                lambda: cmds.deleteUI(channel_connection) if channel_connection else None,
                lambda: cmds.namespace(removeNamespace=prefix, deleteNamespaceContent=True) if cmds.namespace(exists=prefix) else None,
                lambda: selection.select(),
                lambda: cmds.currentTime(original_time),
                lambda: cmds.setFocus(original_focus) if original_focus and cmds.getPanel(typeOf=original_focus) else None):
            try:
                action()
            except Exception:
                cleanup_errors.append(traceback.format_exc())
        result["cleanup_errors"] = cleanup_errors
        result["scene_name_unchanged"] = cmds.file(query=True, sceneName=True) == original_scene
        result["test_namespace_removed"] = not cmds.namespace(exists=prefix)
        if cleanup_errors or not result["scene_name_unchanged"] or not result["test_namespace_removed"]:
            result["status"] = "failed"
        (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("GUI test results: " + str(output))
        if finished is not None:
            finished(result)

    try:
        cmds.namespace(add=prefix)
        curves = []
        for x, label in ((-4, "LEFT"), (0, "CENTER"), (4, "RIGHT")):
            name = cmds.circle(name=prefix + ":" + label, normal=(0, 0, 1), radius=1.3, constructionHistory=False)[0]
            cmds.setAttr(name + ".tx", x)
            curves.append(mlib.getNode(name))
        cmds.addAttr(curves[0].getFullName(), longName="guiAmount", attributeType="double", keyable=True)
        camera, camera_shape = cmds.camera(name=prefix + ":camera", orthographic=True)
        cmds.setAttr(camera + ".tz", 20)
        cmds.setAttr(camera_shape + ".orthographicWidth", 15)
        window = cmds.window(title="mlib GUI tests", widthHeight=(1200, 520))
        pane = cmds.paneLayout(configuration="vertical3")
        connection = cmds.selectionConnection()
        for curve in curves:
            cmds.selectionConnection(connection, edit=True, select=curve.getFullName())
        editor = cmds.outlinerEditor(parent=pane, mainListConnection=connection,
                                     showDagOnly=True, showShapes=False)
        panel = cmds.modelPanel(parent=pane, camera=camera, menuBarVisible=False)
        channel_connection = cmds.selectionConnection()
        cmds.selectionConnection(channel_connection, edit=True, select=curves[0].getFullName())
        channel = cmds.channelBox(parent=pane, mainListConnection=channel_connection)
        cmds.modelEditor(panel, edit=True, grid=False, cameras=False, displayAppearance="wireframe")
        cmds.select([c.getFullName() for c in curves], replace=True)
        cmds.isolateSelect(panel, state=True)
        cmds.isolateSelect(panel, loadSelected=True)
        cmds.select(clear=True)
        cmds.showWindow(window)

        def capture(label, control=None):
            cmds.refresh(force=True)
            QtWidgets.QApplication.processEvents()
            path = output / (label + ".png")
            if control:
                pointer = omui.MQtUtil.findControl(control)
                if not pointer:
                    raise RuntimeError("UI control not found: " + control)
                widget = wrapInstance(int(pointer), QtWidgets.QWidget)
                if not widget.isVisible():
                    raise RuntimeError("UI control is not visible: " + control)
                screenshot = widget.grab()
                if screenshot.isNull() or not screenshot.save(str(path)):
                    raise RuntimeError("Failed to save UI screenshot")
            else:
                view = omui.M3dView()
                omui.M3dView.getM3dViewFromModelPanel(panel, view)
                view.refresh(False, True)
                image = om.MImage()
                view.readColorBuffer(image, True)
                image.writeToFile(str(path), "png")
            evidence.append({"file": path.name, "review": "pending"})


        class VisualTests(unittest.TestCase):


            def test_component_selection(self):
                """Component選択を保持し、明示的なSelection参照から復元する。"""
                cmds.select(curves[0].getFullName() + ".cv[0:2]", replace=True)
                saved = mlib.common.Selection.capture()
                before = cmds.ls(selection=True, flatten=True, long=True)
                cmds.select(clear=True)
                saved.select()
                self.assertEqual(cmds.ls(selection=True, flatten=True, long=True), before)
                capture("component_selection")
                cmds.select(clear=True)

            def test_viewport_off_nested_exception_and_hidden_start(self):
                """実メインペインの入れ子・例外・非表示開始でもmanage元値へ戻す。"""
                from maya import mel
                from mlib.decorator import viewportOff
                pane_name = mel.eval("global string $gMainPane; $mlibGuiPane = $gMainPane;")
                previous = cmds.paneLayout(pane_name, query=True, manage=True)
                try:
                    for visible in (True, False):
                        cmds.paneLayout(pane_name, edit=True, manage=visible)
                        with self.assertRaisesRegex(ValueError, "viewport body"):
                            with viewportOff():
                                self.assertFalse(cmds.paneLayout(pane_name, query=True, manage=True))
                                with viewportOff():
                                    self.assertFalse(cmds.paneLayout(pane_name, query=True, manage=True))
                                self.assertFalse(cmds.paneLayout(pane_name, query=True, manage=True))
                                raise ValueError("viewport body")
                        self.assertEqual(cmds.paneLayout(pane_name, query=True, manage=True), visible)
                finally:
                    cmds.paneLayout(pane_name, edit=True, manage=previous)
                capture("viewport_restored")




            def test_logger_notification(self):
                import logging
                from mlib.logger import MayaHandler
                cmds.setFocus(panel)
                MayaHandler().emit(logging.LogRecord("mlib.gui.test", logging.WARNING, "", 0,
                                                   "MLIB GUI notification <test>", (), None))
                capture("logger_notification")

        def execute():
            try:
                suite = unittest.TestSuite()
                loader = unittest.defaultTestLoader
                for cls in (VisualTests,):
                    suite.addTests(loader.loadTestsFromTestCase(cls))
                stream = io.StringIO()
                outcome = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
                (output / "tests.log").write_text(stream.getvalue(), encoding="utf-8")
                print(stream.getvalue())
                result.update(status="passed" if outcome.wasSuccessful() else "failed",
                              tests=outcome.testsRun, skipped=[(str(t), reason) for t, reason in outcome.skipped],
                              failures=[(str(t), reason) for t, reason in outcome.failures + outcome.errors])
            except BaseException:
                result["status"] = "error"
                result["error"] = traceback.format_exc()
            finally:
                cleanup()

        result["status"] = "running"
        (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        QtCore.QTimer.singleShot(500, execute)
        scheduled = True
        print("GUI tests scheduled: " + str(output))
    except BaseException:
        result["error"] = traceback.format_exc()
        raise
    finally:
        if not scheduled:
            cleanup()


if __name__ == "__main__":
    main()
