"""GUI監査の失敗を正常終了として報告しないことをMayaなしで検証する。"""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import qpe_audit_runner


class AuditRunnerTests(unittest.TestCase):
    """専用GUIランナーの結果と監査CLIの終了コードを照合する。"""

    def test_standalone_relative_writes_are_removed(self):
        """単体版でも相対コピーの残骸をソース外へ隔離して後始末する。"""
        with tempfile.TemporaryDirectory() as directory:
            created = []

            def run(args, cwd, **kwargs):
                """起動先の書込だけを模擬し、実ソースをコピーしない。"""
                working = Path(cwd)
                self.assertIn(Path(directory).resolve(), working.parents)
                created.append(working)
                (working / "trial/mlib").mkdir(parents=True)
                (working / "trial/orig").mkdir()
                (Path(args[-1]) / "result.json").write_text(json.dumps({"status": "passed"}), encoding="utf-8")
                return types.SimpleNamespace(returncode=0)

            argv = ["qpe_audit_runner.py", directory, "--suites", "context"]
            with patch.object(qpe_audit_runner.subprocess, "run", run), patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(qpe_audit_runner.main(), 0)
            self.assertFalse(created[0].exists())

    def test_gui_failure_exit_status_and_import_bootstrap(self):
        """成功・失敗・タイムアウトを区別し、補助importを隔離環境でも解決する。"""
        for status in ("passed", "failed", "timeout", "error"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                def run_version(*args, **kwargs):
                    """Maya起動の代わりに実際に生成した入口を検査して結果を返す。"""
                    source = kwargs["suite_path"].read_text(encoding="utf-8")
                    self.assertIn("sys.path.insert", source)
                    compile(source, str(kwargs["suite_path"]), "exec")
                    return {"status": status}

                fake = types.SimpleNamespace(run_version=run_version)
                argv = ["qpe_audit_runner.py", directory, "--maya", "2022", "--suites", "sidebars"]
                with patch.dict(sys.modules, {"runGui": fake}), patch.object(sys, "argv", argv):
                    with contextlib.redirect_stdout(io.StringIO()):
                        code = qpe_audit_runner.main()
                self.assertEqual(code, 0 if status == "passed" else 1)
                self.assertTrue((Path(directory) / "summary.json").is_file())


if __name__ == "__main__":
    unittest.main()
