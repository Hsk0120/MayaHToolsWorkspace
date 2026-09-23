"""hlib/__tests__ 配下の全テストを一括実行し、結果をログへ出力する。

他のテストスクリプトと同じ手段(VS Code の Ctrl+S → Ctrl+Shift+B、または
Maya の Script Editor)で、このファイル自体を送信して実行する。

対象は同ディレクトリの ``test_*.py`` のうち、以下を除いたすべて:

- ``test_command_discovery.py``: mayapy 単体プロセスでの実行専用。Maya GUI の
  commandPort 経由で実行すると、内部の subprocess が新しい Maya.exe を
  起動してしまうため対象外。
- ``test_maya_standalone.py``: 存在しない ``HTools.decorator`` を参照しており
  常に ImportError になる、疎通確認用の手動スクリプト。
- ``test_slack_postMessage.py``: ``SLACK_API_BOT_TOKEN`` が必須で、実行すると
  実際に Slack へメッセージを投稿する副作用があるため、一括実行には含めない。

``test_scene_api.py`` は setUp/tearDown で現在のシーンを ``new(force=True)``
するため、一括実行すると現在開いているシーンの未保存の変更は失われる
(このテストを単体実行した場合も同様で、本スクリプト固有の挙動ではない)。
保存したい変更がある場合は実行前に保存すること。

ログは ``__tests__/.logs/`` 配下へ ``YYYYMMDD_HHMMSS.log`` として書き出す
(``*.log`` は .gitignore 済み)。将来的な Slack 通知などへの接続点として、
``run_all(notify=...)`` にサマリ文字列を受け取るコールバックを渡せる
(``hlib.utils.progress.progress_bar`` の ``notify`` と同じ考え方)。
"""

import contextlib
import io
import runpy
import sys
import traceback
from datetime import datetime
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
LOG_DIR = TESTS_DIR / ".logs"

EXCLUDED_FILES = {
    Path(__file__).name,
    "test_command_discovery.py",
    "test_maya_standalone.py",
    "test_slack_postMessage.py",
}


def discover_test_files():
    """一括実行対象の test_*.py パスを名前順で取得する。

    Returns:
        list[Path]: 除外ファイルを除いた対象パスのリスト。
    """
    return sorted(
        path for path in TESTS_DIR.glob("test_*.py")
        if path.name not in EXCLUDED_FILES
    )


def _run_one(path):
    """1つのテストファイルを他のファイルへ影響しない形で実行する。

    ``tools/send_to_maya.py`` が個別実行時に使うのと同じ
    ``runpy.run_path(path, run_name="__main__")`` を使い、各ファイル自身の
    ``if __name__ == "__main__":`` ブロック(unittest.main 呼び出し)を
    そのまま動かす。標準出力・標準エラーは呼び出し元に流さず捕捉する。

    Args:
        path (Path): 実行する test_*.py のパス。

    Returns:
        tuple[bool, str]: 成功したかどうかと、捕捉した出力全文。
    """
    buffer = io.StringIO()
    ok = True
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        try:
            runpy.run_path(str(path), run_name="__main__")
        except SystemExit as exit_signal:
            code = exit_signal.code
            ok = code is None or code == 0 or code is False
        except Exception:
            ok = False
            buffer.write("\n")
            buffer.write(traceback.format_exc())
    return ok, buffer.getvalue()


def run_all(notify=None):
    """対象テストファイルをすべて実行し、結果を集計してログへ書き出す。

    Args:
        notify (Callable[[str], object] | None): サマリ文字列を受け取る
            任意の通知コールバック(例: 将来の Slack 投稿)。戻り値は無視する。

    Returns:
        dict: ``{"ok": bool, "total": int, "failed": list[str],
            "log_path": Path, "summary": str}``。``ok`` は全ファイル成功なら True。
    """
    started_at = datetime.now()
    files = discover_test_files()
    results = []
    for path in files:
        ok, output = _run_one(path)
        results.append((path.name, ok, output))

    failed = [name for name, ok, _ in results if not ok]
    finished_at = datetime.now()

    summary_lines = [
        f"hlib run_all_tests: {started_at:%Y-%m-%d %H:%M:%S} 開始",
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

    if notify is not None:
        notify(summary)

    return {
        "ok": not failed,
        "total": len(results),
        "failed": failed,
        "log_path": log_path,
        "summary": summary,
    }


def main():
    """一括実行し、失敗があれば非ゼロで終了する。"""
    result = run_all()
    if not result["ok"]:
        raise AssertionError(f"hlib run_all_tests failed: {result['failed']}")


if __name__ == "__main__":
    main()
