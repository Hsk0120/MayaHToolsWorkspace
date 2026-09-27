"""ドキュメント用のスクリーンショットを、専用の Maya GUI で撮り直す。

使い方(リポジトリ直下から)::

    python maya/inhouse/hedit/docs/tools/run_capture.py 2027

既存の Maya・ユーザー設定には触れず、空シーン・専用設定の Maya を起動する。
画像は ``docs/_static/images/`` へコピーする。親リポジトリの ``tools/run_hlib_gui_versions.py`` を利用する。
"""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import sys

DOCS = Path(__file__).resolve().parents[1]
PROJECT = DOCS.parent
ROOT = PROJECT.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from run_hlib_gui_versions import run_version  # noqa: E402

SAMPLE_FILES = {
    "build_rig.py": (
        '"""リグを組み立てるサンプル。"""\n'
        "import maya.cmds as cmds\n\n\n"
        'def build_arm(prefix="arm"):\n'
        '    joints = [cmds.joint(name="{}_{}".format(prefix, i), position=(i * 2, 0, 0)) for i in range(3)]\n'
        "    cmds.select(joints[0])\n"
        "    return joints\n\n\n"
        'if __name__ == "__main__":\n'
        "    print(build_arm())\n"),
    "utils.py": "def clean(names):\n    return sorted(set(names))\n",
    "notes.mel": '// メモ\nint $count = 3;\nprint ("count = " + $count + "\\n");\n',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?", default="2027", choices=["2022", "2024", "2025", "2026", "2027"])
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    directory = ROOT / ".maya-output/hedit-docs" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    modules = directory.with_name(directory.name + "-modules")
    modules.mkdir(parents=True)
    sample = directory.with_name(directory.name + "-sample") / "my_scripts"
    sample.mkdir(parents=True)
    for name, text in SAMPLE_FILES.items():
        (sample / name).write_text(text, encoding="utf-8")
    definition = (ROOT / "maya/modules/hedit.mod").read_text(encoding="ascii").replace("../inhouse/hedit", PROJECT.as_posix())
    (modules / "hedit.mod").write_text(definition, encoding="utf-8")
    tabs = []
    for name, language in (("build_rig.py", "python"), ("utils.py", "python"), ("notes.mel", "mel")):
        tabs.append({"anchor": 0, "language": language, "modified": False, "path": str(sample / name),
                     "position": 0, "text": (sample / name).read_text(encoding="utf-8")})
    session = directory.with_name(directory.name + "-session")
    session.mkdir(parents=True)
    (session / "tabs.json").write_text(json.dumps({
        "active": 0, "explorerVisible": True, "folders": [str(sample)], "tabs": tabs, "version": 1},
        ensure_ascii=False, indent=4), encoding="utf-8")
    print("Evidence: " + str(directory), flush=True)
    outcome = run_version(args.version, directory, Path("C:/Program Files/Autodesk"), args.timeout,
                          shutdown_timeout=60, suite_path=Path(__file__).with_name("capture_suite.py"),
                          environment={"MAYA_MODULE_PATH": str(modules),
                                       "HEDIT_SESSION_FILE": str(session / "tabs.json")})
    suite = directory / "result.json"
    data = json.loads(suite.read_text(encoding="utf-8")) if suite.exists() else {}
    print(json.dumps({"status": outcome.get("status"), "suite": data.get("status"), "error": data.get("error")},
                     ensure_ascii=False, indent=2), flush=True)
    if data.get("status") != "passed":
        return 1
    target = DOCS / "_static" / "images"
    target.mkdir(parents=True, exist_ok=True)
    for name in data["images"]:
        shutil.copy2(str(directory / name), str(target / name))
        print("copied", name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
