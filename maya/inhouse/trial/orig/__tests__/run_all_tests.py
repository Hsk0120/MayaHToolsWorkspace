"""unit/・integration/のtest_*.pyを実行し、件数・失敗・skipと詳細ログをまとめる。

通常はrun.bat/runMaya.pyから隔離したmayapyで実行する。
テストはシーンを初期化することがあるため、作業中のMaya GUIへ送信しない。
Maya不要の検査はrunStatic.py、外部パッケージとの連携はワークスペース側で実行する。
"""

import contextlib
import io
import runpy
import sys
import traceback
import unittest
from unittest import mock
from datetime import datetime
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
LOG_DIR = TESTS_DIR / "_output/logs"

EXCLUDED_FILES = set()


def discover_test_files(directories=None, names=None, suite="all"):
    """一括実行対象の test_*.py パスを名前順で取得する。

    Returns:
        list[Path]: 除外ファイルを除いた対象パスのリスト。
    """
    if suite not in {"unit", "integration", "all"}:
        raise ValueError("Unknown test suite: " + suite)
    groups = ("unit", "integration") if suite == "all" else (suite,)
    directories = directories if directories is not None else [TESTS_DIR / group for group in groups]
    files = sorted({path for directory in directories for path in Path(directory).rglob("test_*.py")
                    if path.name not in EXCLUDED_FILES and not path.name.startswith("test_static_")},
                   key=lambda path: (path.name, str(path)))
    if names:
        selected = [path for path in files if any(path.match(name) for name in names)]
        unmatched = [name for name in names if not any(path.match(name) for path in files)]
        if unmatched:
            raise ValueError("一致するテストがありません: " + ", ".join(unmatched))
        return selected
    return files


def _run_one(path, metrics=None):
    """1つのテストファイルを他のファイルへ影響しない形で実行する。

    各テストの実行入口を使うため
    ``runpy.run_path(path, run_name="__main__")`` を使い、各ファイル自身の
    ``if __name__ == "__main__":`` ブロック(unittest.main 呼び出し)を
    そのまま動かす。標準出力・標準エラーは呼び出し元に流さず捕捉する。

    Args:
        path (Path): 実行する test_*.py のパス。
        metrics (dict | None): 実行件数とスキップ理由の集計先。省略時は呼出内だけで保持。

    Returns:
        tuple[bool, str]: 成功したかどうかと、捕捉した出力全文。
    """
    buffer = io.StringIO()
    ok = True
    metrics = metrics if metrics is not None else {"tests_run": 0, "skipped": []}
    original_start = unittest.TestResult.startTest
    original_skip = unittest.TestResult.addSkip

    def start(result, test):
        """実行したテスト数を数える。"""
        metrics["tests_run"] += 1
        return original_start(result, test)

    def skip(result, test, reason):
        """スキップ理由を結果に保持する。"""
        metrics["skipped"].append({"test": test.id(), "reason": str(reason)})
        return original_skip(result, test, reason)

    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer), \
            mock.patch.object(unittest.TestResult, "startTest", start), \
            mock.patch.object(unittest.TestResult, "addSkip", skip):
        try:
            previous_argv = sys.argv
            try:
                sys.argv = [str(path)]
                runpy.run_path(str(path), run_name="__main__")
            finally:
                sys.argv = previous_argv
        except SystemExit as exit_signal:
            code = exit_signal.code
            ok = code is None or code == 0 or code is False
        except Exception:
            ok = False
            buffer.write("\n")
            buffer.write(traceback.format_exc())
    return ok, buffer.getvalue()


def run_all(notify=None, *, directories=None, names=None, suite="all"):
    """対象テストファイルをすべて実行し、結果を集計してログへ書き出す。

    Args:
        notify (Callable[[str], object] | None): サマリ文字列を受け取る
            任意の通知コールバック(例: 将来の Slack 投稿)。戻り値は無視する。

    Returns:
        dict: ``{"ok": bool, "total": int, "failed": list[str],
            "log_path": Path, "summary": str, "tests_run": int, "skipped": list,
            "failure_details": list[dict]}``。``ok`` は全ファイル成功なら True。
            ``failure_details`` は失敗ファイルの名前と捕捉した出力。
    """
    started_at = datetime.now()
    files = discover_test_files(directories, names, suite)
    results = []
    metrics = {"tests_run": 0, "skipped": []}
    for path in files:
        ok, output = _run_one(path, metrics)
        results.append((path.name, ok, output))

    failed = [name for name, ok, _ in results if not ok]
    finished_at = datetime.now()

    summary_lines = [
        f"mlib run_all_tests: {started_at:%Y-%m-%d %H:%M:%S} 開始",
        f"対象ファイル数: {len(results)} / 成功: {len(results) - len(failed)} / 失敗: {len(failed)}",
        f"所要時間: {(finished_at - started_at).total_seconds():.2f}秒",
    ]
    if failed:
        summary_lines.append("失敗したファイル: " + ", ".join(failed))
    summary = "\n".join(summary_lines)

    log_lines = [summary, ""]
    for name, ok, output in results:
        log_lines.append(f"{'OK  ' if ok else 'FAIL'} {name}")
        log_lines.append(output.rstrip("\n"))
        log_lines.append("-" * 70)
    log_text = "\n".join(log_lines) + "\n"

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{started_at:%Y%m%d_%H%M%S}.log"
    log_path.write_text(log_text, encoding="utf-8")

    print(summary)
    print(f"ログ: {log_path}")
    for name, ok, _ in results:
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
    failure_details = []
    for name, ok, output in results:
        if not ok:
            failure_details.append({"file": name, "output": output})
            print(f"\nFAIL {name}")
            print(output.rstrip())

    if notify is not None:
        notify(summary)

    return {
        "ok": not failed,
        "total": len(results),
        "failed": failed,
        "log_path": log_path,
        "summary": summary,
        "tests_run": metrics["tests_run"],
        "skipped": metrics["skipped"],
        "failure_details": failure_details,
    }


def main():
    """一括実行し、失敗があれば非ゼロで終了する。"""
    result = run_all()
    if not result["ok"]:
        raise AssertionError(f"mlib run_all_tests failed: {result['failed']}")


if __name__ == "__main__":
    main()
