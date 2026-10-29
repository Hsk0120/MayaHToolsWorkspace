"""Mayaの継承と公開API・保存範囲の設計契約を検証する。"""
import sys
import unittest
import uuid
import maya.cmds as cmds
import mlib

mlib.reload()


class ClassDesignTest(unittest.TestCase):
    """使い捨てノードと保存しない設定照会で契約を検証する。"""

    def setUp(self):
        """他のシーン要素と衝突しない名前空間を作る。"""
        self.ns = "mlibDesign_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)

    def tearDown(self):
        """このテストが作ったノードだけを削除する。"""
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_constraint_is_transform(self):
        """型変換・DAG照会・コレクション格納がMayaの継承と一致する。"""
        from mlib.nodes import Node, Nodes, DagNode, Transform
        for kind in ("parentConstraint", "pointConstraint", "aimConstraint"):
            name = cmds.createNode(kind, name=self.ns + ":" + kind)
            self.assertIn("transform", cmds.nodeType(name, inherited=True))
            node = Node(name)
            self.assertIsInstance(node, Transform)
            self.assertEqual(DagNode(name).mpath().fullPathName(), node.getFullName())
            self.assertEqual(Transform(name), node)
            nodes = Nodes([node])
            self.assertIsInstance(nodes[0], Transform)
            self.assertIs(nodes[0].setVisibility(False), nodes[0])
            self.assertFalse(node.getVisibility())

    def test_display_api_is_dag_only(self):
        """DG基底に表示専用APIを公開せずDAG単数だけが持つ。複数形はsetVisibilityだけを一括適用する(5.0.0)。"""
        from mlib.nodes import Node, Nodes, DagNode, Joints
        methods = ("getVisibility", "setVisibility", "getOutlinerVisibility", "setOutlinerVisibility")
        for method in methods:
            self.assertFalse(hasattr(Node, method))
            self.assertEqual(hasattr(Nodes, method), method == "setVisibility")
            self.assertTrue(hasattr(DagNode, method))
            self.assertEqual(hasattr(Joints, method), method == "setVisibility")
        self.assertTrue(issubclass(Joints, Nodes))
        name = cmds.createNode("multiplyDivide", name=self.ns + ":dg")
        with self.assertRaises(TypeError):
            Joints([name])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
