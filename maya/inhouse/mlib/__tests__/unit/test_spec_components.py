"""mlib.components の単数・複数コンポーネントの約束を固定する仕様テスト(担当D)。

番号の検証・名前・座標の取得と設定(cm・object/world)・Undo・fast・範囲外・
トポロジー変更後・削除後・Faceの割り当て照会を、cmdsとOpenMayaで独立に求めた値と比べる。
"""

import sys
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.components import CV
from mlib.components import CVs
from mlib.components import Edge
from mlib.components import Edges
from mlib.components import Face
from mlib.components import Faces
from mlib.components import UV
from mlib.components import UVs
from mlib.components import Vertex
from mlib.components import Vertices
from mlib.components.pointComponent import PointComponent
from mlib.components.pointComponent import PointComponents
from mlib.maths import Vector


def _shape(transform):
    """transformの最初のShapeをmlibのラッパーで返す。"""
    return mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])


class _ComponentCase(unittest.TestCase):
    """一時名前空間に履歴なしの立方体・履歴付きの立方体・カーブを作る共通の準備。"""

    def setUp(self):
        """テスト用のジオメトリとUI単位・Undo設定を保存する。"""
        self.linear = cmds.currentUnit(query=True, linear=True)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(stateWithoutFlush=True)
        self.ns = "mlibSpecDComp_" + uuid.uuid4().hex[:8]
        cmds.namespace(add=self.ns)
        self.cube = cmds.polyCube(name=self.ns + ":cube", constructionHistory=False)[0]
        cmds.xform(self.cube, translation=(10, 0, 0))
        self.mesh = _shape(self.cube)
        self.history_cube = cmds.polyCube(name=self.ns + ":history")[0]
        self.history_mesh = _shape(self.history_cube)
        curve = cmds.curve(name=self.ns + ":curve", degree=1, point=[(0, 0, 0), (1, 2, 3), (4, 5, 6)])
        self.curve = _shape(curve)

    def tearDown(self):
        """作成物を削除し、UI単位とUndo設定を戻す。"""
        cmds.currentUnit(linear=self.linear)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)
        cmds.undoInfo(state=self.undo_state)

    def assertPoint(self, actual, expected, places=6):
        """XYZの各成分がほぼ一致することを確かめる。"""
        self.assertEqual(len(actual), len(expected))
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, places=places)

    def om2_point(self, shape, index, world=False):
        """OpenMayaで頂点座標をcmで独立に求める。"""
        path = om2.MSelectionList().add(shape.getFullName()).getDagPath(0)
        space = om2.MSpace.kWorld if world else om2.MSpace.kObject
        point = om2.MFnMesh(path).getPoint(index, space)
        return (point.x, point.y, point.z)


