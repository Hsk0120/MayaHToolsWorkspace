"""Jointの通常削除をMaya標準の階層・スキン処理と比較する。"""

import sys
import unittest

import maya.cmds as cmds
import mlib


class JointStandardDeleteTest(unittest.TestCase):
    """単数・コマンド入口がジョイント整理を暗黙実行しない。"""

    def setUp(self):
        """使い捨てのシーンを作る。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)

    def test_hierarchy_deletion_matches_native_and_supports_undo(self):
        """Jointの子も削除し、通常更新は一回のUndoで復元する。"""
        for entry in (lambda n: n.delete(), mlib.delete):
            root = mlib.createNode("joint")
            child = mlib.createNode("joint", parent=root)
            control = mlib.createNode("transform", parent=child)
            entry(root)
            self.assertFalse(root.isValid())
            self.assertFalse(child.isValid())
            self.assertFalse(control.isValid())
            cmds.undo()
            self.assertTrue(root.isValid())
            self.assertEqual(child.getParent(), root)
            cmds.redo()
            self.assertFalse(root.isValid())

    def test_fast_hierarchy_deletion_does_not_add_undo(self):
        """fastも子を削除し、直前のUndo履歴を変えない。"""
        root = mlib.createNode("joint")
        child = mlib.createNode("joint", parent=root)
        sentinel = mlib.createNode("network")
        previous = cmds.undoInfo(query=True, undoName=True)
        root.delete(fast=True)
        self.assertFalse(root.isValid())
        self.assertFalse(child.isValid())
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), previous)
        cmds.undo()
        self.assertFalse(sentinel.isValid())

    def test_skin_deletion_uses_native_redistribution(self):
        """祖先への独自移送を行わず、ネイティブ削除と同じウェイトになる。"""
        for fast in (False, True):
            cmds.file(new=True, force=True)
            root = mlib.createNode("joint")
            middle = mlib.createNode("joint", parent=root)
            other = mlib.createNode("joint")
            mesh = cmds.polyPlane(ch=False, sx=1, sy=1)[0]
            skin = mlib.getNode(cmds.skinCluster([n.getFullName() for n in (root, middle, other)],
                                                mesh, toSelectedBones=True)[0])
            skin.setWeights([n.getFullName() for n in (root, middle, other)], [.2, .3, .5])
            cmds.delete(middle.getFullName())
            expected = list(skin.getWeights([root, other]))
            cmds.undo()
            middle.delete(fast=fast)
            self.assertEqual(list(skin.getWeights([root, other])), expected)

    def test_safe_preserves_connected_joint_and_descendants(self):
        """safeの接続保護は標準化後も維持する。"""
        root = mlib.createNode("joint")
        child = mlib.createNode("joint", parent=root)
        root.getPlug("scale").connectTo(child.getPlug("inverseScale"))
        root.delete(safe=True)
        self.assertTrue(root.isValid())
        self.assertTrue(child.isValid())
        with self.assertRaises(TypeError):
            root.delete(safe=1)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
