"""hlib Scene file APIを検証するMaya内テスト。"""

import sys
import tempfile
import unittest
from pathlib import Path

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.files import Scene
from hlib.files import Scene as SceneFromPackage


class SceneApiTest(unittest.TestCase):
    """現在シーンの参照とファイル操作を検証する。"""

    def setUp(self):
        self.scene = Scene()
        self.path = Path(tempfile.gettempdir()) / "hlib_scene_api.ma"
        self.import_path = Path(tempfile.gettempdir()) / "hlib_scene_api_import_source.ma"
        if self.path.exists():
            self.path.unlink()
        if self.import_path.exists():
            self.import_path.unlink()
        self.scene.new(force=True, prompt=False)

    def tearDown(self):
        self.scene.new(force=True, prompt=False)
        if self.path.exists():
            self.path.unlink()
        if self.import_path.exists():
            self.import_path.unlink()

    def test_public_api_and_new_scene_state(self):
        self.assertIs(Scene, SceneFromPackage)
        self.assertIsNone(self.scene.path())
        self.assertIsNone(self.scene.name())
        self.assertTrue(self.scene.is_new())
        self.assertFalse(self.scene.is_modified())

    def test_save_open_and_new(self):
        cmds.createNode("transform", name="hlibSceneApiNode")
        self.assertTrue(self.scene.is_modified())

        result = self.scene.save_as(self.path)
        self.assertIs(result, self.scene)
        self.assertEqual(self.scene.path(), self.path)
        self.assertEqual(self.scene.name(), self.path.name)
        self.assertEqual(self.scene.file_type(), "mayaAscii")
        self.assertFalse(self.scene.is_modified())

        self.scene.open(self.path, force=True, prompt=False)
        self.assertEqual(self.scene.path(), self.path)
        self.scene.new(force=True, prompt=False)
        self.assertTrue(self.scene.is_new())

    def test_invalid_save_as_extension(self):
        with self.assertRaises(ValueError):
            self.scene.save_as(self.path.with_suffix(".txt"))

    def test_import_file_brings_in_nodes_under_namespace(self):
        cmds.createNode("transform", name="hlibImportSourceNode")
        self.scene.save_as(self.import_path)
        self.scene.new(force=True, prompt=False)
        cmds.createNode("transform", name="hlibSceneApiNode")

        new_nodes = self.scene.import_file(self.import_path, namespace="hlibImportedNs")
        imported_names = [node.name() for node in new_nodes]
        self.assertTrue(any(name.endswith("hlibImportSourceNode") for name in imported_names))
        self.assertTrue(cmds.objExists("hlibImportedNs:hlibImportSourceNode"))
        self.assertTrue(cmds.objExists("hlibSceneApiNode"))

    def test_import_file_requires_current_scene(self):
        cmds.createNode("transform", name="hlibImportSourceNode")
        self.scene.save_as(self.import_path)
        self.scene.new(force=True, prompt=False)

        stale = Scene(self.import_path)
        with self.assertRaises(RuntimeError):
            stale.import_file(self.import_path)

    def test_scene_command_snapshots_without_opening(self):
        self.assertIs(hlib.scene, hlib.cmds.scene)
        self.assertEqual(str(hlib.scene()), "untitled")
        other = hlib.scene(self.path)
        self.assertEqual(other.path(), self.path.resolve())
        self.assertEqual(str(other), str(self.path.resolve()))
        self.assertTrue(self.scene.is_new())
        self.assertFalse(other.is_current())
        with self.assertRaises(RuntimeError):
            other.save()
        with self.assertRaises(RuntimeError):
            other.is_modified()
        self.scene.save_as(self.path)
        captured = hlib.scene()
        self.scene.new(force=True, prompt=False)
        self.assertEqual(captured.path(), self.path.resolve())
        captured.open(force=True, prompt=False)
        self.assertTrue(captured.is_current())
        self.assertEqual(hlib.scene().path(), self.path.resolve())
        with self.assertRaises(ValueError):
            hlib.scene("")



if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
