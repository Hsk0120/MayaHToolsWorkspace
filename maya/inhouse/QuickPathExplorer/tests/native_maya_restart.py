"""専用prefsで実プロセス再起動を跨いでMaya配置を検査する。"""

import json
import os
from pathlib import Path
import time


def main(out, request):
    """prepareとverifyは別Maya PIDで実行する。信頼設定は変更しない。"""
    from maya import cmds
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets
    root = Path(__file__).resolve().parents[1]
    year = cmds.about(version=True)[:4]
    product = os.environ.get("QPE_TEST_PRODUCT") == "1"
    plugin_name = "quickPathExplorer" if product else "quickPathExplorerNativeMigration"
    plugin_folder = Path(os.environ.get("QPE_TEST_PLUGIN_ROOT", str(root / ("release/plug-ins/windows" if product else ".maya-output/native-plugin"))))
    def command(*args):
        """ロード後に登録されるMayaコマンドを呼ぶ。"""
        return getattr(cmds, "quickPathExplorer" if product else "quickPathExplorerNative")(*args)
    control = "QuickPathExplorerWorkspaceControl" if product else "QPENativeMigrationWorkspaceControl"
    state_file = out.parent / "restart-state.json"
    settings_file = out.parent / "restart-settings.json"
    app = QtWidgets.QApplication.instance()
    if request["phase"] == "inspect":
        from maya import mel
        return {"status": "diagnostic", "pid": os.getpid(), "loaded": cmds.pluginInfo(query=True, listPlugins=True),
                "deferred": cmds.evalDeferred(list=True), "plugin_path": os.environ.get("MAYA_PLUG_IN_PATH"),
                "app_dir": cmds.internalVar(userPrefDir=True), "autoload": cmds.pluginInfo(plugin_name, query=True, autoload=True),
                "plugin_prefs_source": mel.eval('whatIs "pluginPrefs"'),
                "skip_user_setup": os.environ.get("MAYA_SKIP_USERSETUP_PY"),
                "script_path": os.environ.get("MAYA_SCRIPT_PATH")}

    def settle(seconds=1):
        """MayaとQtの遅延処理を完了させる。"""
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(int(seconds * 1000), loop.quit)
        (loop.exec if hasattr(loop, "exec") else loop.exec_)()

    if request["phase"] == "prepare":
        os.environ["QPE_SETTINGS_FILE"] = str(settings_file)
        if not cmds.pluginInfo(plugin_name, query=True, loaded=True):
            cmds.loadPlugin((plugin_folder / year / (plugin_name + ".mll")).as_posix())
        fixture = out.parent / "restart-fixture"
        fixture.mkdir(exist_ok=True)
        (fixture / "restart.txt").write_text("restart test", encoding="utf-8")
        command("-path", fixture.as_posix())
        mode = request["mode"]
        if mode == "docked":
            cmds.workspaceControl(control, edit=True, dockToMainWindow=("right", False))
        else:
            cmds.workspaceControl(control, edit=True, floating=True)
        settle()
        window = next(w for w in app.allWidgets() if w.objectName() == "qpeNativeWindow")
        if mode == "floating":
            window.window().setGeometry(70, 80, 930, 690)
        settle()
        if mode == "closed":
            cmds.workspaceControl(control, edit=True, close=True)
        command("-saveLayout")
        cmds.pluginInfo(plugin_name, edit=True, autoload=True)
        cmds.pluginInfo(savePluginPrefs=True)
        cmds.workspaceLayoutManager(saveAs="QPEValidationWorkspace")
        cmds.savePrefs(uiLayout=True)
        state = {"pid": os.getpid(), "mode": mode, "path": fixture.as_posix(), "settings": str(settings_file),
                 "dock": json.loads(settings_file.read_text(encoding="utf-8"))["mayaDock" + year]}
        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return {"status": "passed", "phase": "prepared", "maya": year, "state": state}
    if request["phase"] != "verify":
        raise ValueError("Unknown restart phase")
    expected = json.loads(state_file.read_text(encoding="utf-8"))
    assert expected["pid"] != os.getpid(), "Not a real process restart"
    assert Path(os.environ["QPE_SETTINGS_FILE"]) == settings_file
    loaded_at_start = cmds.pluginInfo(plugin_name, query=True, loaded=True)
    if not loaded_at_start and request.get("explicit_load"):
        cmds.loadPlugin((root / plugin_folder / year / (plugin_name + ".mll")).as_posix())
    deadline = time.monotonic() + 30
    while not cmds.pluginInfo(plugin_name, query=True, loaded=True) and time.monotonic() < deadline:
        settle(0.1)
    assert cmds.pluginInfo(plugin_name, query=True, loaded=True), "Plugin did not autoload"
    settle(2)
    mode = expected["mode"]
    exists = cmds.workspaceControl(control, exists=True)
    if mode == "closed":
        assert not exists or not cmds.workspaceControl(control, query=True, visible=True), "Closed QPE reopened"
    else:
        assert exists and cmds.workspaceControl(control, query=True, visible=True), "Open QPE did not restore"
        assert cmds.workspaceControl(control, query=True, floating=True) == (mode == "floating")
        assert command("-status").replace("\\", "/") == expected["path"]
        window = next(w for w in app.allWidgets() if w.objectName() == "qpeNativeWindow")
        if mode == "floating":
            actual = window.window().normalGeometry()
            values = [actual.x(), actual.y(), actual.width(), actual.height()]
            assert all(abs(a - b) <= 12 for a, b in zip(values, expected["dock"]["geometry"])), (values, expected)
        window.grab().save(str(out / "restart.png"))
    return {"status": "passed", "phase": "verified", "maya": year, "mode": mode, "already_loaded": loaded_at_start,
            "old_pid": expected["pid"], "new_pid": os.getpid(), "evidence": "Maya real process restart; Qt/Maya API assertions"}
