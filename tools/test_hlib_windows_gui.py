"""隔離Maya GUIランナー用のウィンドウAPI検証。手動の作業GUIでは実行しない。"""
import io
import json
import os
from pathlib import Path
import runpy
import unittest


def main(output_dir=None, finished=None):
    """専用プロファイルでウィンドウテストを実行しランナーへ結果を返す。

    Args:
        output_dir (str | Path): 結果保存先。
        finished (callable): 終了処理。ランナーが所有するGUIだけを終了する。
    """
    if os.environ.get("HLIB_WINDOW_LAYOUT_TEST") != "1" or not output_dir or finished is None:
        raise RuntimeError("Use the isolated GUI version runner")
    root = Path(__file__).resolve().parents[1]
    scope = runpy.run_path(str(root / "maya/inhouse/hlib/__tests__/test_window_layout.py"))
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(scope[name]) for name in ("WindowApiTest", "WindowGuiTest"))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    data = {"status": "passed" if result.wasSuccessful() else "failed", "tests": result.testsRun,
            "log": stream.getvalue(), "scope": "automated GUI assertions; visual review separate"}
    Path(output_dir, "result.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    finished(data)
