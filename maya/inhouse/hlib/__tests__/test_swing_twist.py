"""Swing/Twistの数値分解、基準姿勢、所有権を検証する。"""

import unittest

from maya import cmds
from maya.api import OpenMaya as om

from hlib.animation import SwingTwist


class SwingTwistTest(unittest.TestCase):
    """標準ノードの実評価結果を比較する。"""

    def setUp(self):
        """親とjointを持つ空シーンを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg")
        self.parent = cmds.createNode("transform")
        self.joint = cmds.createNode("joint", parent=self.parent)

    def test_axes_and_swing(self):
        """全軸の正負Twistと、Twistを除いたSwingを取得する。"""
        for axis in "xyz":
            cmds.setAttr(self.joint + ".rotate", 0, 0, 0)
            graph = SwingTwist.create(self.joint, name="decompose" + axis, axis=axis)
            for angle in (-150, -60, 0, 60, 150):
                cmds.setAttr(self.joint + ".r" + axis, angle)
                self.assertAlmostEqual(graph.container.plug("twist").get(), angle, delta=0.001)
                for component in "XYZ":
                    self.assertAlmostEqual(
                        graph.container.plug("swing" + component).get(), 0, places=4
                    )
            cmds.delete(graph.container.full_name())
        cmds.setAttr(self.joint + ".rotate", 0, 0, 0)
        graph = SwingTwist.create(self.joint)
        cmds.setAttr(self.joint + ".rz", 50)
        self.assertAlmostEqual(graph.container.plug("swingZ").get(), 50, places=4)
        self.assertAlmostEqual(graph.container.plug("twist").get(), 0, places=4)

    def test_reconstruct_rest_and_singular(self):
        """複合回転を再構築し、180度の不定Twistを安全に処理する。"""
        cmds.setAttr(self.joint + ".jointOrient", 10, 20, 30)
        graph = SwingTwist.create(self.joint)
        baseline = om.MMatrix(cmds.getAttr(self.joint + ".matrix"))
        self.assertAlmostEqual(graph.container.plug("twist").get(), 0, places=4)
        for rotation in ((40, 30, 20), (-35, 50, -40)):
            cmds.setAttr(self.joint + ".rotate", *rotation)
            matrix = om.MMatrix(cmds.getAttr(self.joint + ".matrix")) * baseline.inverse()
            twist = om.MMatrix(graph.container.plug("twistMatrix").get())
            swing = om.MMatrix(graph.container.plug("swingMatrix").get())
            for actual, expected in zip(twist * swing, matrix):
                self.assertAlmostEqual(actual, expected, places=5)
        cmds.currentUnit(angle="rad")
        value = graph.container.plug("twist").get()
        cmds.currentUnit(angle="deg")
        self.assertAlmostEqual(graph.container.plug("twist").get(), value, places=5)
        cmds.delete(graph.container.full_name())
        cmds.setAttr(self.joint + ".jointOrient", 0, 0, 0)
        cmds.setAttr(self.joint + ".rotate", 0, 0, 0)
        graph = SwingTwist.create(self.joint)
        cmds.setAttr(self.joint + ".ry", 180)
        self.assertAlmostEqual(graph.container.plug("twist").get(), 0, places=4)
