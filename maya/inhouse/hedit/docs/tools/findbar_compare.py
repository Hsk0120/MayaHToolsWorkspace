"""hedit の検索バーを VS Code と同じ状態で撮り、上下に並べた比較画像を作る(開発用)。

使い方(リポジトリ直下から)::

    python maya/inhouse/hedit/docs/tools/findbar_compare.py 2027
    python maya/inhouse/hedit/docs/tools/findbar_compare.py 2027 --no-vscode

1. ``vscode_capture/capture.py`` で、隔離した VS Code の検索ウィジェットを5つの状態で撮る
   (``--no-vscode`` なら省略し、hedit だけを撮る)。
2. 専用設定の Maya GUI で ``findbar_suite.py`` を実行し、hedit の検索バーを同じ状態で撮って比較画像を作る。

出力は ``.maya-output/hedit-findbar/<日時>/``(VS Code の画像は ``<日時>-vscode/``。Git 対象外)。既存の Maya・VS Code の設定には触れない。
親リポジトリの ``tools/run_hlib_gui_versions.py`` を利用する。
"""
import argparse
import datetime
import json
from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parent
PROJECT = TOOLS.parents[1]
ROOT = PROJECT.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(TOOLS / "vscode_capture"))
from run_hlib_gui_versions import run_version  # noqa: E402


def main():
    """コマンドラインの入口。

    Returns:
        int: 成功なら0。
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("version", nargs="?", default="2027", choices=["2022", "2024", "2025", "2026", "2027"])
    parser.add_argument("--no-vscode", action="store_true", help="VS Code を撮らず、hedit だけを撮る")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    directory = ROOT / ".maya-output/hedit-findbar" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    environment = {}
    if not args.no_vscode:
        import capture  # vscode_capture/capture.py
        capture.user32.SetProcessDPIAware()
        script = json.loads((TOOLS / "vscode_capture/find_replace.json").read_text(encoding="utf-8"))
        vscode = directory.with_name(directory.name + "-vscode")  # 本体のフォルダはrun_versionが作る。
        capture.run(script, vscode)
        environment["HEDIT_VSCODE_CAPTURE"] = str(vscode)
        environment["HEDIT_VSCODE_CROP"] = ",".join(str(value) for value in script["compareCrop"])
    # 開発中の hedit を読み込むよう、この作業フォルダを指す .mod を一時的に作る。
    modules = directory.with_name(directory.name + "-modules")
    modules.mkdir(parents=True)
    definition = (ROOT / "maya/modules/hedit.mod").read_text(encoding="ascii")
    (modules / "hedit.mod").write_text(definition.replace("../inhouse/hedit", PROJECT.as_posix()), encoding="utf-8")
    session = directory.with_name(directory.name + "-session")
    session.mkdir(parents=True)
    environment.update({"MAYA_MODULE_PATH": str(modules), "HEDIT_TEST_COMMANDS": "1",
                        "HEDIT_SESSION_FILE": str(session / "tabs.json")})
    outcome = run_version(args.version, directory, Path("C:/Program Files/Autodesk"), args.timeout,
                          shutdown_timeout=60, suite_path=TOOLS / "findbar_suite.py", environment=environment)
    suite = directory / "result.json"
    data = json.loads(suite.read_text(encoding="utf-8")) if suite.exists() else {}
    print(json.dumps({"status": outcome.get("status"), "suite": data, "dir": str(directory)},
                     ensure_ascii=False, indent=1))
    return 0 if data.get("status") == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
