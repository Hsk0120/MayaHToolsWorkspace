"""専用Mayaを2つ同時起動し、強制終了直後と再起動後の未保存タブを検証する。"""
from concurrent.futures import ThreadPoolExecutor
import ctypes
import datetime
import json
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[2]
sys.path.insert(0, str(ROOT / "maya/inhouse/mlib/__tests__"))
from runGui import run_version


class OwnedMayaProcess:
    """専用ランナーの起動証拠と実体を照合し、同じプロセスのハンドルを保持する。"""

    def __init__(self, directory, stage):
        """再利用されたPIDを後で開き直さず、ready時の実行ファイルを検証する。"""
        launch = json.loads((directory / stage / "launch.json").read_text(encoding="utf-8"))
        ready_pid = int((directory / (stage + ".ready")).read_text(encoding="utf-8"))
        if ready_pid != launch["pid"]:
            raise RuntimeError("Ready PID differs from this runner's launch PID")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        self.kernel.OpenProcess.restype = ctypes.c_void_p
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.kernel.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                                        ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
        self.handle = self.kernel.OpenProcess(0x1000 | 0x0001, False, ready_pid)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_ulong(len(buffer))
        try:
            if not self.kernel.QueryFullProcessImageNameW(self.handle, 0, buffer, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            if Path(buffer.value).resolve() != Path(launch["executable"]).resolve():
                raise RuntimeError("Executable differs from this runner's launch evidence")
        except Exception:
            self.close()
            raise

    def terminate(self):
        """DLL終了処理を通さず、所有する専用Mayaだけを終了する。"""
        if not self.kernel.TerminateProcess(self.handle, 23):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        """プロセスを終了せず、検証用ハンドルだけを解放する。"""
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def main():
    """指定Maya版で保存・同時編集・途中終了・2回の復元を検証する。"""
    version = sys.argv[1] if len(sys.argv) > 1 else "2027"
    external_termination = "--external-terminate" in sys.argv[2:]
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
                                           "MCE_SESSION_FILE": str(session), "MCE_RECOVERY_STAGE": stage,
                                           "MCE_RECOVERY_EXTERNAL_TERMINATE": "1" if external_termination else "0"})
        result_path = directory / stage / "result.json"
        suite = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
        # 23は専用GUIのos._exit。テスト成功記録と終了コードの両方が必要。
        expected = 23 if stage in ("A", "B") else 0
        outcome["crashDumps"] = [str(path) for path in (directory / stage).rglob("*.dmp")]
        outcome["accepted"] = (suite.get("status") == "passed"
                               and outcome.get("exit_code") == expected
                               and not outcome["crashDumps"])
        outcome["suite"] = suite
        outcome["termination_mode"] = "TerminateProcess" if external_termination else "os._exit"
        print(json.dumps(outcome, ensure_ascii=False), flush=True)
        return outcome

    results = [run("seed")]
    if results[-1]["accepted"]:
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(run, stage) for stage in ("A", "B")]
            owned = {}
            deadline = time.monotonic() + 120
            try:
                while time.monotonic() < deadline:
                    if all((directory / (stage + ".ready")).exists() for stage in ("A", "B")):
                        if external_termination:
                            for stage in ("A", "B"):
                                owned[stage] = OwnedMayaProcess(directory, stage)
                        (directory / "go").write_text("go", encoding="utf-8")
                        break
                    time.sleep(0.2)
                if external_termination and len(owned) == 2:
                    terminated = set()
                    deadline = time.monotonic() + 60
                    while time.monotonic() < deadline and len(terminated) < 2:
                        for stage, process in owned.items():
                            path = directory / stage / "result.json"
                            if stage in terminated or not path.exists():
                                continue
                            try:
                                suite = json.loads(path.read_text(encoding="utf-8"))
                            except json.JSONDecodeError:
                                continue
                            if suite.get("status") == "passed" and "external_termination_ready" in suite.get("checks", []):
                                process.terminate()
                                terminated.add(stage)
                        time.sleep(0.02)
            finally:
                for process in owned.values():
                    process.close()
            results.extend(job.result() for job in pending)
    if all(row["accepted"] for row in results):
        results.append(run("verify"))
    if all(row["accepted"] for row in results):
        results.append(run("verify_again"))
    (directory / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if len(results) == 5 and all(row["accepted"] for row in results) else 1


if __name__ == "__main__":
    sys.exit(main())