class SingleComponentSpecTest(_ComponentCase):
    """単数コンポーネントの番号検証・名前・比較を固定する。"""

    def test_index_validation(self):
        """boolと整数以外はTypeError、負数・範囲外はIndexError。負数を末尾として扱わない。"""
        self.assertEqual(Vertex(self.mesh, 7).index, 7)
        with self.assertRaises(TypeError):
            Vertex(self.mesh, True)
        with self.assertRaises(TypeError):
            Vertex(self.mesh, 1.0)
        for index in (-1, 8, 100):
            with self.assertRaises(IndexError):
                Vertex(self.mesh, index)
        for cls, valid, invalid in ((Edge, 11, 12), (Face, 5, 6), (UV, 13, 14)):
            self.assertEqual(cls(self.mesh, valid).index, valid)
            with self.assertRaises(IndexError):
                cls(self.mesh, invalid)
        with self.assertRaises(IndexError):
            CV(self.curve, 3)

    def test_class_hierarchy(self):
        """Vertex/CVはPointComponent、Vertices/CVsはPointComponentsの派生。Edge/Face/UVは座標型ではない。"""
        self.assertTrue(issubclass(Vertex, PointComponent))
        self.assertTrue(issubclass(CV, PointComponent))
        self.assertTrue(issubclass(Vertices, PointComponents))
        self.assertTrue(issubclass(CVs, PointComponents))
        for cls in (Edge, Face, UV):
            self.assertFalse(issubclass(cls, PointComponent))

    def test_shape_type_validation(self):
        """meshの型にカーブ、CVにmeshを渡すとTypeError。Shapeラッパー以外もTypeError。"""
        with self.assertRaises(TypeError):
            Vertex(self.curve, 0)
        with self.assertRaises(TypeError):
            CV(self.mesh, 0)
        with self.assertRaises(TypeError):
            Vertex(self.mesh.getFullName(), 0)

    def test_names_and_value_semantics(self):
        """名前は完全パス・種類記号・番号。同じShape・種類・番号なら等しくハッシュも一致する。"""
        prefix = self.mesh.getFullName()
        self.assertEqual(Vertex(self.mesh, 3).getFullName(), prefix + ".vtx[3]")
        self.assertEqual(str(Edge(self.mesh, 2)), prefix + ".e[2]")
        self.assertEqual(Face(self.mesh, 1).getFullName(), prefix + ".f[1]")
        self.assertEqual(UV(self.mesh, 4).getFullName(), prefix + ".map[4]")
        self.assertEqual(CV(self.curve, 1).getFullName(), self.curve.getFullName() + ".cv[1]")
        self.assertTrue(cmds.objExists(Vertex(self.mesh, 3).getFullName()))
        self.assertEqual(Vertex(self.mesh, 3), Vertex(self.mesh, 3))
        self.assertEqual(hash(Vertex(self.mesh, 3)), hash(Vertex(self.mesh, 3)))
        self.assertEqual(len({Vertex(self.mesh, 3), Vertex(self.mesh, 3)}), 1)
        self.assertNotEqual(Vertex(self.mesh, 3), Vertex(self.mesh, 4))
        self.assertNotEqual(Vertex(self.mesh, 0), Face(self.mesh, 0))
        self.assertIs(Vertex(self.mesh, 0).shape, self.mesh)
        self.assertEqual(Vertex(self.mesh, 0).asString(), Vertex(self.mesh, 0).getFullName())

    def test_names_follow_rename(self):
        """名前はキャッシュせず、親の名前変更に追従する。"""
        vertex = Vertex(self.mesh, 0)
        renamed = cmds.rename(self.cube, self.ns + ":renamedCube")
        self.assertIn("renamedCube", vertex.getFullName())
        self.assertTrue(cmds.objExists(vertex.getFullName()))
        del renamed


class PointPositionSpecTest(_ComponentCase):
    """Vertex/CVの座標取得を固定する。"""

    def test_get_position_object_and_world_in_cm(self):
        """getPositionは既定でobject空間、worldSpace/wsでworld空間。UI単位によらずcm。"""
        vertex = Vertex(self.mesh, 0)
        self.assertIsInstance(vertex.getPosition(), Vector)
        self.assertPoint(vertex.getPosition(), self.om2_point(self.mesh, 0))
        self.assertPoint(vertex.getPosition(worldSpace=True), self.om2_point(self.mesh, 0, world=True))
        self.assertPoint(vertex.getPosition(True), cmds.pointPosition(vertex.getFullName(), world=True))
        cmds.currentUnit(linear="mm")
        self.assertPoint(vertex.getPosition(), self.om2_point(self.mesh, 0))
        self.assertAlmostEqual(vertex.getPositionX(), -0.5)
        self.assertAlmostEqual(vertex.getPositionX(worldSpace=True), 9.5)

    def test_space_argument_validation(self):
        """worldSpaceがbool以外、長短名の同時指定はいずれもTypeError。"""
        vertex = Vertex(self.mesh, 0)
        with self.assertRaises(TypeError):
            vertex.getPosition(worldSpace=1)

    def test_cv_positions_match_cmds(self):
        """CVの座標はcmds.pointPositionと一致する。"""
        cv = CV(self.curve, 1)
        self.assertPoint(cv.getPosition(), cmds.pointPosition(cv.getFullName(), local=True))
        self.assertPoint(cv.getPosition(), (1, 2, 3))


