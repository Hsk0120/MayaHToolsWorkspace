"""mlib Scene file APIを検証するMaya内テスト。"""

import sys
import tempfile
import unittest
from pathlib import Path

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common.scene import Scene
from mlib.common import Scene as SceneFromPackage


class SceneApiTest(unittest.TestCase):
    """現在シーンの参照とファイル操作を検証する。"""

    def setUp(self):
        self.scene = Scene()
        self.path = Path(tempfile.gettempdir()) / "mlib_scene_api.ma"
        self.import_path = Path(tempfile.gettempdir()) / "mlib_scene_api_import_source.ma"
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
        self.assertIsNone(self.scene.path)
        self.assertIsNone(self.scene.name)
        self.assertTrue(self.scene.isNew())
        self.assertFalse(self.scene.isModified())

    def test_save_open_and_new(self):
        cmds.createNode("transform", name="mlibSceneApiNode")
        self.assertTrue(self.scene.isModified())

        result = self.scene.saveAs(self.path)
        self.assertIs(result, self.scene)
        self.assertEqual(self.scene.path, self.path)
        self.assertEqual(self.scene.name, self.path.name)
        self.assertEqual(self.scene.getFileType(), "mayaAscii")
        self.assertFalse(self.scene.isModified())

        self.scene.open(self.path, force=True, prompt=False)
        self.assertEqual(self.scene.path, self.path)
        self.scene.new(force=True, prompt=False)
        self.assertTrue(self.scene.isNew())

    def test_invalid_save_as_extension(self):
        with self.assertRaises(ValueError):
            self.scene.saveAs(self.path.with_suffix(".txt"))

    def test_import_file_brings_in_nodes_under_namespace(self):
        cmds.createNode("transform", name="mlibImportSourceNode")
        self.scene.saveAs(self.import_path)
        self.scene.new(force=True, prompt=False)
        cmds.createNode("transform", name="mlibSceneApiNode")

        new_nodes = self.scene.importFile(self.import_path, namespace="mlibImportedNs")
        imported_names = [node.getName() for node in new_nodes]
        self.assertTrue(any(name.endswith("mlibImportSourceNode") for name in imported_names))
        self.assertTrue(cmds.objExists("mlibImportedNs:mlibImportSourceNode"))
        self.assertTrue(cmds.objExists("mlibSceneApiNode"))

    def test_import_file_requires_current_scene(self):
        cmds.createNode("transform", name="mlibImportSourceNode")
        self.scene.saveAs(self.import_path)
        self.scene.new(force=True, prompt=False)

        stale = Scene(self.import_path)
        with self.assertRaises(RuntimeError):
            stale.importFile(self.import_path)

    def test_scene_command_snapshots_without_opening(self):
        self.assertIs(mlib.getScene, mlib.cmds.getScene)
        self.assertEqual(str(mlib.getScene()), "untitled")
        other = mlib.getScene(self.path)
        self.assertEqual(other.path, self.path.resolve())
        self.assertEqual(str(other), str(self.path.resolve()))
        self.assertTrue(self.scene.isNew())
        self.assertFalse(other.isCurrent())
        with self.assertRaises(RuntimeError):
            other.save()
        with self.assertRaises(RuntimeError):
            other.isModified()
        self.scene.saveAs(self.path)
        captured = mlib.getScene()
        self.scene.new(force=True, prompt=False)
        self.assertEqual(captured.path, self.path.resolve())
        captured.open(force=True, prompt=False)
        self.assertTrue(captured.isCurrent())
        self.assertEqual(mlib.getScene().path, self.path.resolve())
        with self.assertRaises(ValueError):
            mlib.getScene("")



if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
