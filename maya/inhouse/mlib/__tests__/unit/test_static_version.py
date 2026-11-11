"""Maya不要で、mlibの版番号が__init__.pyとmlib.modで一致し、Versionとして読めることを検証する。"""

import importlib.util
from pathlib import Path
import re
import unittest

_MLIB_ROOT = Path(__file__).resolve().parents[2]
_WORKSPACE_ROOT = _MLIB_ROOT.parents[2]
_MODULE_FILE = _WORKSPACE_ROOT / "maya" / "modules" / "mlib.mod"
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
    """__init__.py・mlib.modの版番号を突き合わせる。"""

    def setUp(self):
        self.version = _read_version()
        self.assertIsNotNone(self.version, "__version__ が mlib/__init__.py にない")

    def test_version_is_a_release_number(self):
        """__version__ は数字3桁の版で、mlib.Version として構築できる。"""
        self.assertRegex(self.version, r"^\d+\.\d+\.\d+$")
        Version = _load_version_class()
        self.assertEqual(Version(self.version), Version(self.version.split(".")))
        self.assertEqual(Version(self.version).suffix, "")

    def test_version_is_not_exported(self):
        """__version__ は __all__(明示した _names とクラス名)に入れない。"""
        text = (_MLIB_ROOT / "__init__.py").read_text(encoding="utf-8")
        match = re.search(r"^_names\s*=\s*\[(.*?)\]", text, re.S | re.M)
        self.assertIsNotNone(match)
        self.assertNotIn("__version__", match.group(1))
        self.assertRegex(text, r"(?m)^__all__ = _names \+ sorted\(_classes\)$")

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


if __name__ == "__main__":
    unittest.main()
