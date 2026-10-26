"""専用Mayaを2つ同時起動し、強制終了直後と再起動後の未保存タブを検証する。"""
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[2]
sys.path.insert(0, str(ROOT / "maya/inhouse/mlib/__tests__"))
from runGui import run_version


def main():
    """指定Maya版で保存・同時編集・途中終了・2回の復元を検証する。"""
    version = sys.argv[1] if len(sys.argv) > 1 else "2027"
    directory = ROOT / ".maya-output/mce-recovery" / datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    modules = directory / "modules"
    modules.mkdir(parents=True)
    definition = (ROOT / "maya/modules/MayaCodeEditor.mod").read_text(encoding="utf-8").replace("../inhouse/MayaCodeEditor", PROJECT.as_posix())
    (modules / "MayaCodeEditor.mod").write_text(definition, encoding="utf-8")
    session = directory / "tabs.json"
    print(str(directory), flush=True)

    def run(stage):
        outcome = run_version(version, directory / stage, Path("C:/Program Files/Autodesk"), 180,
                              shutdown_timeout=30, suite_path=PROJECT / "tests/recovery_gui.py",
                              environment={"MAYA_MODULE_PATH": str(modules), "MCE_TEST_COMMANDS": "1",
                                           "MCE_SESSION_FILE": str(session), "MCE_RECOVERY_STAGE": stage})
        result_path = directory / stage / "result.json"
        suite = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
        # 23は専用GUIのos._exit。テスト成功記録と終了コードの両方が必要。
        expected = 23 if stage in ("A", "B") else 0
        outcome["accepted"] = suite.get("status") == "passed" and outcome.get("exit_code") == expected
        outcome["suite"] = suite
        print(json.dumps(outcome, ensure_ascii=False), flush=True)
        return outcome

    results = [run("seed")]
    if results[-1]["accepted"]:
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(run, stage) for stage in ("A", "B")]
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if all((directory / (stage + ".ready")).exists() for stage in ("A", "B")):
                    (directory / "go").write_text("go", encoding="utf-8")
                    break
                time.sleep(0.2)
            results.extend(job.result() for job in pending)
    if all(row["accepted"] for row in results):
        results.append(run("verify"))
    if all(row["accepted"] for row in results):
        results.append(run("verify_again"))
    (directory / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if len(results) == 5 and all(row["accepted"] for row in results) else 1


if __name__ == "__main__":
    sys.exit(main())
