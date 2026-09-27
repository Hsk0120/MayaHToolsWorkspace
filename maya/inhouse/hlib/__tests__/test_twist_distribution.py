"""ツイスト行列分配と行列属性の直接設定を実Mayaで検証する。"""

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
        plug = node.add_attr(long_name="rest", data_type="matrix")
        value = Matrix()
        value[12] = 3
        plug.set_value(value)
        self.assertAlmostEqual(plug.get()[12], 3)
        self.assertEqual(cmds.getAttr("joint.tx"), 2)
        node.plug("offsetParentMatrix").set_value(value)
        self.assertEqual(cmds.getAttr("joint.tx"), 2)
        self.assertAlmostEqual(node.get_translate(ws=True)[0], 5)
        cmds.undo()
        self.assertAlmostEqual(node.get_translate(ws=True)[0], 2)

    def test_fraction_and_ownership(self):
        """親子でない二つの姿勢も始点空間で補間し、外部参照を削除しない。"""
        from hlib.animation import TwistDistribution

        start = hlib.createNode("transform", name="start", skipSelect=True)
        end = hlib.createNode("transform", name="end", skipSelect=True)
        start.set_translate((1, 0, 0))
        end.set_translate((9, 0, 0))
        end.plug("rotateX").set(120)
        graph = TwistDistribution.create(start, end)
        output = graph.sample(0.25, "quarter")
        matrix = om.MMatrix(output.get())
        self.assertAlmostEqual(matrix[12], 2, places=5)
        quaternion = om.MTransformationMatrix(matrix).rotation(asQuaternion=True)
        self.assertAlmostEqual(
            math.degrees(2 * math.atan2(quaternion.x, quaternion.w)), 30, places=4
        )
        owned = cmds.container(graph.container.full_name(), query=True, nodeList=True)
        hlib.delete(graph.container)
        self.assertTrue(start.is_valid() and end.is_valid())
        self.assertFalse(any(cmds.objExists(n) for n in owned))

    def test_invalid_fraction(self):
        """範囲外の補間率は生成物を増やさない。"""
        from hlib.animation import TwistDistribution

        a = hlib.createNode("transform", name="a", skipSelect=True)
        b = hlib.createNode("transform", name="b", skipSelect=True)
        graph = TwistDistribution.create(a, b)
        before = set(cmds.ls())
        with self.assertRaises(ValueError):
            graph.sample(1.1, "bad")
        self.assertEqual(set(cmds.ls()), before)
