"""Mayaの継承と公開API・保存範囲の設計契約を検証する。"""
import sys
import unittest
import uuid
from unittest.mock import patch
import maya.cmds as cmds
import hlib

hlib.reload()


class ClassDesignTest(unittest.TestCase):
    """使い捨てノードと保存しない設定照会で契約を検証する。"""

    def setUp(self):
        """他のシーン要素と衝突しない名前空間を作る。"""
        self.ns = "hlibDesign_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)

    def tearDown(self):
        """このテストが作ったノードだけを削除する。"""
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_constraint_is_transform(self):
        """型変換・DAG照会・コレクション格納がMayaの継承と一致する。"""
        from hlib.nodes import Node, DagNode, Transform, Transforms
        for kind in ("parentConstraint", "pointConstraint", "aimConstraint"):
            name = cmds.createNode(kind, name=self.ns + ":" + kind)
            self.assertIn("transform", cmds.nodeType(name, inherited=True))
            node = Node(name)
            self.assertIsInstance(node, Transform)
            self.assertEqual(DagNode(name).dag_path().fullPathName(), node.full_name())
            self.assertEqual(Transform(name), node)
            nodes = Transforms([node])
            self.assertIs(nodes.set_visibility(False), nodes)
            self.assertFalse(node.get_visibility())

    def test_display_api_is_dag_only(self):
        """DG基底に表示専用APIを公開せずDAG単数・複数で共有する。"""
        from hlib.nodes import Node, Nodes, DagNode, DagNodes, Transforms, Joints
        methods = ("get_visibility", "set_visibility", "get_outliner_color",
                   "set_outliner_color", "get_override_color", "set_override_color",
                   "get_outliner_visibility", "set_outliner_visibility")
        for method in methods:
            self.assertFalse(hasattr(Node, method))
            self.assertFalse(hasattr(Nodes, method))
            self.assertTrue(hasattr(DagNode, method))
            self.assertTrue(hasattr(DagNodes, method))
        self.assertTrue(issubclass(Transforms, DagNodes))
        self.assertTrue(issubclass(Joints, Transforms))
        name = cmds.createNode("multiplyDivide", name=self.ns + ":dg")
        with self.assertRaises(TypeError):
            DagNodes([name])

    def test_bulk_returns_and_undo(self):
        """更新は自身、照会は保持順の値、生成は生成物を返しUndoも維持する。"""
        from hlib.nodes import Transforms
        names = [cmds.createNode("transform", name=self.ns + ":t" + str(i)) for i in range(2)]
        nodes = Transforms(names)
        self.assertIs(nodes.set_translate((1, 2, 3)), nodes)
        self.assertEqual([tuple(v) for v in nodes.get_translate()], [(1, 2, 3)] * 2)
        cmds.undo()
        self.assertEqual([tuple(v) for v in nodes.get_translate()], [(0, 0, 0)] * 2)
        self.assertIs(nodes.call_each("set_translate", [((4, 0, 0),), ((5, 0, 0),)]), nodes)
        self.assertEqual([tuple(v) for v in nodes.get_translate()], [(4, 0, 0), (5, 0, 0)])
        self.assertEqual(len(nodes.add_attribute("custom", attribute_type="double")), 2)
        empty = Transforms()
        self.assertIs(empty.set_translate((0, 0, 0)), empty)
        self.assertEqual(empty.get_translate(), [])
        self.assertIs(nodes.freeze(), nodes)

    def test_bulk_requires_declaration(self):
        """単数クラスへのメソッド追加だけでは公開範囲が広がらない。"""
        from hlib._core.collection import BulkCollection, bulk_api
        class Item:
            """公開対象を選択する単体。"""
            def query(self):
                """保持値を返す。"""
                return 3
            def not_exported(self):
                """一括公開しない操作。"""
                raise AssertionError("must not run")
        @bulk_api(Item, undo=False, reads=("query",))
        class Items(BulkCollection):
            """明示した照会だけを持つ集合。"""
        values = Items()
        values._items = [Item()]
        self.assertEqual(values.query(), [3])
        self.assertFalse(hasattr(values, "not_exported"))
        with self.assertRaises(ValueError):
            values.call_each("not_exported", [()])

    def test_save_scope_prevalidation(self):
        """単位saveとbatchの保存要求は現在値を変更する前に拒否する。"""
        from hlib.general import Preferences
        with patch.object(cmds, "currentUnit") as unit:
            for method in (Preferences.set_linear_unit, Preferences.set_angle_unit, Preferences.set_time_unit):
                with self.assertRaises(TypeError):
                    method("anything", save=True)
            unit.assert_not_called()
        with patch.object(cmds, "about", return_value=True), patch.object(cmds, "selectPref") as selection:
            with self.assertRaises(RuntimeError):
                Preferences.set_track_selection_order(True, save=True)
            selection.assert_not_called()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
