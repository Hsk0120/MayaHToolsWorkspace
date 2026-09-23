"""hlib.workspace の Workspace を検証するMaya内テスト。"""

import sys
import tempfile
import unittest
from pathlib import Path

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.workspace import Workspace


class WorkspaceTest(unittest.TestCase):
    """現在のワークスペースの参照・ファイルルール・パス展開を検証する。"""

    def setUp(self):
        self.previous_root = cmds.workspace(query=True, rootDirectory=True)
        self.previous_scene_rule = cmds.workspace(fileRuleEntry="scene")

    def tearDown(self):
        cmds.workspace(self.previous_root, openWorkspace=True)
        cmds.workspace(fileRule=("scene", self.previous_scene_rule))

    def test_root_matches_cmds_workspace(self):
        self.assertEqual(Workspace.root(), Path(self.previous_root))

    def test_open_changes_current_workspace_and_restores(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            Workspace.open(tmp_dir)
            self.assertEqual(Workspace.root(), Path(tmp_dir).resolve())
        # tearDown が元のワークスペースへ戻す。ここでは明示的に検証もしておく。
        cmds.workspace(self.previous_root, openWorkspace=True)
        self.assertEqual(Workspace.root(), Path(self.previous_root))

    def test_open_rejects_invalid_path(self):
        with self.assertRaises(ValueError):
            Workspace.open("")
        with self.assertRaises(ValueError):
            Workspace.open(123)

    def test_rule_get_set_round_trip(self):
        self.assertEqual(Workspace.rule("scene"), self.previous_scene_rule)
        Workspace.set_rule("scene", "hlibScenesDir")
        self.assertEqual(Workspace.rule("scene"), "hlibScenesDir")

    def test_rule_returns_empty_string_for_unknown_rule(self):
        self.assertEqual(Workspace.rule("hlibDoesNotExistRule123"), "")

    def test_rules_includes_known_rule_names(self):
        rules = Workspace.rules()
        self.assertIn("scene", rules)

    def test_expand_resolves_relative_to_root_literally(self):
        # expandName はファイルルール名としては解決せず、文字通り root に連結する。
        expanded = Workspace.expand("myScene.ma")
        self.assertEqual(expanded, Workspace.root() / "myScene.ma")

    def test_path_for_combines_root_rule_and_filename(self):
        result = Workspace.path_for("scene", "myScene.ma")
        self.assertEqual(result, Workspace.root() / self.previous_scene_rule / "myScene.ma")

        directory_only = Workspace.path_for("scene")
        self.assertEqual(directory_only, Workspace.root() / self.previous_scene_rule)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
