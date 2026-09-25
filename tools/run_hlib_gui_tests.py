"""起動中のMaya GUIへ送信する専用スイート。通常の一括テストは呼ばない。"""
import datetime
import io
import json
from pathlib import Path
import runpy
import sys
import traceback
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]


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
    import hlib

    if cmds.about(batch=True):
        raise RuntimeError("Run this file in an interactive Maya GUI")
    if cmds.play(query=True, state=True):
        raise RuntimeError("Stop playback before running GUI tests")
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError("Enable Undo before running GUI tests")
    output = Path(output_dir) if output_dir else ROOT / ".maya-output/gui-tests" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output.mkdir(parents=True, exist_ok=True)
    tests = ROOT / "maya/inhouse/hlib/__tests__"
    scene_tests = runpy.run_path(str(tests / "test_scene_ui.py"))["SceneUiTest"]
    selection = hlib.captureSelection()
    original_time = cmds.currentTime(query=True)
    original_focus = cmds.getPanel(withFocus=True)
    original_scene = cmds.file(query=True, sceneName=True)
    prefix = "hlibGui_" + uuid.uuid4().hex[:10]
    window = connection = channel_connection = None
    evidence = []
    result = {"maya_version": cmds.about(version=True), "python": sys.version,
              "status_scope": "automated assertions and cleanup only; visual review is separate",
              "status": "error", "screenshots": evidence,
              "manual_checks": {
                  "timeline_drag_range": "pending: mouse-created highlighted interval",
                  "playback_motion": "pending: real-time frame progression (play/stop state is automated)",
                  "logger_fade": "pending: fade timing and Script Editor visual appearance",
                  "channel_sections": "pending: mouse selection in shape/history/output sections",
                  "outliner_hierarchy": "pending: visible child rows after expand/collapse",
                  "attribute_presentation": "pending: lock/keyable/channelBox flags and attribute order",
                  "viewport_interaction": "pending: camera switch, suspend redraw and focus-based panel resolution",
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
                lambda: selection.restore(),
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
        for x, label, color in ((-4, "INDEX_RED", 13), (0, "RGB_CYAN", (0, .75, 1)), (4, "RGB_ORANGE", (1, .4, 0))):
            name = cmds.circle(name=prefix + ":" + label, normal=(0, 0, 1), radius=1.3, constructionHistory=False)[0]
            cmds.setAttr(name + ".tx", x)
            curves.append(hlib.node(name))
        cmds.addAttr(curves[0].full_name(), longName="guiAmount", attributeType="double", keyable=True)
        camera, camera_shape = cmds.camera(name=prefix + ":camera", orthographic=True)
        cmds.setAttr(camera + ".tz", 20)
        cmds.setAttr(camera_shape + ".orthographicWidth", 15)
        window = cmds.window(title="hlib GUI tests", widthHeight=(1200, 520))
        pane = cmds.paneLayout(configuration="vertical3")
        connection = cmds.selectionConnection()
        for curve in curves:
            cmds.selectionConnection(connection, edit=True, select=curve.full_name())
        editor = cmds.outlinerEditor(parent=pane, mainListConnection=connection,
                                     showDagOnly=True, showShapes=False)
        panel = cmds.modelPanel(parent=pane, camera=camera, menuBarVisible=False)
        channel_connection = cmds.selectionConnection()
        cmds.selectionConnection(channel_connection, edit=True, select=curves[0].full_name())
        channel = cmds.channelBox(parent=pane, mainListConnection=channel_connection)
        cmds.modelEditor(panel, edit=True, grid=False, cameras=False, displayAppearance="wireframe")
        cmds.select([c.full_name() for c in curves], replace=True)
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

        class IsolatedSceneTests(scene_tests):
            def setUp(self):
                self.view = hlib.viewport(panel)
                self.outliner = hlib.outliner(editor)
                self.panel = panel

        class VisualTests(unittest.TestCase):
            def test_editor_snapshot_read_only(self):
                saved = hlib.json.loads(hlib.json.dumps(hlib.json.capture(
                    [hlib.viewport(panel), hlib.outliner(editor)], kind="editor")))
                before = hlib.viewport(panel).settings()
                self.assertTrue(saved.plan().errors)
                with self.assertRaises(NotImplementedError):
                    saved.apply()
                self.assertEqual(hlib.viewport(panel).settings(), before)

            def test_colors_disable_undo_redo(self):
                for node, override, rgb in zip(curves, (13, (0, .75, 1), (1, .4, 0)),
                                               ((1, .15, .15), (0, .75, 1), (1, .4, 0))):
                    node.set_outliner_color(rgb)
                    node.shape().set_override_color(override)
                outliner_control = cmds.outlinerEditor(editor, query=True, control=True)
                for label in ("colors", "disabled", "undo", "redo"):
                    if label == "disabled":
                        from hlib.decorators import undo_chunk
                        with undo_chunk("hlibGuiDisableColors"):
                            for node in curves:
                                node.set_outliner_color(None)
                                node.shape().set_override_color(None)
                    elif label == "undo":
                        cmds.undo()
                    elif label == "redo":
                        cmds.redo()
                    self.assertEqual(curves[0].shape().override_color(), 13 if label in ("colors", "undo") else None)
                    capture(label + "_viewport")
                    capture(label + "_outliner", outliner_control)

            def test_visibility_and_component_selection(self):
                view = hlib.viewport(panel)
                with view.temporary_settings(nurbsCurves=False):
                    self.assertFalse(view.settings("nurbsCurves")["nurbsCurves"])
                    capture("curves_hidden")
                capture("curves_restored")
                cmds.select(curves[0].full_name() + ".cv[0:2]", replace=True)
                saved = hlib.captureSelection()
                before = cmds.ls(selection=True, flatten=True, long=True)
                cmds.select(clear=True)
                saved.restore()
                self.assertEqual(cmds.ls(selection=True, flatten=True, long=True), before)
                capture("component_selection")
                cmds.select(clear=True)

            def test_channelbox_real_selection_and_display(self):
                node = curves[0]
                cmds.select(node.full_name(), replace=True)
                cmds.refresh(force=True)
                box = hlib.channelBox(channel)
                cmds.channelBox(channel, edit=True, select=node.full_name() + ".guiAmount")
                capture("channel_selected", channel)
                self.assertEqual(len(box.selected_plugs()), 1,
                                 str(cmds.channelBox(channel, query=True, mainObjectList=True)))
                self.assertEqual(box.selected_plugs()[0].get(), 0)
                box.clear_selection()
                self.assertEqual(box.selected_plugs(), [])
                capture("channel_cleared", channel)
                cmds.select(clear=True)

            def test_outliner_expansion_display(self):
                outliner = hlib.outliner(editor)
                with outliner.temporary_settings(showShapes=True):
                    outliner.expand_all(True)
                    capture("outliner_shapes", cmds.outlinerEditor(editor, query=True, control=True))
                    outliner.expand_all(False)
                    capture("outliner_collapsed", cmds.outlinerEditor(editor, query=True, control=True))

            def test_logger_notification(self):
                import logging
                from hlib.utils.logger import MayaHandler
                cmds.setFocus(panel)
                MayaHandler().emit(logging.LogRecord("hlib.gui.test", logging.WARNING, "", 0,
                                                   "HLIB GUI notification <test>", (), None))
                capture("logger_notification")

        def execute():
            try:
                suite = unittest.TestSuite()
                loader = unittest.defaultTestLoader
                for cls in (IsolatedSceneTests, VisualTests):
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
