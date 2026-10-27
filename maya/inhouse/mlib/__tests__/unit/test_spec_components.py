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
    """Vertex/CVの座標取得・設定・Undo・fastを固定する。"""

    def test_get_position_object_and_world_in_cm(self):
        """getPositionは既定でobject空間、worldSpace/wsでworld空間。UI単位によらずcm。"""
        vertex = Vertex(self.mesh, 0)
        self.assertIsInstance(vertex.getPosition(), tuple)
        self.assertPoint(vertex.getPosition(), self.om2_point(self.mesh, 0))
        self.assertPoint(vertex.getPosition(worldSpace=True), self.om2_point(self.mesh, 0, world=True))
        self.assertPoint(vertex.getPosition(ws=True), self.om2_point(self.mesh, 0, world=True))
        self.assertPoint(vertex.getPosition(True), cmds.pointPosition(vertex.getFullName(), world=True))
        cmds.currentUnit(linear="mm")
        self.assertPoint(vertex.getPosition(), self.om2_point(self.mesh, 0))
        self.assertAlmostEqual(vertex.getPositionX(), -0.5)
        self.assertAlmostEqual(vertex.getPositionX(ws=True), 9.5)

    def test_space_argument_validation(self):
        """worldSpaceがbool以外はValueError、長短名の同時指定とfastの非boolはTypeError。"""
        vertex = Vertex(self.mesh, 0)
        with self.assertRaises(ValueError):
            vertex.getPosition(worldSpace=1)
        with self.assertRaises(TypeError):
            vertex.getPosition(worldSpace=True, ws=True)
        with self.assertRaises(TypeError):
            vertex.setPosition((0, 0, 0), fast=1)
        with self.assertRaises(TypeError):
            vertex.setPositionY(1.0, worldSpace=False, ws=False)

    def test_set_position_uses_cm_under_mm_ui_and_one_undo(self):
        """UI単位がmmでもsetPositionはcmで設定し、1回のUndoで戻る。"""
        cmds.currentUnit(linear="mm")
        vertex = Vertex(self.mesh, 2)
        before = vertex.getPosition()
        self.assertIs(vertex.setPosition((1, 2, 3)), vertex)
        self.assertPoint(self.om2_point(self.mesh, 2), (1, 2, 3))
        self.assertPoint(cmds.pointPosition(vertex.getFullName(), local=True), (10, 20, 30), places=4)
        cmds.undo()
        self.assertPoint(vertex.getPosition(), before)
        cmds.redo()
        self.assertPoint(vertex.getPosition(), (1, 2, 3))

    def test_set_world_position(self):
        """worldSpace=Trueはworld座標を設定し、object座標は親の変換を除いた値になる。"""
        vertex = Vertex(self.mesh, 1)
        vertex.setPosition((12, 1, 1), worldSpace=True)
        self.assertPoint(vertex.getPosition(ws=True), (12, 1, 1))
        self.assertPoint(vertex.getPosition(), (2, 1, 1))

    def test_axis_setters_keep_other_components(self):
        """setPositionX/Y/Zは1成分だけを変え、他の成分を保つ。"""
        vertex = Vertex(self.mesh, 3)
        x, y, z = vertex.getPosition()
        vertex.setPositionY(4.0)
        self.assertPoint(vertex.getPosition(), (x, 4.0, z))
        vertex.setPositionZ(-4.0)
        self.assertAlmostEqual(vertex.getPositionZ(), -4.0)
        self.assertAlmostEqual(vertex.getPositionY(), 4.0)
        vertex.setPositionX(11.0, ws=True)
        self.assertAlmostEqual(vertex.getPositionX(), 1.0)

    def test_invalid_coordinates_are_rejected_without_change(self):
        """3成分以外・非有限・数値以外はValueErrorで、座標を変えない。"""
        vertex = Vertex(self.mesh, 0)
        before = vertex.getPosition()
        for value in ((1, 2), (1, 2, 3, 4), (float("nan"), 0, 0), ("a", 0, 0), 5):
            with self.assertRaises(ValueError):
                vertex.setPosition(value)
        self.assertPoint(vertex.getPosition(), before)

    def test_fast_is_not_recorded_in_undo(self):
        """fast=TrueはUndoへ記録しない。入力履歴付きのShapeはNotImplementedError。"""
        cmds.select(clear=True)
        marker = cmds.undoInfo(query=True, undoName=True)
        vertex = Vertex(self.mesh, 0)
        vertex.setPosition((5, 5, 5), fast=True)
        self.assertPoint(self.om2_point(self.mesh, 0), (5, 5, 5))
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), marker)
        with self.assertRaises(NotImplementedError):
            Vertex(self.history_mesh, 0).setPosition((1, 1, 1), fast=True)

    def test_cv_positions_match_cmds(self):
        """CVの座標はcmds.pointPositionと一致し、設定も1回のUndoで戻る。"""
        cv = CV(self.curve, 1)
        self.assertPoint(cv.getPosition(), cmds.pointPosition(cv.getFullName(), local=True))
        cv.setPosition((7, 8, 9))
        self.assertPoint(cmds.pointPosition(cv.getFullName(), local=True), (7, 8, 9))
        cmds.undo()
        self.assertPoint(cv.getPosition(), (1, 2, 3))


