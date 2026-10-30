"""参照再利用の最適化で公開APIの意味を維持する。"""
import sys
import unittest

import maya.cmds as cmds
import mlib

mlib.reload()


class BulkPerformanceContractsTest(unittest.TestCase):
    """更新順・寿命の変化を実Mayaで確認する。"""

    def setUp(self):
        """検証専用のシーンを作る。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg")

    def test_plug_lookup_follows_alias_rename_delete_undo(self):
        """function set再利用後もノードや動的アトリビュートの変化に追従する。"""
        node = mlib.getNode(cmds.createNode("transform"))
        cmds.addAttr(node.getFullName(), ln="amount", at="double")
        node.getPlug("amount").set(3)
        cmds.aliasAttr("aliasAmount", node.getFullName() + ".amount")
        self.assertEqual(node.getPlug("aliasAmount").get(), 3)
        cmds.rename(node.getFullName(), "renamed")
        cmds.deleteAttr(node.getFullName() + ".amount")
        with self.assertRaises(AttributeError):
            node.getPlug("amount")
        cmds.undo()
        self.assertEqual(node.getPlug("amount").get(), 3)
        cmds.deleteAttr(node.getFullName() + ".amount")
        cmds.addAttr(node.getFullName(), ln="amount", at="long", dv=7)
        self.assertEqual(node.getPlug("amount").get(), 7)

    def test_fast_matrix_matches_normal_with_units_and_joint(self):
        """直接MPlug更新でも単位とJoint補正を通常経路に合わせる。"""
        for kind in ("transform", "joint"):
            node = mlib.getNode(cmds.createNode(kind))
            if kind == "joint":
                cmds.setAttr(node.getFullName() + ".jointOrient", 11, 23, 7)
            for linear, angle in (("cm", "deg"), ("m", "rad")):
                cmds.currentUnit(linear=linear, angle=angle)
                target = mlib.maths.Matrix(translate=(2, 3, 4))
                node.setMatrix(target)
                expected = list(node.getMatrix())
                node.setTranslate((0, 0, 0), at=4)
                node.setMatrix(target, fast=True)
                for a, b in zip(node.getMatrix(), expected):
                    self.assertAlmostEqual(a, b, places=7)

    def test_weight_order_holes_duplicate_and_partial_failure(self):
        """検索表を再構築し、欠番・入力順・未指定値・失敗時の更新順を保つ。"""
        joints = [cmds.createNode("joint") for _ in range(4)]
        mesh = cmds.polyCube(ch=False)[0]
        skin = mlib.getNode(cmds.skinCluster(joints, mesh, tsb=True)[0])
        cmds.skinCluster(skin.getFullName(), e=True, ri=joints[1])
        skin.setWeights([joints[3], joints[0]], [.2, .3], broadcast=True)
        values = list(skin.getWeights([joints[0], joints[3]]))
        self.assertAlmostEqual(values[0], .3)
        self.assertAlmostEqual(values[1], .2)
        with self.assertRaises(ValueError):
            skin.setWeights([joints[0], cmds.ls(joints[0], long=True)[0]], [.1, .2], broadcast=True)
        prefix = skin.getFullName() + ".weightList[0].weights"
        before = cmds.getAttr(prefix + "[0]")
        protected = cmds.getAttr(prefix + "[2]")
        cmds.setAttr(prefix + "[2]", lock=True)
        with self.assertRaises(RuntimeError):
            skin.setWeights([joints[0], joints[2]], [.4, .6], broadcast=True)
        self.assertAlmostEqual(cmds.getAttr(prefix + "[0]"), .4)
        self.assertEqual(cmds.getAttr(prefix + "[2]"), protected)
        cmds.undo()
        self.assertAlmostEqual(cmds.getAttr(prefix + "[0]"), before)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