class PointCollectionSpecTest(_ComponentCase):
    """Vertices/CVsの保持順・一括取得を固定する。"""

    def test_indices_order_and_duplicates(self):
        """番号は初出順で重複を除いたtuple。Noneは全要素、空列は空集合。"""
        vertices = Vertices(self.mesh, [3, 1, 3, 0])
        self.assertEqual(vertices.indices, (3, 1, 0))
        self.assertEqual(len(vertices), 3)
        self.assertEqual([v.index for v in vertices], [3, 1, 0])
        self.assertEqual(Vertices(self.mesh).indices, tuple(range(8)))
        self.assertEqual(len(Vertices(self.mesh, [])), 0)
        self.assertEqual(Vertices(self.mesh, []).getPosition(), [])
        with self.assertRaises(IndexError):
            Vertices(self.mesh, [0, 8])
        with self.assertRaises(IndexError):
            Vertices(self.mesh, [-1])
        with self.assertRaises(TypeError):
            Vertices(self.curve, [0])

    def test_getitem_and_names(self):
        """添字は保持列の位置で、sliceは同型の部分集合。名前は個別・範囲圧縮の両方を返す。"""
        vertices = Vertices(self.mesh, [0, 1, 2, 5, 3])
        self.assertIsInstance(vertices[0], Vertex)
        self.assertEqual(vertices[-1].index, 3)
        part = vertices[1:3]
        self.assertIs(type(part), Vertices)
        self.assertEqual(part.indices, (1, 2))
        prefix = self.mesh.getFullName()
        self.assertEqual(vertices.getFullNames()[3], prefix + ".vtx[5]")
        self.assertEqual(vertices.getCompactNames(),
                         [prefix + ".vtx[0:2]", prefix + ".vtx[5]", prefix + ".vtx[3]"])
        self.assertEqual(Vertices(self.mesh, []).getCompactNames(), [])
        with self.assertRaises(IndexError):
            vertices[5]

    def test_axis_values_for_collections(self):
        """getPositionY等は保持順のlistで、各要素のgetPositionの成分と一致する。"""
        vertices = Vertices(self.mesh, [1, 0])
        cmds.xform(vertices[0].getFullName(), objectSpace=True, translation=(0.5, 3.0, 1.0))
        cmds.xform(vertices[1].getFullName(), objectSpace=True, translation=(-0.5, 3.0, -1.0))
        self.assertEqual(vertices.getPositionY(), [3.0, 3.0])
        self.assertEqual(vertices.getPositionZ(), [1.0, -1.0])
        self.assertEqual(vertices.getPositionX(worldSpace=True), [v.getPositionX(worldSpace=True) for v in vertices])

    def test_cvs_bulk(self):
        """CVsも保持順に座標を返す。周期CVの対応を保つため名前は範囲へ圧縮しない。"""
        cvs = CVs(self.curve)
        self.assertEqual(len(cvs), 3)
        self.assertPoint(cvs.getPosition()[2], (4, 5, 6))
        prefix = self.curve.getFullName()
        self.assertEqual(cvs.getCompactNames(), [prefix + ".cv[0]", prefix + ".cv[1]", prefix + ".cv[2]"])
        self.assertEqual(cvs.getCompactNames(), cvs.getFullNames())


