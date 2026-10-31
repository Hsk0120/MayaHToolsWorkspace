"""検証用フォルダーの標準モジュール衝突検出を、副作用なしで検証する。"""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "maya/inhouse/mlib/__tests__"))
import runGui
from support.importSafety import find_shadowing


class ImportSafetyTests(unittest.TestCase):
    """対象スクリプトをimportせず、Mayaを起動する前に拒否する。"""

    def test_source_legacy_bytecode_and_package_without_execution(self):
        """ソース・旧形式pyc・パッケージを検出し、名前空間だけの空フォルダーは許す。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "copy.py"
            source.write_text("raise AssertionError('must not execute')\n", encoding="utf-8")
            (root / "json.pyc").write_bytes(b"not valid bytecode")
            (root / "shutil").mkdir()
            (root / "shutil/__init__.py").write_text("raise AssertionError('must not execute')\n", encoding="utf-8")
            (root / "tempfile").mkdir()
            self.assertEqual(set(find_shadowing(root)),
                             {source, root / "json.pyc", root / "shutil/__init__.py"})
            self.assertFalse((root / "trial").exists())

    def test_target_maya_legacy_module_and_quarantine(self):
        """ホストPythonに無い旧Mayaの標準名も検出し、退避したtxtは読み込まない。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library, scripts = root / "stdlib", root / "scripts"
            library.mkdir()
            scripts.mkdir()
            (library / "legacy_probe_module.py").touch()
            bad = scripts / "legacy_probe_module.py"
            bad.write_text("raise AssertionError('must not execute')\n", encoding="utf-8")
            self.assertEqual(find_shadowing(scripts, [library]), [bad])
            bad.rename(scripts / "legacy_probe_module.py.txt")
            self.assertEqual(find_shadowing(scripts, [library]), [])

    def test_gui_runner_rejects_before_launch(self):
        """危険な隣接copy.pyがある場合はMayaプロセスを起動しない。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "install/Maya2027/bin/maya.exe"
            executable.parent.mkdir(parents=True)
            executable.touch()
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "copy.py").write_text("raise AssertionError('must not execute')\n", encoding="utf-8")
            suite = scripts / "probe.py"
            suite.touch()
            with patch.object(runGui.subprocess, "Popen") as launch:
                with self.assertRaisesRegex(ValueError, "copy.py"):
                    runGui.run_version("2027", root / "output", root / "install", 1, suite_path=suite)
                launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
