"""フリーズと作成コマンドの結果型・Undo・標準フラグを検証する。"""
from maya.api.OpenMaya import MSpace
import sys
import unittest
import maya.cmds as cmds
import mlib
mlib.reload()
from mlib.nodes import Node


class BindMirrorFreezeTest(unittest.TestCase):
    """専用namespace内のノードだけを操作する。"""

    def setUp(self):
        self.old = cmds.namespaceInfo(currentNamespace=True)
        self.ns = cmds.namespace(add="mlibBindMirrorFreezeTest")
        cmds.namespace(set=self.ns)

    def tearDown(self):
        cmds.namespace(set=self.old)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_freeze_matches_maya(self):
        names = [cmds.polyCube()[0] for _ in range(2)]
        for name in names:
            cmds.setAttr(name + ".translate", 2, 3, 4)
            cmds.setAttr(name + ".rotate", 10, 20, 30)
            cmds.setAttr(name + ".scale", 2, 3, 4)
        Node(names[0]).makeIdentity(apply=True, t=True, r=True, s=True)
        cmds.makeIdentity(names[1], apply=True, translate=True, rotate=True, scale=True)
        for attr in ("translate", "rotate", "scale"):
            self.assertEqual(cmds.getAttr(names[0] + "." + attr), cmds.getAttr(names[1] + "." + attr))
        for i in range(8):
            a = cmds.pointPosition(names[0] + ".vtx[%d]" % i, world=True)
            b = cmds.pointPosition(names[1] + ".vtx[%d]" % i, world=True)
            for x, y in zip(a, b): self.assertAlmostEqual(x, y)
        nodes = [Node(name) for name in names]
        for node in nodes:
            node.setTranslation((3, 2, 1), at=4)
        for node in nodes:
            node.makeIdentity(apply=True, t=True, r=True, s=True)
        for node in nodes:
            self.assertEqual(tuple(node.getTranslation(at=4)), (0, 0, 0))
        cmds.undo()
        cmds.undo()
        for node in nodes:
            self.assertEqual(tuple(node.getTranslation(at=4)), (3, 2, 1))




if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
