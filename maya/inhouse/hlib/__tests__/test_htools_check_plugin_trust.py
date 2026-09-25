"""HTools/system/checkWorkspacePluginTrust の検出処理を検証するMaya内テスト。

ユーザーの実設定(SafeModeAllowedlistPaths)は参照も変更もせず、テスト専用のoptionVar名を使う。
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import maya.cmds as cmds

import HTools.system.checkWorkspacePluginTrust as tool

OPTION_VAR = "hlibTestTrustedPluginPaths"


class CheckWorkspacePluginTrustTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.with_mll = self.root / "release" / "2027"
        self.without_mll = self.root / "other"
        self.with_mll.mkdir(parents=True)
        self.without_mll.mkdir()
        (self.with_mll / "sample.mll").write_bytes(b"")
        self.outside = Path(tempfile.mkdtemp())
        (self.outside / "outside.mll").write_bytes(b"")
        if cmds.optionVar(exists=OPTION_VAR):
            cmds.optionVar(remove=OPTION_VAR)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.outside, ignore_errors=True)
        if cmds.optionVar(exists=OPTION_VAR):
            cmds.optionVar(remove=OPTION_VAR)

    def _path_var(self, *paths):
        return os.pathsep.join(str(p) for p in paths)

    def test_only_directories_inside_root_that_contain_mll_are_selected(self):
        value = self._path_var(self.with_mll, self.without_mll, self.outside, self.root / "missing", "")
        found = tool.workspace_plugin_locations(value, root=self.root)
        self.assertEqual(found, [str(self.with_mll).replace("\\", "/")])

    def test_duplicate_entries_are_reported_once(self):
        value = self._path_var(self.with_mll, self.with_mll)
        self.assertEqual(len(tool.workspace_plugin_locations(value, root=self.root)), 1)

    def test_untrusted_ignores_registered_locations_regardless_of_case_and_separator(self):
        location = str(self.with_mll).replace("\\", "/")
        self.assertEqual(tool.untrusted([location], OPTION_VAR), [location])
        cmds.optionVar(stringValueAppend=(OPTION_VAR, location.upper().replace("/", "\\")))
        self.assertEqual(tool.untrusted([location], OPTION_VAR), [])

    def test_trusted_locations_is_empty_when_unset(self):
        self.assertEqual(tool.trusted_locations(OPTION_VAR), [])

    def test_default_scan_root_is_limited_to_inhouse(self):
        self.assertEqual(tool.SCAN_ROOT, tool.WORKSPACE_ROOT / "maya" / "inhouse")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
