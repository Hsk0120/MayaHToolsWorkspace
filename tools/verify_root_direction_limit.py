"""隔離mayapyで根元方向制限のテストを実行し結果を保存する。"""

import json
import os
import runpy
import sys
import unittest
from pathlib import Path


def main():
    """standaloneを初期化し対象のテストだけを実行する。"""
    import maya.standalone
    maya.standalone.initialize(name="python")
    from maya import cmds
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "maya/inhouse"))
    namespace = runpy.run_path(str(root / "maya/inhouse/hrig/__tests__/test_setup_root_direction_limit.py"))
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(namespace["RootDirectionLimitTest"])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    target = Path(os.environ.get("ROOT_LIMIT_RESULT", str(root / ".maya-output/root-limit-tests.json")))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"maya": cmds.about(version=True), "ok": result.wasSuccessful(),
                                  "run": result.testsRun, "failures": [(str(t), e) for t, e in result.failures],
                                  "errors": [(str(t), e) for t, e in result.errors]}, indent=2), encoding="utf-8")
    maya.standalone.uninitialize()
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
