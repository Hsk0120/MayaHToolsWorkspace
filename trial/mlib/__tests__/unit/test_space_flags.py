"""空間指定の長短フラグ・旧指定拒否・複数操作を検証する。"""

import unittest
import maya.cmds as cmds
import mlib
from mlib.nodes import Node


class SpaceFlagsTest(unittest.TestCase):
    """専用namespaceのノードで空間指定を比較する。"""

    def setUp(self):
        """親子Transformとメッシュを用意する。"""
        self.previous = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        self.ns = cmds.namespace(add="spaceFlagsTest")
        cmds.namespace(set=self.ns)
        self.parent = cmds.createNode("transform")
        cmds.setAttr(self.parent + ".translateX", 10)
        self.child = Node(cmds.createNode("joint", parent=self.parent))
        self.child.getPlug("translateX").set(2)
        self.mesh = Node(cmds.polyCube(constructionHistory=False)[0]).getShape()

    def tearDown(self):
        """専用namespaceを削除する。"""
        cmds.namespace(set=self.previous)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_world_and_local(self):
        """既定ローカルとワールド空間を検証する。廃止した短縮名wsは受け付けない。"""
        self.assertEqual(self.child.getTranslate(at=4).x, 2)
        self.assertEqual(self.child.getTranslate(worldSpace=True, at=4).x, 12)
        for method in (self.child.getMatrix, self.mesh.getPoints, self.mesh.getVertices([0, 1]).getPosition):
            with self.subTest(method=method.__name__):
                with self.assertRaises(TypeError):
                    method(ws=True)

    def test_setter_flags_and_undo(self):
        """更新・Undo・空間指定を検証する。"""
        self.child.setTranslate((20, 0, 0), worldSpace=True, at=4)
        self.assertEqual(self.child.getPlug("translateX").get(), 10)
        cmds.undo()
        self.assertEqual(self.child.getPlug("translateX").get(), 2)
        self.assertEqual(self.child.getTranslate(worldSpace=True, at=4).x, 12)
        self.child.setTranslate((15, 0, 0), worldSpace=True, at=4)
        self.assertEqual(self.child.getPlug("translateX").get(), 5)

    def test_rejected_flags_do_not_edit(self):
        """旧名・廃止した短縮名・非boolを更新前に拒否する。"""
        for flags, error in [({"space": 4}, TypeError), ({"ws": True}, TypeError),
                             ({"worldSpace": 1}, TypeError), ({"worldSpace": "world"}, TypeError)]:
            with self.assertRaises(error):
                self.child.setTranslate((99, 0, 0), **flags, at=4)
            self.assertEqual(self.child.getPlug("translateX").get(), 2)

    def test_curve_connection_flags(self):
        """カーブ長のワールド空間指定はTransformの拡大を含む。"""
        curve = mlib.getNode(cmds.curve(degree=1, point=[(0, 0, 0), (2, 0, 0)]))
        cmds.setAttr(curve.getFullName() + ".scaleX", 3)
        self.assertAlmostEqual(curve.getShape().getLength(), 2.0)
        self.assertAlmostEqual(curve.getShape().getLength(worldSpace=True), 6.0)


if __name__ == "__main__":
    unittest.main()
