"""回転成分と割合を、Quaternionの期待値で検証する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from hrig.setups import RotationFollow


class RotationFollowTest(unittest.TestCase):
    """標準ノードの数値評価と基準姿勢を確認する。"""

    def setUp(self):
        """親付き入力jointを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.parent = cmds.createNode("transform")
        self.joint = cmds.createNode("joint", parent=self.parent)

    def assertMatrix(self, actual, expected):
        """行列を誤差付きで比較する。"""
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, places=5)

    def test_components_and_ratios(self):
        """XYZのTwist抽出・除去と0/半分/全追従を検証する。"""
        for axis in "xyz":
            cmds.setAttr(self.joint + ".rotate", 0, 0, 0)
            graph = RotationFollow.create(self.joint, name="follow" + axis, axis=axis).container
            for degrees in (-120, 80):
                cmds.setAttr(self.joint + ".r" + axis, degrees)
                for mode in (0, 1, 2):
                    graph.getPlug("followMode").set(mode)
                    for ratio in (0, 0.25, 0.5, 1):
                        graph.getPlug("ratio").set(ratio)
                        angle = math.radians(degrees * ratio) if mode != 2 else 0
                        vector = om.MVector(*[int(a == axis) for a in "xyz"])
                        expected = om.MQuaternion(angle, vector).asMatrix()
                        self.assertMatrix(graph.getPlug("matrix").get(), expected)
            cmds.delete(graph.getFullName())

    def test_combined_rotation_and_rest(self):
        """JointOrient/OPM/移動を含む基準姿勢と複合回転を確認する。"""
        cmds.setAttr(self.joint + ".jointOrient", 10, 20, 30)
        cmds.setAttr(self.joint + ".translate", 5, 2, -1)
        opm = om.MEulerRotation(0.1, -0.2, 0.3).asMatrix()
        cmds.setAttr(self.joint + ".offsetParentMatrix", *opm, type="matrix")
        graph = RotationFollow.create(self.joint, ratio=1).container
        rest = om.MMatrix(cmds.getAttr(self.joint + ".matrix")) * opm
        self.assertMatrix(graph.getPlug("matrix").get(), rest)
        rest_rotation = om.MTransformationMatrix(rest).rotation(asQuaternion=True).asMatrix()
        for rotation in ((35, 50, -20), (-70, 10, 45)):
            cmds.setAttr(self.joint + ".rotate", *rotation)
            current = om.MMatrix(cmds.getAttr(self.joint + ".matrix")) * opm
            self.assertMatrix(graph.getPlug("matrix").get(), current)
            for mode, component in ((1, "twistMatrix"), (2, "swingMatrix")):
                graph.getPlug("followMode").set(mode)
                graph.getPlug("ratio").set(0.5)
                q = om.MTransformationMatrix(om.MMatrix(graph.getPlug(component).get())).rotation(
                    asQuaternion=True
                )
                expected = om.MTransformationMatrix(
                    om.MQuaternion.slerp(om.MQuaternion(), q, 0.5).asMatrix() * rest_rotation
                )
                expected.setTranslation(
                    om.MTransformationMatrix(current).translation(om.MSpace.kTransform),
                    om.MSpace.kTransform,
                )
                self.assertMatrix(graph.getPlug("matrix").get(), expected.asMatrix())
            graph.getPlug("followMode").set(0)
            graph.getPlug("ratio").set(1)
        cmds.currentUnit(angle="rad", linear="m")
        self.assertMatrix(graph.getPlug("matrix").get(), current)
        cmds.currentUnit(angle="deg", linear="cm")

    def test_invalid_ratio_and_singular(self):
        """無効値を拒否し、180度Swingでも有限行列を返す。"""
        for ratio in (-1, 2, float("nan")):
            with self.assertRaises(ValueError):
                RotationFollow.create(self.joint, ratio=ratio)
        graph = RotationFollow.create(self.joint).container
        cmds.setAttr(self.joint + ".ry", 180)
        for mode in range(3):
            graph.getPlug("followMode").set(mode)
            self.assertTrue(all(math.isfinite(v) for v in graph.getPlug("matrix").get()))