class PointTypeSpecTest(_ComponentCase):
    """点の位置はすべてVector(単体)またはlist[Vector]で返す(6.0.0)。UVは(U, V)のtuple。"""

    def test_point_types(self):
        """Vertex/CV・Vertices/CVs・Mesh.getPoints・NurbsCurve.getCvPositionsの型と値。"""
        cases = [
            ("Vertex", Vertex(self.mesh, 0).getPosition(), self.om2_point(self.mesh, 0)),
            ("CV", CV(self.curve, 1).getPosition(), (1, 2, 3)),
        ]
        for name, value, expected in cases:
            with self.subTest(name=name):
                self.assertIs(type(value), Vector)
                self.assertPoint(value, expected)
        path = om2.MSelectionList().add(self.mesh.getFullName()).getDagPath(0)
        for ws in (False, True):
            space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
            raw = om2.MFnMesh(path).getPoints(space)
            collections = [
                ("Vertices", Vertices(self.mesh, [2, 0]).getPosition(ws), [raw[2], raw[0]]),
                ("Mesh.getPoints", self.mesh.getPoints(worldSpace=ws), list(raw)),
            ]
            for name, values, expected in collections:
                with self.subTest(name=name, worldSpace=ws):
                    self.assertIsInstance(values, list)
                    self.assertTrue(all(type(value) is Vector for value in values))
                    self.assertEqual(len(values), len(expected))
                    for value, point in zip(values, expected):
                        self.assertPoint(value, (point.x, point.y, point.z))
        curve_points = self.curve.getCvPositions()
        self.assertTrue(all(type(value) is Vector for value in curve_points))
        self.assertEqual(curve_points, [(0, 0, 0), (1, 2, 3), (4, 5, 6)])
        self.assertEqual(CVs(self.curve).getPosition(), curve_points)
        self.assertIsInstance(UV(self.mesh, 0).getPosition(), tuple)

    def test_set_points_round_trip_and_undo(self):
        """Mesh.setPointsはgetPointsの結果・tuple列・MPointArrayを受け、1回のUndoで戻る。"""
        before = self.mesh.getPoints()
        moved = [point + (0, 1, 0) for point in before]
        self.assertIs(self.mesh.setPoints(moved), self.mesh)
        self.assertEqual(self.mesh.getPoints(), moved)
        cmds.undo()
        self.assertEqual(self.mesh.getPoints(), before)
        tuples = [(p.x * 2, p.y, p.z) for p in before]
        self.mesh.setPoints(tuples)
        self.assertEqual(self.mesh.getPoints(), tuples)
        cmds.undo()
        array = om2.MPointArray([om2.MPoint(p.x, p.y + 3, p.z) for p in before])
        self.mesh.setPoints(array)
        self.assertEqual(self.mesh.getPoints(), [(p.x, p.y + 3, p.z) for p in before])
        cmds.undo()
        self.assertEqual(self.mesh.getPoints(), before)
        # 未変更の頂点は書き込まない。部分的な変更でも結果は同じ。
        partial = list(before)
        partial[3] = Vector(5, 6, 7)
        self.mesh.setPoints(partial)
        self.assertEqual(self.mesh.getPoints(), partial)
        cmds.undo()
        self.assertEqual(self.mesh.getPoints(), before)

    def test_set_points_world_space_and_units(self):
        """worldSpace=TrueはTransformを含む座標。UI単位によらずcm。"""
        world = self.mesh.getPoints(worldSpace=True)
        cmds.currentUnit(linear="mm")
        target = [point + (0, 0, 1) for point in world]
        self.mesh.setPoints(target, worldSpace=True)
        for actual, expected in zip(self.mesh.getPoints(worldSpace=True), target):
            self.assertPoint(actual, expected)
        for actual, expected in zip(self.mesh.getPoints(), target):
            self.assertPoint(actual, expected - (10, 0, 0))
        cmds.undo()
        for actual, expected in zip(self.mesh.getPoints(worldSpace=True), world):
            self.assertPoint(actual, expected)

    def test_set_points_rejects_invalid_input(self):
        """頂点数違いはValueError、型の誤りはTypeError、非有限はValueError。変更前に拒否する。"""
        before = self.mesh.getPoints()
        for points, error in [(before[:-1], ValueError), (before + [Vector()], ValueError),
                              ([(0, 0)] * 8, ValueError), ([(0, 0, float("nan"))] * 8, ValueError),
                              ("abc", TypeError), (Vector(), TypeError), (5, TypeError),
                              ([("a", 0, 0)] * 8, TypeError)]:
            with self.subTest(points=repr(points)[:40]):
                with self.assertRaises(error):
                    self.mesh.setPoints(points)
        with self.assertRaises(TypeError):
            self.mesh.setPoints(before, worldSpace=1)
        self.assertEqual(self.mesh.getPoints(), before)


