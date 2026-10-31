"""GUI検証の相対書込先と終了後の後始末をMayaなしで検証する。"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "maya/inhouse/mlib/__tests__"))
import runGui


class WorkingDirectoryTests(unittest.TestCase):
    """実ソースの代わりに最小fixtureでコピー残骸を模擬する。"""

    def test_cleanup_after_success_failure_and_timeout(self):
        """成功・失敗・監視タイムアウトでも所有cwdのみを後始末する。"""
        for status in ("passed", "failed", "timeout"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temp:
                base = Path(temp).resolve()
                binary = base / "install/Maya2027/bin/maya.exe"
                binary.parent.mkdir(parents=True)
                binary.touch()
                output = base / "result"
                created = []

                class Process:
                    """実Mayaを起動せず、Popenへ渡されたcwdを検査する。"""
                    pid = 123
                    returncode = 0

                    def __init__(self, args, cwd, **kwargs):
                        working = Path(cwd)
                        self.assert_safe(working)
                        created.append(working)
                        (working / "trial/mlib").mkdir(parents=True)
                        (working / "trial/orig").mkdir()
                        (working / "trial/mlib/example.py").write_text("# fixture\n", encoding="utf-8")
                        runGui.write_json(output / "result.json", {"status": status})

                    @staticmethod
                    def assert_safe(working):
                        if not working.is_absolute() or output not in working.parents:
                            raise AssertionError("cwd escaped test output")

                with patch.object(runGui.subprocess, "Popen", Process), patch.object(
                        runGui, "monitor_process", return_value={"timed_out": status == "timeout"}):
                    result = runGui.run_version("2027", output, base / "install", 1)
                self.assertEqual(result["status"], status)
                self.assertTrue(created)
                self.assertFalse(created[0].exists())
                self.assertTrue((output / "result.json").exists())
                record = json.loads((output / "working-directory.json").read_text(encoding="utf-8"))
                self.assertEqual(record["path"], str(created[0]))


if __name__ == "__main__":
    unittest.main()
