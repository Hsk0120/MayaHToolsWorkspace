"""Mayaを起動せず、検査ツールとその単体テストを実行する。"""
from pathlib import Path
import subprocess
import sys
import unittest

TESTS_DIR = Path(__file__).resolve().parent


def main():
    """公開・レイアウト検査とchecks/test_*.pyを順に実行する。"""
    checks = TESTS_DIR / "checks"
    sys.path.insert(0, str(TESTS_DIR))
    sys.path.insert(0, str(checks))
    failures = 0
    for filename, arguments in [("check_mlib_exports.py", []), ("check_mlib_layout.py", ["--check"])]:
        result = subprocess.run([sys.executable, str(checks / filename)] + arguments)
        failures += result.returncode != 0
    suite = unittest.defaultTestLoader.discover(str(TESTS_DIR / "unit"), pattern="test_static_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 1 if failures or not result.wasSuccessful() else 0


if __name__ == "__main__":
    sys.exit(main())
