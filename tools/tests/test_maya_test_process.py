"""実プロセスで監視期限・終了・対象の分離を検証する。Mayaは起動しない。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _maya_test_process import monitor_process, read_result, stop_owned_process


class ProcessMonitorTests(unittest.TestCase):
    def run_timeout(self, phase):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            if phase == "tests":
                (directory / "started.json").write_text("{}", encoding="utf-8")
            elif phase == "shutdown":
                (directory / "result.json").write_text(json.dumps({"status": "passed"}), encoding="utf-8")
            owned = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                result = monitor_process(owned, directory, 0.2, 0.2, poll_seconds=0.02)
                self.assertTrue(result["timed_out"])
                self.assertEqual(result["timeout_phase"], phase)
                self.assertTrue(result["owned_process_stopped"])
                self.assertIsNone(unrelated.poll(), "Unrelated process must survive")
                if phase == "shutdown":
                    self.assertEqual(result["suite_status"], "passed")
            finally:
                stop_owned_process(owned)
                stop_owned_process(unrelated)

    def test_startup_timeout(self):
        self.run_timeout("startup")

    def test_test_timeout(self):
        self.run_timeout("tests")

    def test_shutdown_timeout_preserves_suite_result(self):
        self.run_timeout("shutdown")

    def test_normal_exit_and_failure_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            for code in (0, 7):
                process = subprocess.Popen([sys.executable, "-c", "raise SystemExit({})".format(code)])
                result = monitor_process(process, Path(temporary), 5, 5)
                self.assertFalse(result["timed_out"])
                self.assertEqual(result["exit_code"], code)

    def test_partial_result_is_retried(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            path.write_text('{"status":', encoding="utf-8")
            self.assertEqual(read_result(path), {})
            path.write_text('{"status":"failed"}', encoding="utf-8")
            self.assertEqual(read_result(path)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
