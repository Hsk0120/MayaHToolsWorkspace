"""ワークスペース内のmlibと他パッケージとの連携を検証する入口。"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
MLIB_TESTS = HERE.parents[1] / "maya/inhouse/mlib/__tests__"
sys.path.insert(0, str(MLIB_TESTS))
from run_all_tests import run_all as run_cases

LOG_DIR = HERE / "_output/logs"
EXCLUDED_FILES = set()


def run_all(names=None):
    """外部パッケージを使うcasesだけを実行する。手動投稿スクリプトは含めない。"""
    run_cases.__globals__["LOG_DIR"] = LOG_DIR
    return run_cases(directories=[HERE / "cases"], names=names)


if __name__ == "__main__":
    raise RuntimeError("mlib/__tests__/runMaya.py --suite-fileで実行してください。")
