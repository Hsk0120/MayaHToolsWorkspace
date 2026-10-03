"""標準ノードによる曲げ補正の軸、単位、基準姿勢を検証する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from hrig.setups import BendCorrection


class BendCorrectionTest(unittest.TestCase):
    """Maya 2022以降で共通の数値出力を照合する。"""

    def setUp(self):
        """空シーンを標準の単位に戻す。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")

    def tearDown(self):
        """後続テストへ単位変更を持ち越さない。"""
        cmds.currentUnit(angle="deg", linear="cm")

    def test_axes_rest_and_units(self):
        """XYZ各軸で基準からの45度曲げと補間を検証する。"""
        for axis in "xyz":
            parent = cmds.createNode("transform")
            joint = cmds.createNode("joint", parent=parent)
            cmds.setAttr(joint + ".tx", 5)
            cmds.setAttr(joint + ".r" + axis, 20)
            graph = BendCorrection.create(parent, joint, name="bend" + axis, axis=axis)
            cmds.setAttr(joint + ".r" + axis, 65)
            cmds.setAttr(joint + ".tx", 8)
            owner = graph.container
            self.assertAlmostEqual(owner.plug("response").get(), 0.5, places=5)
            matrix = om.MMatrix(owner.plug("matrix").get())
            self.assertAlmostEqual(matrix[12], 8, places=5)
            rotation = om.MTransformationMatrix(matrix).rotation()
            self.assertAlmostEqual(math.degrees(getattr(rotation, axis)), 42.5, places=4)
            self.assertAlmostEqual(owner.plug("inner").get(), 0.4, places=5)
            cmds.currentUnit(angle="rad")
            self.assertAlmostEqual(owner.plug("response").get(), 0.5, places=5)
            cmds.currentUnit(angle="deg")
            owner.plug("rotationRatio").set(0)
            matrix = om.MMatrix(owner.plug("matrix").get())
            self.assertAlmostEqual(
                math.degrees(getattr(om.MTransformationMatrix(matrix).rotation(), axis)),
                20,
                places=4,
            )
            for delta, expected in ((120, 1), (-120, 0), (90, 1)):
                cmds.setAttr(joint + ".r" + axis, 20 + delta)
                self.assertAlmostEqual(owner.plug("response").get(), expected, places=5)

    def test_meter_scene_and_ownership(self):
        """メートル設定で距離を維持し、変換ノードをcontainerで所有する。"""
        cmds.currentUnit(linear="m")
        parent = cmds.createNode("transform")
        joint = cmds.createNode("joint", parent=parent)
        before = set(cmds.ls())
        graph = BendCorrection.create(parent, joint)
        cmds.setAttr(joint + ".rz", 90)
        self.assertAlmostEqual(graph.container.plug("inner").get(), 30, places=5)
        cmds.currentUnit(linear="cm")
        self.assertAlmostEqual(graph.container.plug("inner").get(), 30, places=4)
        graph.container.plug("innerPush").set(-10)
        self.assertAlmostEqual(graph.container.plug("inner").get(), 40, places=4)
        created = set(cmds.ls()) - before
        cmds.delete(graph.container.fullName())
        self.assertFalse(created.intersection(cmds.ls()))

    def test_bad_parent_does_not_edit_scene(self):
        """親子でない参照と無効な軸を変更なしで拒否する。"""
        parent = cmds.createNode("transform")
        joint = cmds.createNode("joint")
        before = set(cmds.ls())
        with self.assertRaises(ValueError):
            BendCorrection.create(parent, joint)
        with self.assertRaises(ValueError):
            BendCorrection.create(parent, joint, axis="bad")
        self.assertEqual(set(cmds.ls()), before)
