"""コンポーネントの正式getter・選択分類・参照の現在有効性を検証する。"""

import inspect
import sys
import unittest
import uuid
from unittest import mock

import maya.cmds as cmds
import hlib

hlib.reload()

from hlib.common import Selection
from hlib.components import CV, CVs, Edge, Edges, Face, Faces, UV, UVs, Vertex, Vertices


class ComponentUsabilityTest(unittest.TestCase):
    """一時名前空間のシーンで、既存入口との互換と境界を確認する。"""

    def setUp(self):
        """テスト用のメッシュとカーブを作成する。"""
        self.namespace = "hlibComponentUsability_" + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)
        name = cmds.polyCube(name=self.namespace + ":mesh", constructionHistory=False)[0]
        self.mesh = hlib.node(name).shape()
        name = cmds.curve(name=self.namespace + ":curve", degree=1,
                          point=[(0, 0, 0), (1, 1, 0), (2, 0, 0)])
        self.curve = hlib.node(name).shape()

    def tearDown(self):
        """テスト用の名前空間を削除する。"""
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def test_formal_getters_preserve_signature_flags_and_types(self):
        """単数・複数の旧入口と正式getterが同じ契約で取得する。"""
        singles = (
            (self.mesh, "getVertex", "vertex", Vertex),
            (self.mesh, "getEdge", "edge", Edge),
            (self.mesh, "getFace", "face", Face),
            (self.mesh, "getUV", "uv", UV),
            (self.curve, "getCV", "cv", CV),
        )
        for shape, formal, short, expected in singles:
            getter, alias = getattr(shape, formal), getattr(shape, short)
            self.assertEqual(inspect.signature(getter), inspect.signature(alias))
            self.assertEqual(str(inspect.signature(getter)), "(index)")
            self.assertIsInstance(getter(idx=0), expected)
            self.assertEqual(getter(0), alias(idx=0))
            for method in (getter, alias):
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
            getter, alias = getattr(shape, formal), getattr(shape, short)
            self.assertEqual(inspect.signature(getter), inspect.signature(alias))
            self.assertEqual(str(inspect.signature(getter)), "(indices=None)")
            self.assertIsInstance(getter(), expected)
            self.assertEqual(getter([2, 0, 2]).indices, (2, 0))
            self.assertEqual(alias(indices=[]).indices, ())
            self.assertEqual(getter(iter([2, 0])).indices, alias([2, 0]).indices)

    def test_short_getters_use_current_formal_override(self):
        """省略入口が、差し替えた正式処理へ元の引数を渡す。"""
        for shape, formal, short in (
            (self.mesh, "getVertex", "vertex"), (self.mesh, "getEdge", "edge"),
            (self.mesh, "getEdges", "edges"), (self.mesh, "getFace", "face"),
            (self.mesh, "getFaces", "faces"), (self.mesh, "getUV", "uv"),
            (self.mesh, "getUVs", "uvs"), (self.curve, "getCV", "cv"),
            (self.curve, "getCVs", "cvs"),
        ):
            sentinel = object()
            with mock.patch.object(shape, formal, return_value=sentinel) as reader:
                self.assertIs(getattr(shape, short)(0), sentinel)
                reader.assert_called_once_with(0)

    def test_selection_formal_names_preserve_symbols_order_and_owners(self):
        """正式種類名は記号と同じ集合を返し、保持順と複数シェイプを維持する。"""
        other = hlib.createPolygon(type="cube", name=self.namespace + ":other")
        joint = hlib.createNode("joint", name=self.namespace + ":joint")
        selected = Selection([
            self.mesh.vertex(2), self.mesh.edge(0), self.curve.cv(1),
            other.vertex(1), self.mesh.vertex(0), self.mesh.face(0), self.mesh.uv(0),
            joint, joint.plug("translateX"),
        ])
        for formal, symbol in (
            ("vertex", "vtx"), ("edge", "e"), ("face", "f"),
            ("uv", "map"), ("controlVertex", "cv"),
        ):
            self.assertEqual(list(selected.filter(formal)), list(selected.filter(symbol)))
        groups = selected.filter("vertex").components()
        self.assertEqual([group.indices for group in groups], [(2, 0), (1,)])
        self.assertEqual([group.shape for group in groups], [self.mesh, other])
        self.assertEqual(list(selected.filter("joint")), [joint])
        self.assertEqual(list(selected.filter("plug")), [joint.plug("translateX")])
        self.assertEqual(len(selected.filter("unknownComponent")), 0)
        self.assertEqual(len(Selection().filter("vertex")), 0)
        self.assertEqual(len(selected), 9)

    def test_current_validity_changes_with_topology(self):
        """保持番号が現在の範囲外になった場合だけFalseになり、既存照会は例外のまま。"""
        transform, history = cmds.polyPlane(name=self.namespace + ":plane", sx=2, sy=2)
        shape = hlib.node(transform).shape()
        items = [shape.vertex(8), shape.vertices([8, 0]), shape.edge(11),
                 shape.edges([11]), shape.face(3), shape.faces([3])]
        empty = shape.vertices([])
        self.assertTrue(all(item.valid() for item in items))
        cmds.setAttr(history + ".subdivisionsWidth", 1)
        cmds.setAttr(history + ".subdivisionsHeight", 1)
        for item in items:
            self.assertFalse(item.isValid())
            self.assertFalse(item.valid())
        self.assertTrue(empty.valid())
        with self.assertRaises(IndexError):
            items[0].position()
        with self.assertRaises(IndexError):
            items[1].fullNames()
        cmds.undo()
        cmds.undo()
        self.assertTrue(all(item.valid() for item in items))

    def test_deleted_shape_empty_contract_and_undo(self):
        """削除中の空集合もFalseで、Undo後は保持参照を再び照会できる。"""
        single = self.mesh.vertex(0)
        items = self.mesh.vertices([1, 0])
        empty = self.mesh.vertices([])
        cmds.delete(self.mesh.transform())
        undo_name = cmds.undoInfo(query=True, undoName=True)
        for value in (single, items, empty):
            self.assertFalse(value.valid())
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        self.assertEqual(empty.position(), [])
        with self.assertRaises(RuntimeError):
            single.fullName()
        cmds.undo()
        self.assertTrue(all(value.valid() for value in (single, items, empty)))
        cmds.redo()
        self.assertFalse(single.valid())

    def test_validity_uses_current_uv_set_and_cv_count(self):
        """UVは現在セットの番号範囲、CVは現在カーブの番号範囲を使う。"""
        uv, uvs, empty = self.mesh.uv(0), self.mesh.uvs([0]), self.mesh.uvs([])
        original = cmds.polyUVSet(self.mesh, query=True, currentUVSet=True)[0]
        cmds.polyUVSet(self.mesh, create=True, uvSet="empty")
        cmds.polyUVSet(self.mesh, currentUVSet=True, uvSet="empty")
        self.assertFalse(uv.valid())
        self.assertFalse(uvs.valid())
        self.assertTrue(empty.valid())
        cmds.polyUVSet(self.mesh, currentUVSet=True, uvSet=original)
        self.assertTrue(uv.valid())
        self.assertTrue(uvs.valid())
        cv, cvs = self.curve.cv(2), self.curve.cvs([2])
        self.assertTrue(cv.valid())
        self.assertTrue(cvs.valid())
        with mock.patch.object(self.curve, "getNumCVs", return_value=2):
            self.assertFalse(cv.valid())
            self.assertFalse(cvs.valid())

    def test_valid_alias_delegates_and_shape_type_is_checked(self):
        """省略判定は派生・差替え先へ委譲し、形状の種類を検証する。"""
        values = (self.mesh.vertex(0), self.mesh.vertices([0]), self.mesh.vertices([]))
        for value in values:
            self.assertEqual(inspect.signature(value.valid), inspect.signature(value.isValid))
            with mock.patch.object(value, "isValid", return_value=False) as reader:
                self.assertFalse(value.valid())
                reader.assert_called_once_with()
        with mock.patch.object(self.mesh, "getType", return_value="nurbsCurve"):
            self.assertTrue(all(not value.valid() for value in values))

    def test_delete_plug_recovery_names_callable_owner(self):
        """拒否時の回復案内は、そのまま実行可能な所有ノード取得を示す。"""
        node = hlib.createNode("network", name=self.namespace + ":deleteOwner")
        plug = node.addAttr("amount", attributeType="double")
        with self.assertRaisesRegex(TypeError, r"plug\.node\(\)"):
            hlib.delete(plug)
        self.assertTrue(node.valid())
        hlib.delete(plug.node())
        self.assertFalse(node.valid())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