class ComponentCollectionOperatorSpecTest(_ComponentCase):
    """Components の ``+``・``==``・sort(6.0.0)。"""

    def test_add(self):
        """同じシェイプ・同じ種類どうしの+は左辺の型で、重複は初出を残す。"""
        a, b = Vertices(self.mesh, [3, 1]), Vertices(self.mesh, [1, 5])
        joined = a + b
        self.assertIs(type(joined), Vertices)
        self.assertEqual(joined.indices, (3, 1, 5))
        self.assertEqual(a.indices, (3, 1))
        self.assertEqual((a + [Vertex(self.mesh, 0)]).indices, (3, 1, 0))
        self.assertEqual(([Vertex(self.mesh, 0)] + a).indices, (0, 3, 1))
        self.assertEqual((CVs(self.curve, [2]) + CVs(self.curve, [0])).indices, (2, 0))
        for other in (Edges(self.mesh, [0]), Vertices(self.history_mesh, [0]), [Edge(self.mesh, 0)],
                      [Vertex(self.history_mesh, 0)], ["x"]):
            with self.subTest(other=repr(other)):
                with self.assertRaises(TypeError):
                    a + other
        with self.assertRaises(TypeError):
            a + 1

    def test_equality(self):
        """同じシェイプ・種類・番号の並びなら等しい。list・tupleとは要素ごとに比べる。"""
        a = Vertices(self.mesh, [0, 2])
        self.assertEqual(a, Vertices(self.mesh, [0, 2]))
        self.assertNotEqual(a, Vertices(self.mesh, [2, 0]))
        self.assertNotEqual(a, Vertices(self.history_mesh, [0, 2]))
        self.assertNotEqual(a, Faces(self.mesh, [0, 2]))
        self.assertEqual(a, [Vertex(self.mesh, 0), Vertex(self.mesh, 2)])
        self.assertEqual(a, (Vertex(self.mesh, 0), Vertex(self.mesh, 2)))
        self.assertNotEqual(a, [Vertex(self.mesh, 0)])
        self.assertEqual(Vertices(self.mesh, []), [])
        with self.assertRaises(TypeError):
            hash(a)

    def test_sort(self):
        """sortはその場で並べ替えてNoneを返す。keyは単数コンポーネントを受ける。別のコレクションは変えない。"""
        a = Vertices(self.mesh, [5, 0, 3])
        part = a[:]
        self.assertIsNone(a.sort())
        self.assertEqual(a.indices, (0, 3, 5))
        self.assertEqual(part.indices, (5, 0, 3))
        a.sort(reverse=True)
        self.assertEqual(a.indices, (5, 3, 0))
        a.sort(key=lambda vertex: vertex.getPositionX())
        xs = [vertex.getPositionX() for vertex in a]
        self.assertEqual(xs, sorted(xs))
        with self.assertRaises(TypeError):
            a.sort(key=1)
        with self.assertRaises(TypeError):
            a.sort(reverse=1)


class TopologySpecTest(_ComponentCase):
    """トポロジー変更後・削除後の扱いを固定する。"""

    def test_index_out_of_range_after_topology_change(self):
        """要素が減って範囲外になった番号はisValid()がFalseで、操作はIndexError。"""
        vertex = Vertex(self.history_mesh, 7)
        vertices = Vertices(self.history_mesh, [0, 7])
        cmds.delete(self.history_mesh.getFullName() + ".f[0:4]")
        self.assertLess(self.history_mesh.getNumVertices(), 8)
        self.assertFalse(vertex.isValid())
        self.assertFalse(vertices.isValid())
        self.assertEqual(vertex.index, 7)
        with self.assertRaises(IndexError):
            vertex.getPosition()
        with self.assertRaises(IndexError):
            vertices.getPosition()
        with self.assertRaises(IndexError):
            vertex.getFullName()

    def test_deleted_shape(self):
        """削除済みShapeのコンポーネントはisValid()がFalseで、照会はRuntimeError。"""
        vertex = Vertex(self.mesh, 0)
        face = Face(self.mesh, 0)
        cmds.delete(self.cube)
        self.assertFalse(vertex.isValid())
        with self.assertRaises(RuntimeError):
            vertex.getPosition()
        with self.assertRaises(RuntimeError):
            face.getVertices()


