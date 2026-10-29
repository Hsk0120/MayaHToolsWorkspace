"""Mayaを起動せずにバージョン別ランナーの結果判定と環境分離を検証する。"""
import json
import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import runMaya as runner


class MatrixRunnerTest(unittest.TestCase):
    def test_main_prints_failed_test_output_and_detail_log(self):
        """親プロセスのターミナルへ失敗内容を出し、終了1とJSONも維持する。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            detail_log = root / "日本語 logs" / "tests.log"
            failure = {"file": "test_example.py", "output": "Traceback: line 15\nAssertionError: 5 != 10\n"}

            def complete(version, executable, directory, *arguments):
                directory.mkdir()
                return {"requested_version": version, "status": "failed", "exit_code": 1,
                        "failed_files": [failure["file"]], "suite_log": str(detail_log),
                        "failure_details": [failure]}

            terminal = io.StringIO()
            argv = ["test", "--versions", "2027", "--output", str(root / "output")]
            with mock.patch.object(runner.sys, "argv", argv), mock.patch.object(
                    runner, "run_version", side_effect=complete), contextlib.redirect_stdout(terminal):
                code = runner.main()
            self.assertEqual(code, 1)
            text = terminal.getvalue()
            self.assertIn(str(detail_log.resolve()), text)
            self.assertIn("FAIL test_example.py", text)
            self.assertIn("Traceback: line 15\nAssertionError: 5 != 10", text)
            path = next((root / "output").glob("*/2027/result.json"))
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["failure_details"], [failure])

    def test_error_and_timeout_show_available_logs_without_reading_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "console.log"
            path.write_text("startup messages", encoding="utf-8")
            for result in ({"status": "error", "error": "RuntimeError: initialization failed"},
                           {"status": "timeout", "timeout_seconds": 12}):
                terminal = io.StringIO()
                with contextlib.redirect_stdout(terminal):
                    runner._print_failure_details(result, root)
                self.assertIn(str(path.resolve()), terminal.getvalue())
                if result["status"] == "error":
                    self.assertIn(result["error"], terminal.getvalue())
                else:
                    self.assertIn("12", terminal.getvalue())

    def test_passed_result_does_not_print_failure_details(self):
        terminal = io.StringIO()
        with contextlib.redirect_stdout(terminal):
            runner._print_failure_details({"status": "passed"}, Path.cwd())
        self.assertEqual(terminal.getvalue(), "")

    def test_gui_main_prints_failed_test_output_and_keeps_exit_code(self):
        import runGui as gui_runner

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def complete(version, directory, *arguments, **kwargs):
                directory.mkdir(parents=True)
                return {"status": "failed", "failed_files": ["test_gui.py"],
                        "suite_log": str(directory / "details.log"),
                        "failure_details": [{"file": "test_gui.py", "output": "AssertionError: GUI detail"}]}

            terminal = io.StringIO()
            argv = ["test", "--versions", "2027", "--suite", "unit"]
            with mock.patch.object(gui_runner.sys, "argv", argv), mock.patch.object(
                    gui_runner, "TESTS_DIR", root), mock.patch.object(
                    gui_runner, "run_version", side_effect=complete), contextlib.redirect_stdout(terminal):
                self.assertEqual(gui_runner.main(), 1)
            self.assertIn("FAIL test_gui.py", terminal.getvalue())
            self.assertIn("AssertionError: GUI detail", terminal.getvalue())
            self.assertIn("details.log", terminal.getvalue())

    def test_relative_suite_resolves_before_worker_changes_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite = root / "suite.py"
            suite.write_text("", encoding="utf-8")
            relative = os.path.relpath(str(suite), str(Path.cwd()))
            argv = ["test", "--versions", "2027", "--suite-file", relative, "--output", str(root / "output")]
            def complete(version, executable, directory, *arguments):
                directory.mkdir()
                return {"requested_version": version, "status": "passed"}

            with mock.patch.object(runner.sys, "argv", argv), mock.patch.object(
                    runner, "run_version", side_effect=complete) as run:
                self.assertEqual(runner.main(), 0)
            self.assertEqual(run.call_args[0][4], suite.resolve())

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

    def test_fbx_directory_is_test_local(self):
        """存在する同一MayaのFBXディレクトリだけ子環境へ追加する。"""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            exe = root / "Maya2022/bin/mayapy.exe"
            fbx = exe.parent.parent / "plug-ins/fbx/plug-ins"
            fbx.mkdir(parents=True)
            (root / 'run').mkdir()
            with mock.patch.dict(os.environ, {"MAYA_PLUG_IN_PATH": "user-path"}):
                env = runner.isolated_environment(exe, root / "run")
                self.assertEqual(env["MAYA_PLUG_IN_PATH"], str(fbx))
                self.assertEqual(os.environ["MAYA_PLUG_IN_PATH"], "user-path")

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
