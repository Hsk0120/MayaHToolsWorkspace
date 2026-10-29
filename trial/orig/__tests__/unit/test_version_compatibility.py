"""古いMayaで見つかった親変更とタイムラインUndoの回帰テスト。"""
import sys
import unittest
import uuid
import maya.cmds as cmds
import mlib

mlib.reload()


class VersionCompatibilityTest(unittest.TestCase):
    def test_same_parent_and_world_are_noops(self):
        prefix = "mlibCompat_" + uuid.uuid4().hex
        parent = cmds.createNode("transform", name=prefix)
        joint = cmds.createNode("joint", name=prefix + "Joint", parent=parent)
        try:
            node = mlib.getNode(joint)
            cmds.setAttr(joint + ".tx", 3)
            before = cmds.xform(joint, query=True, worldSpace=True, matrix=True)
            for target in (parent, mlib.getNode(parent)):
                self.assertIs(node.setParent(target), node)
                self.assertEqual(cmds.xform(node.getFullName(), query=True, worldSpace=True, matrix=True), before)
            node.setParent(None)
            self.assertIsNone(node.getParent())
            node.setParent(None)
            cmds.undo()
            self.assertEqual(node.getParent().getFullName(), mlib.getNode(parent).getFullName())
            cmds.redo()
            self.assertIsNone(node.getParent())
            with self.assertRaises(RuntimeError):
                node.setParent(prefix + "missing")
            cmds.delete(node.getFullName())
            with self.assertRaises(RuntimeError):
                node.setParent(None)
        finally:
            if cmds.objExists(joint):
                cmds.delete(joint)
            cmds.delete(parent)



if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
