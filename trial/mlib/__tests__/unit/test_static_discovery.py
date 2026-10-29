"""本体テストの探索範囲と、指定ミスで空の成功を返さないことを検証する。"""
from pathlib import Path
import contextlib
import io
import tempfile
import unittest
from unittest import mock

import run_all_tests


class DiscoveryTest(unittest.TestCase):
    def test_failures_keep_tracebacks_and_passed_output_stays_in_log(self):
        """値不一致・例外を保存/表示し、成功したファイルの出力は表示しない。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = root / "cases"
            cases.mkdir()
            bodies = {
                "test_pass.py": 'print("passed output only in log")\nself.assertEqual(5, 5)',
                "test_fail.py": 'self.assertEqual(5, 10)',
                "test_error.py": 'raise RuntimeError("failure detail example")',
            }
            for name, body in bodies.items():
                source = ("import unittest\nclass Example(unittest.TestCase):\n"
                          "    def test_example(self):\n        " + body.replace("\n", "\n        ")
                          + '\nif __name__ == "__main__":\n    unittest.main()\n')
                (cases / name).write_text(source, encoding="utf-8")
            terminal = io.StringIO()
            with mock.patch.object(run_all_tests, "LOG_DIR", root / "logs"), contextlib.redirect_stdout(terminal):
                result = run_all_tests.run_all(directories=[cases])
            self.assertFalse(result["ok"])
            self.assertEqual(result["tests_run"], 3)
            self.assertEqual(result["failed"], ["test_error.py", "test_fail.py"])
            self.assertEqual([row["file"] for row in result["failure_details"]], result["failed"])
            text = terminal.getvalue()
            self.assertIn("AssertionError: 5 != 10", text)
            self.assertIn("RuntimeError: failure detail example", text)
            self.assertIn(str(cases / "test_fail.py"), text)
            self.assertIn(str(result["log_path"]), text)
            self.assertNotIn("passed output only in log", text)
            self.assertIn("passed output only in log", result["log_path"].read_text(encoding="utf-8"))

    def test_unit_and_integration_can_run_separately(self):
        files = run_all_tests.discover_test_files(suite="unit")
        self.assertTrue(files)
        root = Path(run_all_tests.__file__).parent / "unit"
        self.assertTrue(all(root in path.parents for path in files))
        self.assertEqual(files, sorted(files, key=lambda path: (path.name, str(path))))
        integration = run_all_tests.discover_test_files(suite="integration")
        self.assertTrue(integration)
        self.assertFalse(set(files) & set(integration))
        self.assertEqual(set(files + integration), set(run_all_tests.discover_test_files()))
        self.assertTrue(all(not path.name.startswith("test_static_") for path in files))

    def test_selects_known_file_and_rejects_a_typo(self):
        files = run_all_tests.discover_test_files(names=["test_datatypes.py"])
        self.assertEqual([path.name for path in files], ["test_datatypes.py"])
        with self.assertRaises(ValueError):
            run_all_tests.discover_test_files(names=["test_does_not_exist.py"])


if __name__ == "__main__":
    unittest.main()
