"""コンポーネントの正式getter・選択分類・参照の現在有効性を検証する。"""

import inspect
import sys
import unittest
import uuid
from unittest import mock

import maya.cmds as cmds
import mlib

mlib.reload()

from mlib.common import Selection
from mlib.components import CV, CVs, Edge, Edges, Face, Faces, UV, UVs, Vertex, Vertices


class ComponentUsabilityTest(unittest.TestCase):
    """一時名前空間のシーンで、既存入口との互換と境界を確認する。"""

    def setUp(self):
        """テスト用のメッシュとカーブを作成する。"""
        self.namespace = "mlibComponentUsability_" + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)
        name = cmds.polyCube(name=self.namespace + ":mesh", constructionHistory=False)[0]
        self.mesh = mlib.getNode(name).getShape()
        name = cmds.curve(name=self.namespace + ":curve", degree=1,
                          point=[(0, 0, 0), (1, 1, 0), (2, 0, 0)])
        self.curve = mlib.getNode(name).getShape()

    def tearDown(self):
        """テスト用の名前空間を削除する。"""
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def test_formal_getters_preserve_signature_flags_and_types(self):
        """単数・複数の正式getterが引数と型を維持する。"""
        singles = (
            (self.mesh, "getVertex", "vertex", Vertex),
            (self.mesh, "getEdge", "edge", Edge),
            (self.mesh, "getFace", "face", Face),
            (self.mesh, "getUV", "uv", UV),
            (self.curve, "getCV", "cv", CV),
        )
        for shape, formal, short, expected in singles:
            getter = getattr(shape, formal)
            self.assertFalse(hasattr(type(shape), short))
            parameters = inspect.signature(getter).parameters
            self.assertEqual(tuple(parameters), ("index", "idx"))
            self.assertIs(parameters["index"].default, Ellipsis)
            self.assertIs(parameters["idx"].default, Ellipsis)
            self.assertEqual(parameters["idx"].kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIsInstance(getter(idx=0), expected)
            self.assertEqual(getter(0), getter(idx=0))
            for method in (getter,):
                with self.assertRaises(TypeError):
                    method(index=0, idx=1)
                with self.assertRaises(IndexError):
                    method(-1)
        plural = (
            (self.mesh, "getVertices", "vertices", Vertices),
            (self.mesh, "getEdges", "edges", Edges),
            (self.mesh, "getFaces", "faces", Faces),
            (self.mesh, "getUVs", "uvs", UVs),
            (self.curve, "getCVs", "cvs", CVs),
        )
        for shape, formal, short, expected in plural:
            getter = getattr(shape, formal)
            self.assertFalse(hasattr(type(shape), short))
            self.assertEqual(str(inspect.signature(getter)), "(indices=None)")
            self.assertIsInstance(getter(), expected)
            self.assertEqual(getter([2, 0, 2]).indices, (2, 0))
            self.assertEqual(getter(indices=[]).indices, ())
            self.assertEqual(getter(iter([2, 0])).indices, getter([2, 0]).indices)

    def test_short_getters_use_current_formal_override(self):
        """正式getterを差し替えて利用できる。"""
        for shape, formal, short in (
            (self.mesh, "getVertex", "vertex"), (self.mesh, "getEdge", "edge"),
            (self.mesh, "getEdges", "edges"), (self.mesh, "getFace", "face"),
            (self.mesh, "getFaces", "faces"), (self.mesh, "getUV", "uv"),
            (self.mesh, "getUVs", "uvs"), (self.curve, "getCV", "cv"),
            (self.curve, "getCVs", "cvs"),
        ):
            sentinel = object()
            with mock.patch.object(shape, formal, return_value=sentinel) as reader:
                self.assertIs(getattr(shape, formal)(0), sentinel)
                reader.assert_called_once_with(0)

    def test_selection_formal_names_preserve_symbols_order_and_owners(self):
        """正式種類名は記号と同じ集合を返し、保持順と複数シェイプを維持する。"""
        other = mlib.getNode(cmds.polyCube(name=self.namespace + ":other")[0]).getShape()
        joint = mlib.createNode("joint", name=self.namespace + ":joint")
        selected = Selection([
            self.mesh.getVertex(2), self.mesh.getEdge(0), self.curve.getCV(1),
            other.getVertex(1), self.mesh.getVertex(0), self.mesh.getFace(0), self.mesh.getUV(0),
            joint, joint.getPlug("translateX"),
        ])
        for formal, symbol in (
            ("vertex", "vtx"), ("edge", "e"), ("face", "f"),
            ("uv", "map"), ("controlVertex", "cv"),
        ):
            self.assertEqual(list(selected.filter(formal)), list(selected.filter(symbol)))
        groups = selected.filter("vertex").getComponents()
        self.assertEqual([group.indices for group in groups], [(2, 0), (1,)])
        self.assertEqual([group.shape for group in groups], [self.mesh, other])
        self.assertEqual(list(selected.filter("joint")), [joint])
        self.assertEqual(list(selected.filter("plug")), [joint.getPlug("translateX")])
        self.assertEqual(len(selected.filter("unknownComponent")), 0)
        self.assertEqual(len(Selection().filter("vertex")), 0)
        self.assertEqual(len(selected), 9)

    def test_current_validity_changes_with_topology(self):
        """保持番号が現在の範囲外になった場合だけFalseになり、既存照会は例外のまま。"""
        transform, history = cmds.polyPlane(name=self.namespace + ":plane", sx=2, sy=2)
        shape = mlib.getNode(transform).getShape()
        items = [shape.getVertex(8), shape.getVertices([8, 0]), shape.getEdge(11),
                 shape.getEdges([11]), shape.getFace(3), shape.getFaces([3])]
        empty = shape.getVertices([])
        self.assertTrue(all(item.isValid() for item in items))
        cmds.setAttr(history + ".subdivisionsWidth", 1)
        cmds.setAttr(history + ".subdivisionsHeight", 1)
        for item in items:
            self.assertFalse(item.isValid())
            self.assertFalse(item.isValid())
        self.assertTrue(empty.isValid())
        with self.assertRaises(IndexError):
            items[0].getPosition()
        with self.assertRaises(IndexError):
            items[1].getFullNames()
        cmds.undo()
        cmds.undo()
        self.assertTrue(all(item.isValid() for item in items))

    def test_deleted_shape_empty_contract_and_undo(self):
        """削除中の空集合もFalseで、Undo後は保持参照を再び照会できる。"""
        single = self.mesh.getVertex(0)
        items = self.mesh.getVertices([1, 0])
        empty = self.mesh.getVertices([])
        cmds.delete(self.mesh.getTransform())
        undo_name = cmds.undoInfo(query=True, undoName=True)
        for value in (single, items, empty):
            self.assertFalse(value.isValid())
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        self.assertEqual(empty.getPosition(), [])
        with self.assertRaises(RuntimeError):
            single.getFullName()
        cmds.undo()
        self.assertTrue(all(value.isValid() for value in (single, items, empty)))
        cmds.redo()
        self.assertFalse(single.isValid())

    def test_validity_uses_current_uv_set_and_cv_count(self):
        """UVは現在セットの番号範囲、CVは現在カーブの番号範囲を使う。"""
        uv, uvs, empty = self.mesh.getUV(0), self.mesh.getUVs([0]), self.mesh.getUVs([])
        original = cmds.polyUVSet(self.mesh, query=True, currentUVSet=True)[0]
        cmds.polyUVSet(self.mesh, create=True, uvSet="empty")
        cmds.polyUVSet(self.mesh, currentUVSet=True, uvSet="empty")
        self.assertFalse(uv.isValid())
        self.assertFalse(uvs.isValid())
        self.assertTrue(empty.isValid())
        cmds.polyUVSet(self.mesh, currentUVSet=True, uvSet=original)
        self.assertTrue(uv.isValid())
        self.assertTrue(uvs.isValid())
        cv, cvs = self.curve.getCV(2), self.curve.getCVs([2])
        self.assertTrue(cv.isValid())
        self.assertTrue(cvs.isValid())
        with mock.patch.object(self.curve, "getNumCVs", return_value=2):
            self.assertFalse(cv.isValid())
            self.assertFalse(cvs.isValid())

    def test_canonical_validity_checks_shape_type(self):
        """正式判定の差替えと、所有シェイプの種類に基づく無効化を確認する。"""
        values = (self.mesh.getVertex(0), self.mesh.getVertices([0]), self.mesh.getVertices([]))
        for value in values:
            self.assertFalse(hasattr(type(value), "valid"))
            with mock.patch.object(value, "isValid", return_value=False) as reader:
                self.assertFalse(value.isValid())
                reader.assert_called_once_with()
        with mock.patch.object(self.mesh, "getType", return_value="nurbsCurve"):
            self.assertTrue(all(not value.isValid() for value in values))

    def test_delete_plug_recovery_names_callable_owner(self):
        """拒否時の回復案内は、そのまま実行可能な所有ノード取得を示す。"""
        node = mlib.createNode("network", name=self.namespace + ":deleteOwner")
        plug = node.addAttr("amount", attributeType="double")
        with self.assertRaisesRegex(TypeError, r"plug\.getNode\(\)"):
            mlib.delete(plug)
        self.assertTrue(node.isValid())
        mlib.delete(plug.getNode())
        self.assertFalse(node.isValid())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
