"""QPE終了時クラッシュを専用Mayaの終了コード・ダンプで判定する。"""
import argparse
import json
from pathlib import Path
import sys


def main():
    """通常終了とDLL終了を独立したMayaプロセスで繰り返す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--maya", choices=("2022", "2027"), required=True)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--mode", choices=("normal", "abrupt", "both"), default="both")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "maya/inhouse/mlib/__tests__"))
    # 専用prefsと所有プロセスだけの終了処理は既存ランナーを再利用する。
    from runGui import run_version

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    modes = ("normal", "abrupt") if args.mode == "both" else (args.mode,)
    rows = []
    for index in range(args.repeat):
        for mode in modes:
            target = out / ("%02d-%s" % (index + 1, mode))
            result = run_version(args.maya, target, Path("C:/Program Files/Autodesk"),
                                 180, shutdown_timeout=30,
                                 suite_path=root / "tools/qpe_ui_shutdown.py",
                                 environment={"QPE_SHUTDOWN_TEST": "1", "QPE_SHUTDOWN_MODE": mode})
            suite_path = target / "result.json"
            suite = json.loads(suite_path.read_text(encoding="utf-8")) if suite_path.exists() else {}
            dumps = [str(path) for path in target.rglob("*.dmp")]
            expected = 23 if mode == "abrupt" else 0
            accepted = (suite.get("status") == "passed" and result.get("exit_code") == expected
                        and not result.get("timed_out") and not dumps)
            rows.append({"mode": mode, "accepted": accepted, "crash_dumps": dumps,
                         "expected_exit": expected, "process": result})
            (out / "summary.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
            print(args.maya, index + 1, mode, "passed" if accepted else "FAILED", flush=True)
            if not accepted:
                return 1
    return 0 if all(row["accepted"] for row in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
