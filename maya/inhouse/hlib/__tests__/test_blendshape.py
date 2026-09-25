"""hlib.nodes.blendShape の BlendShape ラッパーを検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.nodes import Node
from hlib.nodes.blendShape import BlendShape


class BlendShapeTest(unittest.TestCase):
    """ターゲット列挙・ウェイト取得・ターゲット追加を検証する。"""

    def setUp(self):
        self.created = []
        self.base = cmds.polyCube(name="hlibBlendShapeBase", constructionHistory=False)[0]
        self.target1 = cmds.polyCube(name="hlibBlendShapeTarget1", constructionHistory=False)[0]
        self.target2 = cmds.polyCube(name="hlibBlendShapeTarget2", constructionHistory=False)[0]
        cmds.move(1, 0, 0, self.target1 + ".vtx[0]")
        cmds.move(0, 2, 0, self.target2 + ".vtx[0]")
        self.created.extend([self.base, self.target1, self.target2])
        bs_name = cmds.blendShape(self.target1, self.target2, self.base, name="hlibBlendShape")[0]
        self.created.append(bs_name)
        self.bs = Node(bs_name)

    def tearDown(self):
        for node in reversed(self.created):
            if cmds.objExists(node):
                cmds.delete(node)

    def test_node_resolves_to_blend_shape_wrapper(self):
        self.assertIsInstance(self.bs, BlendShape)

    def test_targets_and_weights(self):
        self.assertEqual(self.bs.targets(), [self.target1, self.target2])
        self.assertEqual(self.bs.weights(), [0.0, 0.0])
        self.assertEqual(len(self.bs.weight_plugs()), 2)

        self.bs.weight_plugs()[0].set(0.5)
        self.assertEqual(self.bs.weights(), [0.5, 0.0])

    def test_add_target_creates_new_weight_element(self):
        target3 = cmds.polyCube(name="hlibBlendShapeTarget3", constructionHistory=False)[0]
        self.created.append(target3)
        cmds.move(0, 0, 3, target3 + ".vtx[0]")

        weight_plug = self.bs.add_target(target3)
        # weight[2] は自動的に target3 の名前でエイリアスされるため、
        # full_name はロング名ではなくエイリアス名で表示される。
        self.assertEqual(weight_plug.full_name(), self.bs.full_name() + "." + target3)
        self.assertEqual(self.bs.targets(), [self.target1, self.target2, target3])

        weight_plug.set(1.0)
        self.assertEqual(self.bs.weights(), [0.0, 0.0, 1.0])

    def test_add_target_accepts_explicit_weight_index(self):
        target3 = cmds.polyCube(name="hlibBlendShapeTarget3", constructionHistory=False)[0]
        self.created.append(target3)
        cmds.move(0, 0, 3, target3 + ".vtx[0]")

        weight_plug = self.bs.add_target(target3, weight_index=5)
        self.assertEqual(weight_plug.full_name(), self.bs.full_name() + "." + target3)
        self.assertEqual(weight_plug.attribute(), "weight")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
