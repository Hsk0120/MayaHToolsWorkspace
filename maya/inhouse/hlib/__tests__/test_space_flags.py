"""空間指定の長短フラグ・旧指定拒否・複数操作を検証する。"""

import unittest
import maya.cmds as cmds
import hlib
from hlib.nodes import Node, Joints


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

    def test_long_short_and_local(self):
        """長短名の同値性と既定ローカルを検証する。"""
        self.assertEqual(self.child.getTranslation(at=4).x, 2)
        self.assertEqual(self.child.getTranslation(ws=True, at=4).x, 12)
        self.assertEqual(self.child.getTranslation(worldSpace=True, at=4).x, 12)
        self.assertTrue(self.child.getMatrix(ws=True).isEquivalent(self.child.getMatrix(worldSpace=True)))
        self.assertEqual(list(self.mesh.getPoints(ws=True)), list(self.mesh.getPoints(worldSpace=True)))
        self.assertEqual(self.mesh.getVertices([0, 1]).getPosition(ws=True),
                         self.mesh.getVertices([0, 1]).getPosition(worldSpace=True))

    def test_setter_and_collection(self):
        """更新・Undo・複数ノードのフラグ委譲を検証する。"""
        self.child.setTranslation((20, 0, 0), ws=True, at=4)
        self.assertEqual(self.child.getPlug("translateX").get(), 10)
        cmds.undo()
        self.assertEqual(self.child.getPlug("translateX").get(), 2)
        items = Joints([self.child])
        self.assertEqual(items.getTranslation(ws=True, at=4)[0].x, 12)
        items.setTranslation((15, 0, 0), worldSpace=True, at=4)
        self.assertEqual(self.child.getPlug("translateX").get(), 5)

    def test_rejected_flags_do_not_edit(self):
        """旧名・長短名重複・非boolを更新前に拒否する。"""
        for flags, error in [({"space": 4}, TypeError),
                             ({"ws": True, "worldSpace": True}, TypeError),
                             ({"ws": 1}, ValueError), ({"worldSpace": "world"}, ValueError)]:
            with self.assertRaises(error):
                self.child.setTranslation((99, 0, 0), **flags, at=4)
            self.assertEqual(self.child.getPlug("translateX").get(), 2)
        with self.assertRaises(TypeError):
            self.child.getTranslation(True, ws=True, at=4)

    def test_curve_connection_flags(self):
        """形状情報ノードの長短名と既定ワールドを検証する。"""
        curve = hlib.createCurve(degree=1, point=[(0, 0, 0), (2, 0, 0)])
        info = Node.create("curveInfo")
        info.connectCurve(curve, ws=False)
        self.assertTrue(info.getInputPlug().getSourceWithConversion().getFullName().endswith(".local"))
        info.connectCurve(curve, worldSpace=True, force=True)
        self.assertIn(".worldSpace[", info.getInputPlug().getSourceWithConversion().getFullName())
        self.assertEqual(curve.getShape().getLength(ws=True), curve.getShape().getLength(worldSpace=True))


if __name__ == "__main__":
    unittest.main()
