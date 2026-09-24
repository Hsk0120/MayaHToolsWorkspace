"""Mayaを起動せずにバージョン別ランナーの結果判定と環境分離を検証する。"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import run_hlib_tests as runner


class MatrixRunnerTest(unittest.TestCase):
    def test_missing_exit_codes_and_results(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for extra, expected in (([], 2), (["--allow-missing"], 0)):
                argv = ["test", "--versions", "2023", "--output", str(root)] + extra
                with mock.patch.object(runner.sys, "argv", argv), mock.patch.object(
                        runner, "maya_executable", return_value=root / "missing.exe"):
                    self.assertEqual(runner.main(), expected)
            results = list(root.glob("*/2023/result.json"))
            self.assertEqual(len(results), 2)
            self.assertTrue(all(json.loads(p.read_text())["status"] == "missing" for p in results))

    def test_environment_does_not_mutate_parent(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.dict(os.environ, {
                "MAYA_APP_DIR": "user-preferences", "PYTHONPATH": "external", "QT_PLUGIN_PATH": "old"}):
            result = runner.isolated_environment(Path("C:/Autodesk/Maya2027/bin/mayapy.exe"), Path(temp))
            self.assertNotEqual(result["MAYA_APP_DIR"], "user-preferences")
            self.assertEqual(os.environ["MAYA_APP_DIR"], "user-preferences")
            self.assertNotIn("QT_PLUGIN_PATH", result)
            self.assertEqual(result["MAYA_UI_LANGUAGE"], "en_US")

    def test_nonzero_exit_cannot_report_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            exe = root / "mayapy.exe"
            exe.touch()
            directory = root / "2027"
            process = mock.Mock()

            def finish(timeout):
                runner.write_json(directory / "result.json", {"requested_version": "2027", "status": "passed"})
                return 9

            process.wait.side_effect = finish
            with mock.patch.object(runner.subprocess, "Popen", return_value=process):
                result = runner.run_version("2027", exe, directory, 10)
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["exit_code"], 9)

    def test_timeout_stops_spawned_process(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            exe = root / "mayapy.exe"
            exe.touch()
            process = mock.Mock(pid=12345)
            process.wait.side_effect = [subprocess.TimeoutExpired("test", 1), 1]
            process.poll.return_value = None
            with mock.patch.object(runner.subprocess, "Popen", return_value=process), mock.patch.object(
                    runner.subprocess, "run"):
                result = runner.run_version("2027", exe, root / "2027", 1)
            self.assertEqual(result["status"], "timeout")
            process.kill.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