class PointCollectionSpecTest(_ComponentCase):
    """Vertices/CVsの保持順・一括取得と設定・mirrorを固定する。"""

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

    def test_bulk_positions_order_and_one_undo(self):
        """setPositionsは保持順の座標を設定し、1回のUndoで全て戻る。件数不一致はValueError。"""
        vertices = Vertices(self.mesh, [4, 2])
        before = vertices.getPosition()
        self.assertIs(vertices.setPositions([(1, 1, 1), (2, 2, 2)]), vertices)
        self.assertPoint(self.om2_point(self.mesh, 4), (1, 1, 1))
        self.assertPoint(self.om2_point(self.mesh, 2), (2, 2, 2))
        cmds.undo()
        for actual, expected in zip(vertices.getPosition(), before):
            self.assertPoint(actual, expected)
        with self.assertRaises(ValueError):
            vertices.setPositions([(1, 1, 1)])
        with self.assertRaises(ValueError):
            vertices.setPosition((1, 1))

    def test_axis_values_for_collections(self):
        """getPositionY等は保持順のlist、setPositionYはスカラーまたは同数の列を受ける。"""
        vertices = Vertices(self.mesh, [0, 1])
        vertices.setPositionY(3.0)
        self.assertEqual(vertices.getPositionY(), [3.0, 3.0])
        vertices.setPositionZ([1.0, -1.0])
        self.assertEqual(vertices.getPositionZ(), [1.0, -1.0])
        with self.assertRaises(ValueError):
            vertices.setPositionZ([1.0])

    def test_set_position_collapses_all(self):
        """setPositionは全要素を同じ絶対座標へ集める。"""
        vertices = Vertices(self.mesh, [0, 1, 2])
        vertices.setPosition((0, 9, 0))
        for point in vertices.getPosition():
            self.assertPoint(point, (0, 9, 0))

    def test_mirror(self):
        """mirrorは指定軸をpivot中心に反転し、1回のUndoで戻る。軸・pivotの不正はValueError。"""
        vertices = Vertices(self.mesh, [0, 1])
        before = vertices.getPosition()
        self.assertIs(vertices.mirror("x", pivot=(1, 0, 0)), vertices)
        for actual, original in zip(vertices.getPosition(), before):
            self.assertPoint(actual, (2 - original[0], original[1], original[2]))
        cmds.undo()
        for actual, original in zip(vertices.getPosition(), before):
            self.assertPoint(actual, original)
        for axis in ("w", "xx", "", 0):
            with self.assertRaises(ValueError):
                vertices.mirror(axis)
        with self.assertRaises(ValueError):
            vertices.mirror("x", pivot=(0, 0))

    def test_cvs_bulk(self):
        """CVsも保持順に座標を返す。周期CVの対応を保つため名前は範囲へ圧縮しない。"""
        cvs = CVs(self.curve)
        self.assertEqual(len(cvs), 3)
        self.assertPoint(cvs.getPosition()[2], (4, 5, 6))
        prefix = self.curve.getFullName()
        self.assertEqual(cvs.getCompactNames(), [prefix + ".cv[0]", prefix + ".cv[1]", prefix + ".cv[2]"])
        self.assertEqual(cvs.getCompactNames(), cvs.getFullNames())


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
    """UVの取得・設定・Undoを固定する。"""

    def test_uv_positions_match_cmds_and_undo(self):
        """getPositionはpolyEditUVの照会と一致し、setPositionは1回のUndoで戻る。"""
        uv = UV(self.mesh, 3)
        expected = cmds.polyEditUV(uv.getFullName(), query=True)
        self.assertPoint(uv.getPosition(), expected)
        self.assertAlmostEqual(uv.getU(), expected[0])
        self.assertAlmostEqual(uv.getV(), expected[1])
        self.assertIs(uv.setPosition((1.5, -0.25)), uv)
        self.assertPoint(cmds.polyEditUV(uv.getFullName(), query=True), (1.5, -0.25))
        cmds.undo()
        self.assertPoint(uv.getPosition(), expected)
        uv.setV(0.75)
        self.assertPoint(uv.getPosition(), (expected[0], 0.75))
        with self.assertRaises(ValueError):
            uv.setPosition((1, 2, 3))
        with self.assertRaises(TypeError):
            uv.setPosition((0, 0), fast="no")

    def test_uvs_bulk(self):
        """UVs.setPositionsは保持順の行を設定し、件数不一致はValueError。"""
        uvs = UVs(self.mesh, [1, 0])
        uvs.setPositions([(0.1, 0.2), (0.3, 0.4)])
        self.assertPoint(UV(self.mesh, 1).getPosition(), (0.1, 0.2))
        self.assertPoint(UV(self.mesh, 0).getPosition(), (0.3, 0.4))
        self.assertEqual(uvs.getU(), [UV(self.mesh, 1).getU(), UV(self.mesh, 0).getU()])
        with self.assertRaises(ValueError):
            uvs.setPositions([(0.1, 0.2)])

    def test_uv_fast_is_not_recorded(self):
        """UVのfast更新はUndoへ記録せず、履歴付きShapeはNotImplementedError。"""
        cmds.select(clear=True)
        marker = cmds.undoInfo(query=True, undoName=True)
        UV(self.mesh, 0).setPosition((0.9, 0.9), fast=True)
        self.assertPoint(UV(self.mesh, 0).getPosition(), (0.9, 0.9))
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), marker)
        with self.assertRaises(NotImplementedError):
            UV(self.history_mesh, 0).setPosition((0.1, 0.1), fast=True)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
