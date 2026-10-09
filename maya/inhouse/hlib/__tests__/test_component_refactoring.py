"""一括コンポーネント照会の回数・現在参照・利用側拡張を検証する。"""

import sys
import unittest
import uuid
from unittest.mock import patch

import maya.cmds as cmds
import hlib


class ComponentRefactoringTest(unittest.TestCase):
    """独立した名前空間内で一括照会と従来の単数委譲を比較する。"""

    def setUp(self):
        """使い捨てメッシュとカーブを用意する。"""
        self.ns = "hlibBatchQuery_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.transform = cmds.polyCube(name=self.ns + ":mesh", constructionHistory=False)[0]
        self.mesh = hlib.getNode(cmds.listRelatives(self.transform, shapes=True, fullPath=True)[0])
        curve = cmds.curve(name=self.ns + ":curve", degree=1, point=[(0, 0, 0), (1, 2, 3), (4, 5, 6)])
        self.curve = hlib.getNode(cmds.listRelatives(curve, shapes=True, fullPath=True)[0])

    def tearDown(self):
        """このテストが作成した名前空間だけを削除する。"""
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_standard_construction_queries_count_once_and_keeps_order(self):
        """標準の番号列は要素数を一回だけ照会し、順序・重複除去を維持する。"""
        from hlib.components import CVs, Edges, Faces, UVs, Vertices
        for shape, cls in ((self.mesh, Vertices), (self.mesh, Edges), (self.mesh, Faces),
                           (self.mesh, UVs), (self.curve, CVs)):
            method = cls.component_class.count_attribute
            function_set = "meshFn" if shape is self.mesh else "curveFn"
            with patch.object(shape, function_set, wraps=getattr(shape, function_set)) as query:
                self.assertEqual(cls(shape, [2, 0, 2, 1]).indices, (2, 0, 1))
                self.assertEqual(query.call_count, 1)
                query.reset_mock()
                whole = cls(shape)
                self.assertEqual(query.call_count, 1)
                self.assertEqual(whole.indices, tuple(range(len(whole))))
                query.reset_mock()
                self.assertEqual(cls(shape, []).indices, ())
                query.assert_not_called()

    def test_negative_bool_and_index_conversion_preserve_failure_order(self):
        """先頭の不正番号は後続入力や要素数照会より先に拒否する。"""
        from hlib.components import Vertices
        with patch.object(self.mesh, "getNumVertices", wraps=self.mesh.getNumVertices) as query:
            with self.assertRaisesRegex(IndexError, "-1"):
                Vertices(self.mesh, [-1, 100])
            query.assert_not_called()
            with self.assertRaisesRegex(TypeError, "not bool"):
                Vertices(self.mesh, [True, 0])
            query.assert_not_called()
        events = []

        class Index:
            """番号変換が行われる時点を記録する入力。"""

            def __init__(self, value):
                self.value = value

            def __index__(self):
                events.append(self.value)
                return self.value

        self.assertEqual(Vertices(self.mesh, [Index(2), Index(0), Index(2)]).indices, (2, 0))
        self.assertEqual(events, [2, 0, 2])
        events.clear()
        with self.assertRaises(IndexError):
            Vertices(self.mesh, [Index(100), Index(0)])
        self.assertEqual(events, [100])

    def test_generator_and_custom_validation_are_not_skipped(self):
        """一般generatorの途中停止と独自単数型の構築・検査を維持する。"""
        from hlib.components import Vertex, Vertices
        events = []

        def indices():
            yield 100
            events.append("consumed after invalid index")
            raise AssertionError("The generator must stop at the invalid component")

        with self.assertRaises(IndexError):
            Vertices(self.mesh, indices())
        self.assertEqual(events, [])

        class CustomVertex(Vertex):
            def __init__(self, shape, index):
                events.append(("create", index))
                super().__init__(shape, index)

            def _validate(self):
                events.append(("validate", self.index))
                return super()._validate()

        class CustomVertices(Vertices):
            component_class = CustomVertex

        items = CustomVertices(self.mesh, [2, 0, 2])
        self.assertEqual(items.indices, (2, 0))
        self.assertEqual(events, [("create", 2), ("validate", 2), ("create", 0),
                                  ("validate", 0), ("create", 2), ("validate", 2)])
        events.clear()
        list(items)
        self.assertEqual(events, [("create", 2), ("validate", 2), ("create", 0), ("validate", 0)])

    def test_uv_query_shares_function_set_and_current_set(self):
        """非連続番号でも関数セットと現在セットを呼出し内で一回だけ得る。"""
        from hlib.components import UV
        items = self.mesh.uvs([3, 0, 2])
        expected = [UV(self.mesh, index).getPosition() for index in items.indices]
        native = self.mesh.meshFn()

        class MeshQueries:
            """実APIへ委譲しつつ、一括取得の照会数を記録する。"""

            def __init__(self):
                self.set_queries = 0
                self.count_queries = 0
                self.position_queries = 0

            def numUVs(self):
                self.count_queries += 1
                return native.numUVs()

            def currentUVSetName(self):
                self.set_queries += 1
                return native.currentUVSetName()

            def getUV(self, index, **kwargs):
                self.position_queries += 1
                return native.getUV(index, **kwargs)

        queries = MeshQueries()
        with patch.object(self.mesh, "meshFn", return_value=queries) as function_set:
            self.assertEqual(items.getPosition(), expected)
            self.assertEqual(function_set.call_count, 1)
        self.assertEqual((queries.count_queries, queries.set_queries, queries.position_queries), (1, 1, 3))

    def test_uv_current_set_switch_and_empty_deleted_reference(self):
        """保持中のUVは現在セットへ追従し、空集合は削除後も照会・更新しない。"""
        items = self.mesh.uvs([2, 0])
        before = items.getPosition()
        cmds.polyUVSet(self.transform, copy=True, uvSet="map1", newUVSet="alternate")
        cmds.polyUVSet(self.transform, currentUVSet=True, uvSet="alternate")
        values = [(10.0, 20.0), (30.0, 40.0)]
        items.setPositions(values)
        self.assertEqual(items.getPosition(), values)
        cmds.polyUVSet(self.transform, currentUVSet=True, uvSet="map1")
        self.assertEqual(items.getPosition(), before)
        cmds.polyUVSet(self.transform, create=True, uvSet="emptySet")
        cmds.polyUVSet(self.transform, currentUVSet=True, uvSet="emptySet")
        with self.assertRaises(IndexError):
            items.getPosition()
        empty = self.mesh.uvs([])
        cmds.delete(self.transform)
        self.assertEqual(empty.getPosition(), [])
        self.assertIs(empty.setPositions([]), empty)
        self.assertIs(empty.setPositions([], fast=True), empty)
        with self.assertRaises(RuntimeError):
            items.getPosition()

    def test_uv_getter_and_iteration_overrides_are_used(self):
        """利用側が単数getterまたは反復を変えた場合は従来委譲する。"""
        from hlib.components import UV, UVs
        events = []

        class CustomUV(UV):
            def getPosition(self):
                events.append(self.index)
                return (float(self.index), 99.0)

        class CustomUVs(UVs):
            component_class = CustomUV

        self.assertEqual(CustomUVs(self.mesh, [2, 0]).getPosition(), [(2.0, 99.0), (0.0, 99.0)])
        self.assertEqual(events, [2, 0])

        class ReverseUVs(UVs):
            def __iter__(self):
                return iter([CustomUV(self.shape, index) for index in reversed(self.indices)])

        self.assertEqual(ReverseUVs(self.mesh, [2, 0]).getPosition(), [(0.0, 99.0), (2.0, 99.0)])
        with patch.object(UV, "getPosition", return_value=(7.0, 8.0)) as getter:
            self.assertEqual(UVs(self.mesh, [2, 0]).getPosition(), [(7.0, 8.0)] * 2)
            self.assertEqual(getter.call_count, 2)

    def test_topology_query_order_instance_and_intermediate_wrappers(self):
        """エッジ/フェースの保持順・接続順とDAGインスタンスを維持する。"""
        from hlib.components.component import Component
        instance = cmds.instance(self.transform, name=self.ns + ":instance")[0]
        shape = hlib.getNode(cmds.listRelatives(instance, shapes=True, fullPath=True)[0])
        for items, method in ((shape.edges([3, 0, 2]), "getEdgeVertices"),
                              (shape.faces([3, 0, 2]), "getPolygonVertices")):
            native = shape.meshFn()
            expected = tuple(dict.fromkeys(index for number in items.indices
                                           for index in getattr(native, method)(number)))
            creates = []

            def profile(frame, event, arg):
                if event == "call" and frame.f_code is Component.__init__.__code__:
                    creates.append(frame.f_locals["index"])

            with patch.object(shape, "meshFn", wraps=shape.meshFn) as function_set:
                old_profile = sys.getprofile()
                sys.setprofile(profile)
                try:
                    vertices = items.getVertices()
                finally:
                    sys.setprofile(old_profile)
                self.assertEqual(function_set.call_count, 2)
            self.assertEqual(creates, [])
            self.assertEqual(vertices.indices, expected)
            self.assertIs(vertices.shape, shape)
            self.assertEqual(vertices.shape.getFullName(), shape.getFullName())

    def test_topology_single_getter_and_iteration_overrides_are_used(self):
        """頂点集約でも独自単数getter/反復を省略しない。"""
        from hlib.components import Edge, Edges, Face, Faces, Vertices
        for single, collection in ((Edge, Edges), (Face, Faces)):
            with patch.object(single, "getVertices", return_value=Vertices(self.mesh, [5, 1])) as getter:
                self.assertEqual(collection(self.mesh, [2, 0]).getVertices().indices, (5, 1))
                self.assertEqual(getter.call_count, 2)

        class ReverseEdges(Edges):
            def __iter__(self):
                return iter([Edge(self.shape, number) for number in reversed(self.indices)])

        items = ReverseEdges(self.mesh, [2, 0])
        expected = tuple(dict.fromkeys(v.index for item in items for v in item.getVertices()))
        self.assertEqual(items.getVertices().indices, expected)

    def test_topology_vertex_construction_and_iteration_overrides_are_used(self):
        """中間頂点のconstructorとVertices反復の差替えにも従来どおり委譲する。"""
        from hlib.components import Vertex, Vertices
        events = []
        original = Vertex.__init__

        def construct(vertex, shape, index):
            events.append(index)
            original(vertex, shape, index)

        for items in (self.mesh.edges([2, 0]), self.mesh.faces([2, 0])):
            expected = items.getVertices().indices
            with patch.object(Vertex, "__init__", new=construct):
                self.assertEqual(items.getVertices().indices, expected)
            self.assertTrue(events)
            events.clear()
            with patch.object(Vertex, "_validate", side_effect=LookupError("custom validation")):
                with self.assertRaisesRegex(LookupError, "custom validation"):
                    items.getVertices()

            def iterate(vertices):
                return iter([Vertex(vertices.shape, 7)])

            with patch.object(Vertices, "__iter__", new=iterate):
                self.assertEqual(items.getVertices().indices, (7,))

    def test_shape_count_override_is_not_skipped(self):
        """標準Meshの要素数getterを置換した場合も、その検査を維持する。"""
        from hlib.components import Vertices
        with patch.object(self.mesh, "getNumVertices", return_value=1) as count:
            with self.assertRaises(IndexError):
                Vertices(self.mesh, [2])
            count.assert_called_once_with()
        uvs = self.mesh.uvs([2])
        with patch.object(self.mesh, "getNumUVs", return_value=1) as count:
            with self.assertRaises(IndexError):
                uvs.getPosition()
            count.assert_called_once_with()

    def test_topology_changes_and_deleted_empty_collection_are_revalidated(self):
        """再取得は現在のトポロジーを検査し、空の頂点集約も削除参照を拒否する。"""
        edges = self.mesh.edges([11, 0])
        faces = self.mesh.faces([5, 0])
        empty_edges = self.mesh.edges([])
        empty_faces = self.mesh.faces([])
        cmds.delete(self.transform + ".f[1:5]")
        self.assertLess(self.mesh.getNumEdges(), 12)
        self.assertLess(self.mesh.getNumPolygons(), 6)
        with self.assertRaisesRegex(IndexError, "11"):
            edges.getVertices()
        with self.assertRaisesRegex(IndexError, "5"):
            faces.getVertices()
        cmds.delete(self.transform)
        for items in (edges, faces, empty_edges, empty_faces):
            with self.assertRaises(RuntimeError):
                items.getVertices()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
