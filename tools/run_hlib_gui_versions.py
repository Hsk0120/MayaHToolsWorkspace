"""専用設定のMaya GUIをバージョンごとに起動し、GUIスイートを実行する。"""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

from run_hlib_tests import ROOT, VERSIONS, isolated_environment, maya_executable, write_json
from _maya_test_process import monitor_process, stop_owned_process


def worker(version, directory):
    """このランナーが起動した空シーンのGUI内だけで実行する。"""
    import runpy
    from maya import cmds, mel
    from maya import OpenMayaUI
    try:
        from PySide6 import QtCore, QtWidgets
        from shiboken6 import wrapInstance
    except ImportError:
        from PySide2 import QtCore, QtWidgets
        from shiboken2 import wrapInstance
    directory = Path(directory)

    def finish(result):
        write_json(directory / "shutdown.json", {"requested": True, "suite_status": result["status"]})
        # このプロセスはランナーが作成した使い捨てシーン。保存確認を発生させない。
        cmds.file(modified=False)
        # Pythonコールバックを抜けてからネイティブMELで終了する。
        # 終了処理中にPythonフレームを保持せず、専用のUI設定も保存しない。
        mel.eval('evalDeferred "quit -abort -exitCode {}";'.format(0 if result["status"] == "passed" else 1))

    def execute():
        try:
            actual = str(cmds.about(version=True)).split(".")[0]
            if actual != version or cmds.about(batch=True):
                raise RuntimeError("Requested GUI {} but started {}".format(version, actual))
            write_json(directory / "started.json", {"maya_version": actual, "pid": os.getpid()})
            suite = runpy.run_path(str(ROOT / "tools/run_hlib_gui_tests.py"))
            suite["main"](output_dir=directory, finished=finish)
        except BaseException:
            result = {"status": "error", "error": traceback.format_exc()}
            write_json(directory / "result.json", result)
            finish(result)

    def wait_for_main_window():
        pointer = OpenMayaUI.MQtUtil.mainWindow()
        window = wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None
        if window is not None and window.isVisible() and not window.isMinimized():
            # 起動途中にもidle処理は実行されるため、表示完了後のイベントループで開始する。
            QtCore.QTimer.singleShot(1000, execute)
        else:
            QtCore.QTimer.singleShot(500, wait_for_main_window)
    QtCore.QTimer.singleShot(500, wait_for_main_window)


def run_version(version, directory, install_root, timeout, shutdown_timeout=15):
    directory.mkdir(parents=True)
    executable = maya_executable(version, install_root).with_name("maya.exe")
    if not executable.is_file():
        return {"requested_version": version, "status": "missing", "executable": str(executable)}
    env = isolated_environment(executable, directory)
    prefs = directory / "maya_app" / version / "prefs"
    prefs.mkdir(parents=True)
    (prefs / "userPrefs.mel").write_text(
        'optionVar -iv "showHomeScreenOnStartup" 0;\n'
        'optionVar -iv "SafeModeExecUserSetupScript" 0;\n', encoding="utf-8")
    # MELのpython()引数をJSON文字列規則で引用。シェルには渡さない。
    script = "import sys; sys.path.insert(0, {!r}); import run_hlib_gui_versions as runner; runner.worker({!r}, {!r})".format(str(ROOT / "tools"), version, str(directory))
    command = "python({})".format(json.dumps(script))
    args = [str(executable), "-noAutoloadPlugins", "-log", str(directory / "maya.log"), "-command", command]
    if version == "2022":
        args += ["-pythonver", "3"]
    start = time.monotonic()
    with (directory / "launch.log").open("wb") as log:
        process = subprocess.Popen(args, cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
        write_json(directory / "launch.json", {"pid": process.pid, "version": version, "executable": str(executable)})
        try:
            monitoring = monitor_process(process, directory, timeout, shutdown_timeout)
        except BaseException:
            stop_owned_process(process)
            raise
        write_json(directory / "monitor.json", monitoring)
        if monitoring["timed_out"]:
            return dict(monitoring, requested_version=version, status="timeout", evidence=str(directory),
                        gui_worker_started=(directory / "started.json").exists(),
                        launch_log=str(directory / "launch.log"))
        code = process.returncode
    path = directory / "result.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"status": "error", "error": "No GUI result.json produced; inspect launch.log and temp/MayaCLM*.log"}
    result.update(requested_version=version, exit_code=code, elapsed_seconds=round(time.monotonic() - start, 2),
                  evidence=str(directory), gui_worker_started=(directory / "started.json").exists(),
                  launch_log=str(directory / "launch.log"))
    if code and result["status"] == "passed":
        result["status"] = "error"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versions", nargs="+", choices=VERSIONS, default=list(VERSIONS))
    parser.add_argument("--install-root", type=Path, default=Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Autodesk")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--shutdown-timeout", type=int, default=15)
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0 or args.shutdown_timeout <= 0:
        parser.error("timeouts must be positive")
    output = ROOT / ".maya-output/gui-version-tests" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output.mkdir(parents=True)
    print("GUI results: " + str(output), flush=True)
    results = []
    for version in dict.fromkeys(args.versions):
        print("Maya {} GUI: starting".format(version), flush=True)
        try:
            result = run_version(version, output / version, args.install_root, args.timeout, args.shutdown_timeout)
        except Exception:
            result = {"requested_version": version, "status": "error", "error": traceback.format_exc()}
        results.append(result)
        write_json(output / version / "run-result.json", result)
        write_json(output / "summary.json", results)
        print("Maya {} GUI: {}".format(version, result["status"]), flush=True)
    if any(r["status"] not in ("passed", "missing") for r in results):
        return 1
    return 0 if args.allow_missing or all(r["status"] == "passed" for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())
