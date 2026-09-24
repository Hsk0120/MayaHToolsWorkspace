"""Maya 2022～2027のmayapyを個別起動してhlibを検証する（Python 3.7以上）。"""
import argparse
import datetime
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = tuple(str(year) for year in range(2022, 2028))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def worker(version, result_path):
    """指定Maya内で既存ランナーを使う。GUI・外部投稿テストは実行しない。"""
    result = {"requested_version": version, "status": "error"}
    standalone = None
    try:
        import maya.standalone
        maya.standalone.initialize(name="python")
        standalone = maya.standalone
        import maya.cmds as cmds
        actual = str(cmds.about(version=True))
        result.update(maya_version=actual, api_version=cmds.about(apiVersion=True),
                      python_version=sys.version, executable=sys.executable)
        if actual.split(".")[0] != version:
            raise RuntimeError("Requested Maya {} but started {}".format(version, actual))
        sys.path.insert(0, str(ROOT / "maya/inhouse"))
        tests = ROOT / "maya/inhouse/hlib/__tests__"
        namespace = runpy.run_path(str(tests / "run_all_tests.py"))
        namespace["EXCLUDED_FILES"].add("test_scene_ui.py")
        # 各バージョンの詳細ログを同じ結果ディレクトリに格納する。
        namespace["run_all"].__globals__["LOG_DIR"] = result_path.parent
        suite = namespace["run_all"]()
        result.update(status="passed" if suite["ok"] else "failed",
                      total_files=suite["total"], failed_files=suite["failed"],
                      suite_log=str(suite["log_path"]), summary=suite["summary"],
                      excluded_files=sorted(namespace["EXCLUDED_FILES"] - {"run_all_tests.py"}))
    except BaseException:
        result["status"] = "error"
        result["error"] = traceback.format_exc()
        print(result["error"], flush=True)
    finally:
        if standalone is not None:
            try:
                standalone.uninitialize()
            except BaseException:
                result["status"] = "error"
                result["shutdown_error"] = traceback.format_exc()
        write_json(result_path, result)
    return 0 if result["status"] == "passed" else 1


def maya_executable(version, install_root):
    """MAYA_TEST_LOCATION_<year>でバージョンごとのインストール先を上書きできる。"""
    location = Path(os.environ.get("MAYA_TEST_LOCATION_" + version,
                                   str(install_root / ("Maya" + version))))
    return location / "bin/mayapy.exe"


def isolated_environment(executable, directory):
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(("MAYA_", "PYTHON", "QT_", "PYSIDE")):
            env.pop(key, None)
    app = directory / "maya_app"
    temp = directory / "temp"
    app.mkdir()
    temp.mkdir()
    env.update(MAYA_APP_DIR=str(app), MAYA_LOCATION=str(executable.parent.parent),
               MAYA_UI_LANGUAGE="en_US",
               MAYA_SKIP_USERSETUP_PY="1", MAYA_DISABLE_CIP="1", MAYA_DISABLE_CER="1",
               PYTHONPATH=str(ROOT / "maya/inhouse"), PYTHONIOENCODING="utf-8",
               PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", TEMP=str(temp), TMP=str(temp))
    env["PATH"] = str(executable.parent) + os.pathsep + env.get("PATH", "")
    return env


def run_version(version, executable, directory, timeout):
    directory.mkdir()
    if not executable.is_file():
        return {"requested_version": version, "status": "missing", "executable": str(executable)}
    result_path = directory / "result.json"
    started = time.monotonic()
    with (directory / "console.log").open("wb") as output:
        process = subprocess.Popen(
            [str(executable), str(Path(__file__).resolve()), "--worker", version, str(result_path)],
            cwd=str(ROOT), env=isolated_environment(executable, directory),
            stdout=output, stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # このランナーが起動したプロセスと子だけを停止する。
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if process.poll() is None:
                process.kill()
            process.wait()
            return {"requested_version": version, "status": "timeout", "timeout_seconds": timeout}
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding="utf-8"))
    else:
        result = {"requested_version": version, "status": "error", "error": "Worker produced no result.json"}
    if code and result["status"] == "passed":
        result["status"] = "error"
    result.update(exit_code=code, elapsed_seconds=round(time.monotonic() - started, 2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versions", nargs="+", choices=VERSIONS, default=list(VERSIONS))
    parser.add_argument("--install-root", type=Path, default=Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Autodesk")
    parser.add_argument("--output", type=Path, default=ROOT / ".maya-output/version-tests")
    parser.add_argument("--timeout", type=int, default=600, help="1バージョンの制限秒数")
    parser.add_argument("--list", action="store_true", help="検出だけ行う")
    parser.add_argument("--allow-missing", action="store_true", help="未インストールのみなら終了コードを0にする")
    parser.add_argument("--worker", nargs=2, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return worker(args.worker[0], Path(args.worker[1]))
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    versions = list(dict.fromkeys(args.versions))
    if args.list:
        for version in versions:
            exe = maya_executable(version, args.install_root)
            print("{}: {} ({})".format(version, exe, "installed" if exe.is_file() else "missing"))
        return 0
    directory = args.output.resolve() / datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    directory.mkdir(parents=True)
    results = []
    print("Results: " + str(directory), flush=True)
    for version in versions:
        print("Maya {}: running".format(version), flush=True)
        try:
            result = run_version(version, maya_executable(version, args.install_root), directory / version, args.timeout)
        except Exception:
            result = {"requested_version": version, "status": "error", "error": traceback.format_exc()}
        results.append(result)
        write_json(directory / version / "result.json", result)
        write_json(directory / "summary.json", results)
        print("Maya {}: {}".format(version, result["status"]), flush=True)
    lines = ["Maya\tStatus\tFailed files"]
    for result in results:
        lines.append("{}\t{}\t{}".format(result["requested_version"], result["status"], ", ".join(result.get("failed_files", []))))
    (directory / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines), flush=True)
    if any(row["status"] not in ("passed", "missing") for row in results):
        return 1
    if not args.allow_missing and any(row["status"] == "missing" for row in results):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