class EdgeFaceSpecTest(_ComponentCase):
    """Edge/Faceの頂点と、Faceの割り当て照会を固定する。"""

    def mesh_fn(self):
        """履歴なし立方体のMFnMeshを返す。"""
        return om2.MFnMesh(om2.MSelectionList().add(self.mesh.getFullName()).getDagPath(0))

    def test_vertices_match_om2(self):
        """Edge/Face.getVerticesはMFnMeshの接続順、複数形は保持順で重複を除く。"""
        fn = self.mesh_fn()
        self.assertEqual(Edge(self.mesh, 5).getVertices().indices, tuple(fn.getEdgeVertices(5)))
        self.assertEqual(Face(self.mesh, 2).getVertices().indices, tuple(fn.getPolygonVertices(2)))
        self.assertIs(type(Face(self.mesh, 2).getVertices()), Vertices)
        expected = []
        for face in (2, 0):
            for index in fn.getPolygonVertices(face):
                if index not in expected:
                    expected.append(index)
        self.assertEqual(Faces(self.mesh, [2, 0]).getVertices().indices, tuple(expected))
        expected = []
        for edge in (5, 1):
            for index in fn.getEdgeVertices(edge):
                if index not in expected:
                    expected.append(index)
        self.assertEqual(Edges(self.mesh, [5, 1]).getVertices().indices, tuple(expected))

    def test_shading_engine_and_material(self):
        """getShadingEngineはフェースごとの割り当て、getMaterialはそのサーフェスシェーダー。"""
        shader = cmds.shadingNode("lambert", asShader=True, name=self.ns + ":lambert")
        group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=self.ns + ":lambertSG")
        cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
        cmds.sets(self.mesh.getFullName() + ".f[1]", edit=True, forceElement=group)
        assigned = Face(self.mesh, 1).getShadingEngine()
        self.assertEqual(assigned.getName(), group)
        self.assertEqual(Face(self.mesh, 1).getMaterial().getName(), shader)
        default = Face(self.mesh, 0).getShadingEngine()
        self.assertEqual(default.getName(), "initialShadingGroup")
        engines = Faces(self.mesh, [0, 1, 2]).getShadingEngines()
        self.assertEqual([item.getName() for item in engines], ["initialShadingGroup", group])
        materials = Faces(self.mesh, [1, 0, 1]).getMaterials()
        self.assertEqual(materials[0].getName(), shader)
        self.assertEqual(len(materials), 2)

    def test_unassigned_face_returns_none(self):
        """割り当てのないフェースはNoneを返し、複数形の結果には含めない。"""
        cmds.sets(self.mesh.getFullName(), edit=True, remove="initialShadingGroup")
        cmds.sets(self.mesh.getFullName() + ".f[*]", edit=True, remove="initialShadingGroup")
        self.assertIsNone(Face(self.mesh, 0).getShadingEngine())
        self.assertIsNone(Face(self.mesh, 0).getMaterial())
        self.assertEqual(Faces(self.mesh, [0, 1]).getShadingEngines(), [])
        self.assertEqual(Faces(self.mesh, [0, 1]).getMaterials(), [])


class UVSpecTest(_ComponentCase):
    """UVの取得を固定する。"""

    def test_uv_positions_match_cmds_and_undo(self):
        """getPosition・getU・getVはpolyEditUVの照会と一致する。"""
        uv = UV(self.mesh, 3)
        expected = cmds.polyEditUV(uv.getFullName(), query=True)
        self.assertPoint(uv.getPosition(), expected)
        self.assertAlmostEqual(uv.getU(), expected[0])
        self.assertAlmostEqual(uv.getV(), expected[1])
        cmds.polyEditUV(uv.getFullName(), relative=False, uValue=1.5, vValue=-0.25)
        self.assertPoint(uv.getPosition(), (1.5, -0.25))

    def test_uvs_bulk(self):
        """UVsは保持順に座標を返す。"""
        uvs = UVs(self.mesh, [1, 0])
        self.assertEqual(uvs.getPosition(), [UV(self.mesh, 1).getPosition(), UV(self.mesh, 0).getPosition()])
        self.assertEqual(uvs.getU(), [UV(self.mesh, 1).getU(), UV(self.mesh, 0).getU()])
        self.assertEqual(uvs.getV(), [UV(self.mesh, 1).getV(), UV(self.mesh, 0).getV()])

if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
