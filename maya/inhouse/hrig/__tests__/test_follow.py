"""腕脚・スカートの追従レイヤーを隔離Mayaで検証する。"""

from pathlib import Path
import tempfile
import math
import unittest
from unittest import mock

from maya import cmds
from maya.api import OpenMaya as om

import hlib
from hrig import build_skirt
from hrig.limb import LimbRig
from hrig.skirtRig import SkirtRig
from hrig.sampleBuilder import SampleBuilder


class FollowTest(unittest.TestCase):
    """補助骨・割合・Enabled/LOD・永続参照を確認する。"""

    def setUp(self):
        """独立シーンでプラグイン依存を禁止する。"""
        cmds.file(new=True, force=True)
        patcher = mock.patch.object(cmds, "loadPlugin", side_effect=AssertionError("Plugin load"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def rotation(self, bone):
        """OPM出力から度単位のXYZ回転を取得する。"""
        matrix = om.MMatrix(cmds.getAttr(bone + ".offsetParentMatrix"))
        euler = om.MTransformationMatrix(matrix).rotation()
        return [om.MAngle(a).asDegrees() for a in (euler.x, euler.y, euler.z)]

    def test_limb_sample_and_lod(self):
        """3種類のサンプルと割合を変更し、Undo/LODを検証する。"""
        rig = SampleBuilder.module("limb")
        for kind in ("followTwist", "followSwing", "followHalf"):
            SampleBuilder.layer(rig, kind, axis="x", ratio=0.5)
        self.assertEqual(len(rig.follow_joints()), 3)
        cmds.setAttr(rig.controls()["fk1"] + ".rx", 60)
        twist, swing, half = rig.follow_joints()
        for bone, expected in ((twist, 30), (swing, 0), (half, 30)):
            self.assertAlmostEqual(self.rotation(bone)[0], expected, places=4)
        rig.follow_settings("followHalf1").plug("ratio").set(0.25)
        self.assertAlmostEqual(self.rotation(half)[0], 15, places=4)
        rig.set_layer_enabled("follow", False)
        self.assertIsNone(hlib.getPlug(half + ".offsetParentMatrix").sourceWithConversion())
        cmds.undo()
        self.assertAlmostEqual(self.rotation(half)[0], 15, places=4)
        rig.set_lod(0)
        self.assertIsNone(hlib.getPlug(half + ".offsetParentMatrix").sourceWithConversion())
        rig.set_lod(1)
        self.assertAlmostEqual(self.rotation(half)[0], 15, places=4)
        self.assertIn(half, rig.joints())

    def test_skirt_save_and_delete(self):
        """スカートのドライバー入力と保存後の参照・削除を確認する。"""
        rig = build_skirt(chain_count=4)
        bone = rig.add_follow("driverHalf", ratio=0.5)
        rig.driver_chains()[0][0].plug("rotateY").set(math.radians(80))
        self.assertAlmostEqual(self.rotation(bone)[1], 40, places=4)
        rig.root.rename("renamed")
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "follow.ma")
            cmds.file(rename=path)
            cmds.file(save=True, type="mayaAscii")
            cmds.file(path, open=True, force=True, executeScriptNodes=False)
        rig = SkirtRig("renamed")
        bone = rig.follow_joints()[0]
        rig.set_lod(0)
        self.assertIsNone(hlib.getPlug(bone + ".offsetParentMatrix").sourceWithConversion())
        rig.set_lod(1)
        self.assertAlmostEqual(self.rotation(bone)[1], 40, places=4)
        rig.delete()
        self.assertFalse(cmds.ls("skirt01*"))

    def test_ownership_and_creation_undo(self):
        """外部骨への後付けを拒否し、作成全体をUndoする。"""
        rig = SampleBuilder.module("limb")
        external = cmds.createNode("joint", name="external")
        with self.assertRaises(ValueError):
            rig.add_follow("external", external)
        rig.add_follow("half")
        cmds.undo()
        self.assertFalse(rig.follow_joints())
        cmds.redo()
        self.assertEqual(len(rig.follow_joints()), 1)
        rig.delete()
        self.assertTrue(cmds.objExists(external))
        self.assertFalse(cmds.ls("limb_follow*"))
