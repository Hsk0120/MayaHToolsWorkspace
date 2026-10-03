"""ランナーが起動した使い捨てMaya GUIの中で、hlibの単体テスト一式を実行する。

``run_hlib_gui_versions.py --suite unit`` から ``main(output_dir, finished)`` として呼ばれる。
mayapyでは実行できない(skipされる)GUI専用のケースと ``test_scene_ui.py`` も対象にする。
テストはシーンの新規作成やウィンドウ配置の変更を行うため、普段使うGUIへ送信しない。
"""
import os
from pathlib import Path
import runpy
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]

#: ランナーが使い捨てGUIを起動したときだけ設定する環境変数。
DISPOSABLE_FLAG = "HLIB_DISPOSABLE_GUI"


def main(output_dir, finished):
    """単体テスト一式を実行し、結果を ``result.json`` へ書いて ``finished`` を呼ぶ。

    Args:
        output_dir (str | Path): 結果・ログの保存先。
        finished (Callable[[dict], object]): 結果を受け取り、GUIを終了させるコールバック。
    """
    import maya.cmds as cmds

    from run_hlib_tests import write_json

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result = {"status": "error", "suite": "unit"}
    try:
        if cmds.about(batch=True):
            raise RuntimeError("Run this suite in an interactive Maya GUI")
        if os.environ.get(DISPOSABLE_FLAG) != "1":
            raise RuntimeError("This suite resets the scene; run it only through run_hlib_gui_versions.py")
        sys.path.insert(0, str(ROOT / "maya/inhouse"))
        namespace = runpy.run_path(str(ROOT / "maya/inhouse/hlib/__tests__/run_all_tests.py"))
        namespace["run_all"].__globals__["LOG_DIR"] = output
        suite = namespace["run_all"]()
        result.update(status="passed" if suite["ok"] else "failed",
                      maya_version=cmds.about(version=True), python_version=sys.version,
                      total_files=suite["total"], failed_files=suite["failed"],
                      tests_run=suite["tests_run"], skipped=suite["skipped"],
                      suite_log=str(suite["log_path"]), summary=suite["summary"],
                      excluded_files=sorted(namespace["EXCLUDED_FILES"] - {"run_all_tests.py"}))
    except BaseException:
        result.update(status="error", error=traceback.format_exc())
    write_json(output / "result.json", result)
    finished(result)
