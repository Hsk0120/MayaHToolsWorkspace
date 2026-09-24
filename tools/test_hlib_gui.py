"""起動中MayaへGUIスイートを送り、遅延実行の最終結果まで待つ。"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=300,
                        help="送信完了後の待機秒数。タイムアウトしてもMaya側は停止しない")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    sent = subprocess.run(
        [sys.executable, str(ROOT / "tools/send_to_maya.py"),
         str(ROOT / "tools/run_hlib_gui_tests.py")],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", errors="replace")
    print(sent.stdout)
    if sent.returncode:
        return sent.returncode
    marker = "GUI tests scheduled: "
    paths = [line[len(marker):] for line in sent.stdout.splitlines() if line.startswith(marker)]
    if len(paths) != 1:
        print("GUI test output path was not returned. Do not automatically resend.")
        return 2
    path = Path(paths[0]).resolve()
    path.relative_to(ROOT / ".maya-output/gui-tests")
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        try:
            result = json.loads((path / "result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(.2)
            continue
        if result.get("status") != "running":
            print("Automated GUI assertions: {} ({} tests)".format(result["status"], result.get("tests", 0)))
            print("Evidence: " + str(path))
            print("Screenshot review and manual checks are separate; see result.json and the GUI test guide.")
            return 0 if result["status"] == "passed" else 1
        time.sleep(.2)
    print("GUI test wait timed out. Maya execution is NOT cancelled. Check result.json before any retry.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
