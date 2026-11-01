"""専用Maya GUIでPythonを内蔵しないmllの寿命とシーン操作を検証する。"""

import json
import os
from pathlib import Path
import time


def main(output_dir, finished=None):
    """専用prefs/テストシーンだけを使う。製品コードのPython実行は要求しない。"""
    gui_request = Path(output_dir).parent / "gui.request"
    if gui_request.is_file():
        import runpy
        request = json.loads(gui_request.read_text(encoding="utf-8"))
        gui_request.unlink()
        return runpy.run_path(str(Path(__file__).with_name("native_maya_gui.py")))["main"](Path(output_dir), request)
    restart_request = Path(output_dir).parent / "restart.request"
    if restart_request.is_file():
        import runpy
        request = json.loads(restart_request.read_text(encoding="utf-8"))
        restart_request.unlink()
        return runpy.run_path(str(Path(__file__).with_name("native_maya_restart.py")))["main"](Path(output_dir), request)
    from maya import cmds
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets
    out = Path(output_dir)
    fixture = out / "fixture"
    fixture.mkdir(exist_ok=True)
    (fixture / "empty").mkdir(exist_ok=True)
    (fixture / "item.txt").write_text("native test", encoding="utf-8")
    os.environ["QPE_SETTINGS_FILE"] = str(out / "settings.json")
    root = Path(__file__).resolve().parents[1]
    year = cmds.about(version=True)[:4]
    product = os.environ.get("QPE_TEST_PRODUCT") == "1"
    plugin_name = "quickPathExplorer" if product else "quickPathExplorerNativeMigration"
    def command(*args):
        """ロード後に登録されるMayaコマンドを呼ぶ。"""
        return getattr(cmds, "quickPathExplorer" if product else "quickPathExplorerNative")(*args)
    control = "QuickPathExplorerWorkspaceControl" if product else "QPENativeMigrationWorkspaceControl"
    plugin_root = Path(os.environ.get("QPE_TEST_PLUGIN_ROOT", str(root / ("release/plug-ins/windows" if product else ".maya-output/native-plugin"))))
    plugin = plugin_root / year / (plugin_name + ".mll")
    if not cmds.pluginInfo(plugin_name, query=True, loaded=True):
        cmds.loadPlugin(plugin.as_posix())
    checks = []

    def wait(predicate):
        """イベントループを維持して条件を待つ。"""
        limit = time.monotonic() + 20
        while not predicate():
            if time.monotonic() >= limit:
                raise AssertionError("Timed out")
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(25, loop.quit)
            (loop.exec if hasattr(loop, "exec") else loop.exec_)()

    def invoke(action, path="", options=None):
        """C++コマンドへ固定JSON値を渡す。"""
        return command("-invoke", action, path, json.dumps(options or {}, ensure_ascii=False))

    unload_request = out.parent / "unload.request"
    if os.environ.get("QPE_NATIVE_KEEP_LOADED") == "1" and unload_request.is_file():
        # 固定パスの再ビルド用。専用mllだけを解除しMaya/prefsは維持する。
        unload_request.unlink()
        if cmds.workspaceControl(control, exists=True):
            cmds.deleteUI(control)
        def unload_owned():
            """ワーカー終了後に専用mllを解除する。強制解除しない。"""
            try:
                cmds.unloadPlugin(plugin_name)
                return True
            except RuntimeError:
                return False
        wait(unload_owned)
        return {"status": "passed", "operation": "unload for rebuild", "maya": year}

    command("-path", fixture.as_posix())
    app = QtWidgets.QApplication.instance()
    window = next(w for w in app.allWidgets() if w.objectName() == "qpeNativeWindow")
    files = window.findChild(QtWidgets.QTreeView, "files")
    wait(lambda: files.model().rowCount() == 1)
    assert files.model().index(0, 0).data() == "item.txt"
    window.grab().save(str(out / "native-maya.png"))
    checks.append("C++ UI with native model, icons and folder enumeration")
    other = QtWidgets.QLineEdit("external Qt input")
    other.setObjectName("qpeTestExternalInput")
    other.show()
    baseline = app.palette().cacheKey()
    cmds.file(new=True, force=True)
    cmds.polyCube(name="qpeNativeCube")
    options = {"directory": fixture.as_posix(), "fileName": "scene.mb", "fileType": "mayaBinary"}
    invoke("saveAs", options=options)
    assert (fixture / "scene.mb").is_file()
    assert Path(cmds.file(query=True, sceneName=True)).resolve() == (fixture / "scene.mb").resolve()
    cmds.file(new=True, force=True)
    invoke("open", (fixture / "scene.mb").as_posix())
    assert cmds.objExists("qpeNativeCube")
    wait(lambda: command("-status").replace("\\", "/") == fixture.as_posix())
    checks.append("Save As .mb, Open in current Maya, follow scene folder")
    # 専用シーンだけを変更し、実ダイアログのCancelがシーンと保存先を保護することを確認する。
    protected_scene = cmds.file(query=True, sceneName=True)
    protected_bytes = (fixture / "scene.mb").read_bytes()
    cmds.polyCube(name="qpeUnsavedProtected")
    cancelled_dialogs = []

    def cancel_scene_dialog():
        """Qtの実モーダルをCancelする。OS入力検証とは区別する。"""
        dialog = app.activeModalWidget()
        if isinstance(dialog, QtWidgets.QMessageBox):
            cancelled_dialogs.append(dialog.windowTitle())
            dialog.button(QtWidgets.QMessageBox.Cancel).click()

    for action, target, settings in (
        ("new", "", {}),
        ("open", (fixture / "scene.mb").as_posix(), {}),
        ("saveAs", "", options),
    ):
        timer = QtCore.QTimer()
        timer.timeout.connect(cancel_scene_dialog)
        timer.start(25)
        try:
            invoke(action, target, settings)
        finally:
            timer.stop()
        assert cmds.objExists("qpeUnsavedProtected")
        assert cmds.file(query=True, modified=True)
        assert cmds.file(query=True, sceneName=True) == protected_scene
        assert (fixture / "scene.mb").read_bytes() == protected_bytes
    assert cancelled_dialogs == ["Unsaved scene", "Unsaved scene", "Overwrite file"]
    cmds.file(new=True, force=True)
    invoke("open", (fixture / "scene.mb").as_posix())
    checks.append("New/Open/Save As Cancel preserves unsaved scene, scene name and existing disk bytes")
    before_frame = cmds.currentTime(query=True)
    before_selection = cmds.ls(selection=True)
    invoke("sidecar")
    sidecar = fixture / "scene.mb.qpe.json"
    assert sidecar.is_file()
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    assert metadata["scene"].replace("\\", "/") == (fixture / "scene.mb").as_posix()
    assert cmds.currentTime(query=True) == before_frame and cmds.ls(selection=True) == before_selection
    assert not cmds.file(query=True, modified=True)
    checks.append("Scene sidecar explicit capture; scene/frame/selection unchanged")
    cmds.file(new=True, force=True)
    # 専用prefsではUndoが無効な場合がある。テストの前提を明示して実UI経路を検証する。
    cmds.undoInfo(state=True)
    window.findChild(QtWidgets.QComboBox, "import_mode").setCurrentIndex(1)
    window.findChild(QtWidgets.QLineEdit, "import_name").setText("shot:asset")
    window.findChild(QtWidgets.QCheckBox, "import_executeScriptNodes").setChecked(False)
    command("-refresh")
    wait(lambda: any(files.model().index(i, 0).data() == "scene.mb" for i in range(files.model().rowCount())))
    scene_index = next(files.model().index(i, 0) for i in range(files.model().rowCount()) if files.model().index(i, 0).data() == "scene.mb")
    files.setCurrentIndex(scene_index)
    window.findChild(QtWidgets.QPushButton, "import").click()
    assert cmds.objExists("shot:asset:qpeNativeCube")
    undo_probe = {"state": cmds.undoInfo(query=True, state=True), "empty": cmds.undoInfo(query=True, undoQueueEmpty=True)}
    cmds.polyCube(name="undoControlCube")
    undo_probe["cube_empty"] = cmds.undoInfo(query=True, undoQueueEmpty=True)
    cmds.undo()
    assert not cmds.objExists("undoControlCube")
    cmds.redo()
    assert cmds.objExists("undoControlCube")
    cmds.file(new=True, force=True)
    cmds.file((fixture / "scene.mb").as_posix(), i=True, namespace="control", preserveReferences=True, executeScriptNodes=False)
    undo_probe["standard_import_empty"] = cmds.undoInfo(query=True, undoQueueEmpty=True)
    (out / "undo-probe.json").write_text(json.dumps(undo_probe, indent=2), encoding="utf-8")
    assert undo_probe["empty"] == undo_probe["standard_import_empty"]
    assert not undo_probe["cube_empty"]
    checks.append("Import nested namespace; Undo queue matches standard import; subsequent cube edit Undo/Redo works")
    cmds.file(new=True, force=True)
    invoke("reference", (fixture / "scene.mb").as_posix(), {"reference": {"mode": "custom", "name": "refAsset", "executeScriptNodes": False}})
    assert cmds.objExists("refAsset:qpeNativeCube")
    checks.append("Reference explicit namespace")
    fbx_request = out.parent / "fbx.request"
    if fbx_request.is_file():
        fbx_request.unlink()
        from maya import mel
        # 分離したprefs環境ではAutodesk FBXのmoduleが未登録でも、本体同梱の固定パスを使う。
        bundled_fbx = Path(os.environ["MAYA_LOCATION"]) / "plug-ins/fbx/plug-ins/fbxmaya.mll"
        if not cmds.pluginInfo("fbxmaya", query=True, loaded=True):
            cmds.loadPlugin(bundled_fbx.as_posix() if bundled_fbx.is_file() else "fbxmaya", quiet=True)
        cmds.file(new=True, force=True)
        joint = cmds.joint(name="qpeAnimJoint")
        cmds.setKeyframe(joint, attribute="translateX", time=1, value=0)
        cmds.setKeyframe(joint, attribute="translateX", time=10, value=8)
        cmds.select(clear=True)
        extra = cmds.joint(name="qpeExtraJoint")
        cmds.select([joint, extra])
        fbx = fixture / "animation 日本語.fbx"
        mel.eval("FBXPushSettings;")
        try:
            mel.eval("FBXExport -f " + json.dumps(fbx.as_posix(), ensure_ascii=False) + " -s;")
        finally:
            mel.eval("FBXPopSettings;")
        assert fbx.is_file()
        cmds.file(new=True, force=True)
        cmds.joint(name="qpeAnimJoint")
        cmds.playbackOptions(minTime=3, maxTime=7, animationStartTime=2, animationEndTime=8)
        mode_before = mel.eval("FBXImportMode -q;")
        invoke("open", fbx.as_posix(), {"fbx": {"mode": "exmerge", "timeline": False}})
        cmds.currentTime(10)
        assert abs(cmds.getAttr("qpeAnimJoint.translateX") - 8.0) < 0.001
        assert not cmds.objExists("qpeExtraJoint")
        assert cmds.playbackOptions(query=True, minTime=True) == 3
        assert cmds.playbackOptions(query=True, maxTime=True) == 7
        assert mel.eval("FBXImportMode -q;") == mode_before
        cmds.file(modified=False)
        invoke("open", fbx.as_posix(), {"fbx": {"mode": "open", "timeline": False}})
        assert cmds.objExists("qpeAnimJoint") and cmds.objExists("qpeExtraJoint")
        assert mel.eval("FBXImportMode -q;") == mode_before
        checks.append("FBX update animation only / Open; Japanese path, existing-only nodes, playback and FBX settings preserved")
    cmds.workspaceControl(control, edit=True, floating=False, dockToMainWindow=("right", False))
    cmds.workspaceControl(control, edit=True, floating=True)
    for _ in range(3):
        cmds.deleteUI(control)
        command("-path", fixture.as_posix())
        wait(lambda: any(w.objectName() == "qpeNativeWindow" for w in app.allWidgets()))
    assert other.text() == "external Qt input" and app.palette().cacheKey() == baseline
    checks.append("dock/float/delete/recreate, external Qt text and application palette preserved")
    current_window = next(w for w in app.allWidgets() if w.objectName() == "qpeNativeWindow")
    # 再生成は保存済みのドック状態を戻すため、浮動サイズ検証の前提を明示する。
    cmds.workspaceControl(control, edit=True, floating=True)
    wait(lambda: cmds.workspaceControl(control, query=True, floating=True))
    settled = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(300, settled.quit)
    (settled.exec if hasattr(settled, "exec") else settled.exec_)()
    cmds.workspaceControl(control, edit=True, resizeWidth=1200, resizeHeight=850)
    # Mayaは再ドック時にフロート親を作り直すため、親のPythonラッパーを保持しない。
    wait(lambda: cmds.workspaceControl(control, query=True, width=True) <= 1250 and cmds.workspaceControl(control, query=True, height=True) <= 900)
    current_window.grab().save(str(out / "native-maya-final.png"))
    command("-saveLayout")
    dock = json.loads((out / "settings.json").read_text(encoding="utf-8"))["mayaDock" + year]
    assert dock["open"] and dock["floating"] and len(dock["geometry"]) == 4
    cmds.workspaceControl(control, edit=True, close=True)
    dock = json.loads((out / "settings.json").read_text(encoding="utf-8"))["mayaDock" + year]
    assert not dock["open"]
    command("-restore")
    wait(lambda: not cmds.workspaceControl(control, query=True, visible=True))
    command("-path", fixture.as_posix())
    wait(lambda: cmds.workspaceControl(control, query=True, visible=True))
    checks.append("floating geometry/open state persisted; closed uiScript stays hidden; explicit show restores")
    if os.environ.get("QPE_NATIVE_KEEP_LOADED") == "1":
        result = {"status": "passed", "maya": year, "evidence": "Qt programmatic and Maya API; not OS mouse input", "checks": checks, "unload": "not run; persistent validation session"}
        (out / "native-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        other.close()
        if finished:
            finished(result)
        return result
    cmds.deleteUI(control)
    def unload():
        """生存ワーカーの解除拒否は待って再確認する。強制解除しない。"""
        try:
            cmds.unloadPlugin(plugin_name)
            return True
        except RuntimeError:
            return False
    wait(unload)
    cmds.loadPlugin(plugin.as_posix())
    command("-path", fixture.as_posix())
    wait(lambda: any(w.objectName() == "qpeNativeWindow" for w in app.allWidgets()))
    checks.append("unload/reload without external Python modules")
    other.close()
    result = {"status": "passed", "maya": year, "evidence": "Qt programmatic and Maya API; not OS mouse input", "checks": checks}
    (out / "native-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if finished:
        finished(result)
    return result
