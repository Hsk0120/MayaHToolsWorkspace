"""ツイスト行列分配と行列属性の直接設定を実Mayaで検証する。"""
from hlib.maths import MSpace

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

import hlib


class TwistDistributionTest(unittest.TestCase):
    """hlib単独のグラフと属性更新を確認する。"""

    def setUp(self):
        """空シーンを用意する。"""
        cmds.file(new=True, force=True)

    def test_matrix_value_does_not_modify_channels(self):
        """動的行列とOPMへの直接設定でTRSを変えずUndoも成立する。"""
        from hlib.maths import Matrix

        node = hlib.createNode("joint", name="joint", skipSelect=True)
        node.plug("translateX").set(2)
        plug = node.addAttr(longName="rest", dataType="matrix")
        value = Matrix()
        value[12] = 3
        plug.set(value)
        self.assertAlmostEqual(plug.get()[12], 3)
        self.assertEqual(cmds.getAttr("joint.tx"), 2)
        node.plug("offsetParentMatrix").set(value)
        self.assertEqual(cmds.getAttr("joint.tx"), 2)
        self.assertAlmostEqual(node.getTranslation(ws=True, at=4)[0], 5)
        cmds.undo()
        self.assertAlmostEqual(node.getTranslation(ws=True, at=4)[0], 2)

    def test_fraction_and_ownership(self):
        """親子でない二つの姿勢も始点空間で補間し、外部参照を削除しない。"""
        from hrig.setups import TwistDistribution

        start = hlib.createNode("transform", name="start", skipSelect=True)
        end = hlib.createNode("transform", name="end", skipSelect=True)
        start.setTranslation((1, 0, 0), at=4)
        end.setTranslation((9, 0, 0), at=4)
        end.plug("rotateX").set(math.radians(120))
        graph = TwistDistribution.create(start, end)
        output = graph.sample(0.25, "quarter")
        matrix = om.MMatrix(output.get())
        self.assertAlmostEqual(matrix[12], 2, places=5)
        quaternion = om.MTransformationMatrix(matrix).rotation(asQuaternion=True)
        self.assertAlmostEqual(
            math.degrees(2 * math.atan2(quaternion.x, quaternion.w)), 30, places=4
        )
        owned = cmds.container(graph.container.fullName(), query=True, nodeList=True)
        hlib.delete(graph.container)
        self.assertTrue(start.isValid() and end.isValid())
        self.assertFalse(any(cmds.objExists(n) for n in owned))

    def test_invalid_fraction(self):
        """範囲外の補間率は生成物を増やさない。"""
        from hrig.setups import TwistDistribution

        a = hlib.createNode("transform", name="a", skipSelect=True)
        b = hlib.createNode("transform", name="b", skipSelect=True)
        graph = TwistDistribution.create(a, b)
        before = set(cmds.ls())
        with self.assertRaises(ValueError):
            graph.sample(1.1, "bad")
        self.assertEqual(set(cmds.ls()), before)
