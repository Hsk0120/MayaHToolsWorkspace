"""肘膝補正の数値・無効化・保存と所有権を検証する。"""

import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from maya import cmds
from maya.api import OpenMaya as om

from hrig import build_limb
from hrig.limb import LimbRig


class BendTest(unittest.TestCase):
    """プラグインをロードせず、標準DGの結果を照合する。"""

    def setUp(self):
        """隔離シーンと基準姿勢の部位を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        patcher = mock.patch.object(cmds, "loadPlugin", side_effect=AssertionError("Plugin load"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.rig = build_limb()

    def test_half_rotation_and_signed_offsets(self):
        """90度曲げで45度追従し、内外の距離を独立して変更する。"""
        half, inner, outer = self.rig.add_bend()
        self.assertEqual(cmds.listRelatives(inner, parent=True, fullPath=True), [half])
        for angle, fraction in ((0, 0), (45, 0.5), (90, 1), (120, 1), (-60, 0)):
            cmds.setAttr(self.rig.controls()["fk1"] + ".rz", angle)
            matrix = om.MMatrix(cmds.getAttr(half + ".offsetParentMatrix"))
            rotation = om.MTransformationMatrix(matrix).rotation()
            self.assertAlmostEqual(math.degrees(rotation.z), angle * 0.5, places=4)
            self.assertAlmostEqual(matrix[12], 5, places=5)
            self.assertAlmostEqual(cmds.getAttr(inner + ".ty"), 0.5 - 0.2 * fraction, places=5)
            self.assertAlmostEqual(cmds.getAttr(outer + ".ty"), -0.5 - 0.2 * fraction, places=5)
        settings = self.rig.bend_settings()
        settings.plug("bendSign").set(-1)
        settings.plug("innerPush").set(0.3)
        settings.plug("outerPush").set(0.1)
        cmds.setAttr(self.rig.controls()["fk1"] + ".rz", -90)
        self.assertAlmostEqual(cmds.getAttr(inner + ".ty"), 0.8, places=5)
        self.assertAlmostEqual(cmds.getAttr(outer + ".ty"), -0.4, places=5)

    def test_lod_undo_save_and_delete(self):
        """出力を切断し、Undo・保存読込・再有効化で接続を維持する。"""
        from hrig.channel_controls import apply

        half, inner, outer = self.rig.add_bend()
        cmds.setAttr(self.rig.controls()["fk1"] + ".rz", 90)
        channel = self.rig._member("channel_bend")
        cmds.setAttr(channel + ".enabled", False)
        apply(self.rig)
        for joint, attr in ((half, "offsetParentMatrix"), (inner, "ty"), (outer, "ty")):
            self.assertFalse(cmds.connectionInfo(joint + "." + attr, isDestination=True))
        self.assertAlmostEqual(cmds.getAttr(inner + ".ty"), 0.5)
        cmds.undo()
        self.assertTrue(cmds.connectionInfo(half + ".offsetParentMatrix", isDestination=True))
        self.rig.set_layer_enabled("bend", True)
        before = cmds.connectionInfo(inner + ".ty", sourceFromDestination=True)
        for _ in range(3):
            self.rig.set_lod(0)
            self.rig.set_lod(1)
        self.assertEqual(cmds.connectionInfo(inner + ".ty", sourceFromDestination=True), before)
        with tempfile.TemporaryDirectory() as directory:
            file = str(Path(directory) / "bend.ma")
            cmds.file(rename=file)
            cmds.file(save=True, type="mayaAscii")
            cmds.file(file, open=True, force=True)
        rig = LimbRig("limb")
        self.assertEqual(len(rig.bend_joints()), 3)
        rig.set_mode("ik")
        self.assertTrue(cmds.getAttr(rig._member("channel_bend") + ".active"))
        rig.delete()
        self.assertFalse(cmds.ls("*bend_layer*"))

    def test_invalid_and_undo_creation(self):
        """不正軸・重複・作成Undoを検証する。"""
        before = set(cmds.ls())
        with self.assertRaises(ValueError):
            self.rig.add_bend(bend_axis="y", push_axis="y")
        self.assertEqual(before, set(cmds.ls()))
        self.rig.add_bend()
        cmds.undo()
        self.assertEqual(self.rig.bend_joints(), ())
        cmds.redo()
        self.assertEqual(len(self.rig.bend_joints()), 3)
        with self.assertRaises(ValueError):
            self.rig.add_bend()

    def test_demo_skin(self):
        """デモの高詳細へ補助3骨を追加し、proxyは3骨のままにする。"""
        from hrig.examples.limb_demo import build_demo

        cmds.file(new=True, force=True)
        demo = build_demo()
        self.assertEqual(len(demo["rig"].bend_joints()), 3)
        owner = demo["rig"].bend_settings().plug("graph").sourceWithConversion().node()
        self.assertGreater(owner.plug("response").get(), 0.5)
        self.assertEqual(len(cmds.skinCluster(demo["high_skin"], q=True, influence=True)), 13)
        self.assertEqual(len(cmds.skinCluster(demo["proxy_skin"], q=True, influence=True)), 3)

    def test_parent_transform_and_unit_change(self):
        """親の変形を継承し、単位変更後もLODの基準位置を維持する。"""
        half, inner, outer = self.rig.add_bend()
        cmds.setAttr(self.rig.controls()["fk1"] + ".rz", 90)
        root = self.rig.root.fullName()
        cmds.setAttr(root + ".translate", 2, 3, 4)
        cmds.setAttr(root + ".rotate", 10, 20, 30)
        cmds.setAttr(root + ".scale", 2, 2, 2)
        anchor = cmds.xform(self.rig.joints()[1], query=True, worldSpace=True, translation=True)
        position = cmds.xform(half, query=True, worldSpace=True, translation=True)
        for expected, actual in zip(anchor, position):
            self.assertAlmostEqual(actual, expected, places=5)
        cmds.currentUnit(linear="m")
        try:
            self.rig.set_lod(0)
            self.assertAlmostEqual(cmds.getAttr(inner + ".ty"), 0.005, places=6)
            self.rig.set_lod(1)
            self.assertAlmostEqual(cmds.getAttr(inner + ".ty"), 0.003, places=6)
        finally:
            cmds.currentUnit(linear="cm")
