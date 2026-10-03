"""DAG共通基底と具象型の選択をMaya内で検証する。"""
import unittest

from maya import cmds
import hlib
from hlib.nodes import DagNode, Node, Shape, Transform, Joint, Mesh


class DagNodeTest(unittest.TestCase):
    """階層の共通化が参照と型の契約を維持することを確認する。"""

    def setUp(self):
        """テスト専用シーンを初期化する。"""
        cmds.file(new=True, force=True)

    def test_hierarchy_and_factory(self):
        """既存の具象型を維持し、DGのみのノードを拒否する。"""
        self.assertTrue(issubclass(Transform, DagNode))
        self.assertTrue(issubclass(Shape, DagNode))
        self.assertTrue(issubclass(DagNode, Node))
        for node_type, expected in (("transform", Transform), ("joint", Joint), ("mesh", Mesh)):
            name = cmds.createNode(node_type)
            self.assertIs(type(DagNode(name)), expected)
            self.assertIs(type(hlib.getNode(name)), expected)
        with self.assertRaises(TypeError):
            DagNode(cmds.createNode("network"))

    def test_shared_methods_and_parent(self):
        """共通実装を継承し、親取得とtransform取得の違いを保持する。"""
        for method in ("dagPath", "dagFn", "parentPath"):
            self.assertIs(getattr(Transform, method), getattr(DagNode, method))
            self.assertIs(getattr(Shape, method), getattr(DagNode, method))
        parent = cmds.createNode("transform")
        child = cmds.createNode("transform", parent=parent)
        mesh = cmds.createNode("mesh", parent=child)
        root, transform, shape = map(DagNode, (parent, child, mesh))
        self.assertIsNone(root.parentPath())
        self.assertEqual(transform.parentNode(), root)
        self.assertEqual(shape.parentNode(), transform)
        self.assertEqual(shape.transform(), transform)
        self.assertEqual(transform.transform(), transform)
        self.assertEqual(shape.dagFn().object(), shape.mobject())


if __name__ == "__main__":
    unittest.main()
