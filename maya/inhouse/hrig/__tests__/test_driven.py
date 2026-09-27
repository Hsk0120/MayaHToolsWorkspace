"""分解SDKとUI用サンプル生成の統合を検証する。"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from maya import cmds

import hlib
from hrig.sampleBuilder import SampleBuilder
from hrig.drivenLayer import DrivenLayer
from hrig.limb import LimbRig


class DrivenTest(unittest.TestCase):
    """SDKの角度、LOD、Undo、保存参照を検証する。"""

    def setUp(self):
        """プラグインを禁止し、サンプル部位を作る。"""
        cmds.file(new=True, force=True)
        patcher = mock.patch.object(cmds, "loadPlugin", side_effect=AssertionError("Plugin load"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.rig = SampleBuilder.module("sample")

    def test_sample_and_sdk_lod(self):
        """SwingZ→SDK→移動を評価し、LOD/Enabled/Undoを確認する。"""
        target = SampleBuilder.layer(self.rig, "driven", component="swingZ")
        graph = hlib.node(target)
        bone = graph.plug("drivenNode").source().node
        for angle in (-90, -45, 0, 45, 90):
            cmds.setAttr(self.rig.controls()["fk1"] + ".rz", angle)
            self.assertAlmostEqual(bone.plug("ty").get(), angle / 90, places=4)
        self.rig.set_layer_enabled("driven", False)
        self.assertIsNone(bone.plug("ty").source())
        self.assertEqual(bone.plug("ty").get(), 0)
        cmds.undo()
        self.assertAlmostEqual(bone.plug("ty").get(), 1, places=4)
        self.rig.set_lod(0)
        self.assertIsNone(bone.plug("ty").source())
        self.rig.set_lod(1)
        self.assertAlmostEqual(bone.plug("ty").get(), 1, places=4)

    def test_save_and_external_destination(self):
        """外部の回転属性を駆動し、改名・保存後も対象を維持する。"""
        external = cmds.createNode("transform", name="external")
        graph = self.rig.add_driven(
            "rotate", self.rig.joints()[1], external + ".rz", keys=[(-90, -30), (0, 0), (90, 30)]
        )
        cmds.setAttr(self.rig.controls()["fk1"] + ".rx", 45)
        self.assertAlmostEqual(cmds.getAttr(external + ".rz"), 15, places=4)
        cmds.rename(external, "renamed")
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "sdk.ma")
            cmds.file(rename=path)
            cmds.file(save=True, type="mayaAscii")
            cmds.file(path, open=True, force=True)
        rig = LimbRig("sample")
        self.assertEqual(len(DrivenLayer(rig).graphs()), 1)
        rig.set_layer_enabled("driven", False)
        self.assertEqual(cmds.getAttr("renamed.rz"), 0)
        rig.set_layer_enabled("driven", True)
        self.assertAlmostEqual(cmds.getAttr("renamed.rz"), 15, places=4)
        rig.delete()
        self.assertTrue(cmds.objExists("renamed"))
        self.assertFalse(cmds.ls("*driven_layer*"))

    def test_creation_undo_and_rejection(self):
        """生成を一回のUndoで戻し、入力側への逆接続を拒否する。"""
        before = set(cmds.ls())
        SampleBuilder.layer(self.rig, "driven")
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertEqual(len(DrivenLayer(self.rig).graphs()), 1)
        with self.assertRaises(ValueError):
            self.rig.add_driven("bad", self.rig.joints()[1], self.rig.controls()["fk1"] + ".rx")

    def test_multiple_modules_and_layers(self):
        """二つの部位と各サンプルを作成し、部位間の状態を独立に保つ。"""
        other = SampleBuilder.module("second")
        for kind in ("twist", "bend", "driven", "foot", "soft", "helper"):
            SampleBuilder.layer(self.rig, kind)
        self.assertEqual(len(self.rig.twist_joints()), 3)
        self.assertEqual(len(self.rig.bend_joints()), 3)
        self.assertEqual(other.twist_joints(), ())
        self.rig.set_lod(0)
        self.assertEqual(other.lod(), 1)
