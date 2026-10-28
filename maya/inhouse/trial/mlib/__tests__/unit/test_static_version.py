"""Maya不要で、mlibの版番号が3か所で一致し、Versionとして読めることを検証する。"""

import importlib.util
from pathlib import Path
import re
import unittest

_MLIB_ROOT = Path(__file__).resolve().parents[2]
_WORKSPACE_ROOT = _MLIB_ROOT.parents[2]
_MODULE_FILE = _WORKSPACE_ROOT / "maya" / "modules" / "mlib.mod"
_CHANGELOG = _MLIB_ROOT / "_docs" / "source" / "changelog.rst"
_MAYA_VERSIONS = ("2022", "2023", "2024", "2025", "2026", "2027")


def _read_version():
    """mlib/__init__.pyの__version__を、mlibをimportせずに読む。"""
    text = (_MLIB_ROOT / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.M)
    return match.group(1) if match else None


def _load_version_class():
    """mlib.common.versionをパッケージ初期化(Maya依存)を通さずに読み込む。"""
    path = _MLIB_ROOT / "common" / "version.py"
    spec = importlib.util.spec_from_file_location("_mlib_static_version", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Version


class VersionConsistencyTest(unittest.TestCase):
    """__init__.py・mlib.mod・changelog.rstの版番号を突き合わせる。"""

    def setUp(self):
        self.version = _read_version()
        self.assertIsNotNone(self.version, "__version__ が mlib/__init__.py にない")

    def test_version_is_a_release_number(self):
        """__version__ は数字3桁の版で、mlib.common.Version として構築できる。"""
        self.assertRegex(self.version, r"^\d+\.\d+\.\d+$")
        Version = _load_version_class()
        self.assertEqual(Version(self.version), Version(self.version.split(".")))
        self.assertEqual(Version(self.version).suffix, "")

    def test_version_is_not_exported(self):
        """__version__ は __all__ に入れない。"""
        text = (_MLIB_ROOT / "__init__.py").read_text(encoding="utf-8")
        match = re.search(r"^__all__\s*=\s*\[(.*?)\]", text, re.S | re.M)
        self.assertIsNotNone(match)
        self.assertNotIn("__version__", match.group(1))

    def test_module_file_matches(self):
        """mlib.mod の対応する全Mayaバージョンの行が同じ版番号を持つ。"""
        lines = _MODULE_FILE.read_text(encoding="utf-8").splitlines()
        entries = {}
        for line in lines:
            match = re.match(r"\+ MAYAVERSION:(\d{4}) PLATFORM:\S+ mlib (\S+) ", line)
            if match:
                entries[match.group(1)] = match.group(2)
        self.assertEqual(tuple(sorted(entries)), _MAYA_VERSIONS)
        self.assertEqual(set(entries.values()), {self.version}, entries)

    def test_changelog_heading_matches(self):
        """changelog.rst の最初の版の見出しが __version__ と同じで、日付を持つ。"""
        text = _CHANGELOG.read_text(encoding="utf-8")
        headings = re.findall(r"^(\d+\.\d+\.\d+)(?: \((\d{4}-\d{2}-\d{2})\))?\n-+\n", text, re.M)
        self.assertTrue(headings, "changelog.rst に版の見出しがない")
        latest, date = headings[0]
        self.assertEqual(latest, self.version)
        self.assertTrue(date, "最新版の見出しに日付 (YYYY-MM-DD) がない")
        Version = _load_version_class()
        versions = [Version(item[0]) for item in headings]
        self.assertEqual(versions, sorted(versions, reverse=True), "版の見出しは新しい順に並べる")


if __name__ == "__main__":
    unittest.main()
