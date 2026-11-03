"""10.2.0 で足したメッシュの照会・編集と、コンポーネントの変換の契約を固定する。

- Mesh: 面の上の最近点・補間した法線・半直線の交点・UV と位置の相互変換は closestPointOnMesh ノードや om2 と突き合わせる。
- Mesh: 頂点の色の読み書き(Undo 1回・fast は Undo なし)、UV セットの照会と作成・複製・改名・削除(Undo 1回)。
- Mesh.getBorderEdges/getBorderVertices、Vertices/Edges.getFaces・Faces.getEdges は polyListComponentConversion と突き合わせる。
"""

import math
import re
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.components import Edges, Faces, Vertices
from mlib.maths import Vector
from support.specCase import NamespaceCase


def _distance(first, second):
    """2点の距離(Python 3.7 には math.dist が無いため)。"""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


def _indices(components):
    """cmds のコンポーネント名の並びを、番号の昇順の list にする。"""
    names = cmds.ls(components or [], flatten=True)
    return sorted(int(re.search(r"\[(\d+)\]$", name).group(1)) for name in names)


class _MeshCase(NamespaceCase):
    """名前空間に polyCube・polySphere・polyPlane を作る補助。"""

    def cube(self, history=False, **flags):
        transform = cmds.polyCube(name=self.name("cube#"), constructionHistory=history, **flags)[0]
        return mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])

    def sphere(self):
        transform = cmds.polySphere(name=self.name("sphere#"), constructionHistory=False,
                                    subdivisionsAxis=12, subdivisionsHeight=8)[0]
        # mayapy の既定ではハードエッジで作られるため、補間した法線を確かめられるようソフトにする。
        cmds.polySoftEdge(transform, angle=180, constructionHistory=False)
        return mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])

    def plane(self):
        transform = cmds.polyPlane(name=self.name("plane#"), constructionHistory=False,
                                   subdivisionsX=3, subdivisionsY=2)[0]
        return mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])

    def transform_of(self, mesh):
        return cmds.listRelatives(mesh.getFullName(), parent=True, fullPath=True)[0]

    def closest_node(self, mesh, point):
        """closestPointOnMesh ノードで、ワールド空間の位置に最も近い点の結果を返す。"""
        node = self.make("closestPointOnMesh", "cpom#")
        cmds.connectAttr(mesh.getFullName() + ".worldMesh[0]", node + ".inMesh")
        cmds.connectAttr(self.transform_of(mesh) + ".worldMatrix[0]", node + ".inputMatrix")
        cmds.setAttr(node + ".inPosition", *point)
        return {
            "position": cmds.getAttr(node + ".result.position")[0],
            "normal": cmds.getAttr(node + ".result.normal")[0],
            "face": cmds.getAttr(node + ".result.closestFaceIndex"),
            "uv": (cmds.getAttr(node + ".result.parameterU"), cmds.getAttr(node + ".result.parameterV")),
        }


class ClosestPointTest(_MeshCase):

    def test_closest_point_matches_closest_point_on_mesh(self):
        """面の上の最近点と面の番号は closestPointOnMesh と同じ。ワールド空間は移動を反映する。"""
        mesh = self.sphere()
        cmds.xform(self.transform_of(mesh), translation=(3, 1, -2), rotation=(10, 20, 30))
        for point in ((5, 3, 0), (3.2, 1.9, -1.7), (0, 0, 0)):
            with self.subTest(point=point):
                position, face = mesh.getClosestPoint(point, worldSpace=True)
                expected = self.closest_node(mesh, point)
                self.assertIsInstance(position, Vector)
                self.assertEqual(face, expected["face"])
                self.assertSequenceAlmostEqual(position, expected["position"], places=4)

    def test_closest_point_object_space(self):
        """オブジェクト空間の立方体の上面の点。"""
        mesh = self.cube(width=2, height=2, depth=2)
        cmds.xform(self.transform_of(mesh), translation=(10, 0, 0))
        position, face = mesh.getClosestPoint((0.2, 5, 0.3))
        self.assertSequenceAlmostEqual(position, (0.2, 1, 0.3), places=6)
        self.assertTrue(all(abs(point.y - 1) < 1e-6 for point in mesh.getFace(face).getVertices().getPosition()))
        position, _face = mesh.getClosestPoint(om2.MPoint(10.2, 5, 0.3), worldSpace=True)
        self.assertSequenceAlmostEqual(position, (10.2, 1, 0.3), places=6)

    def test_closest_normal_is_interpolated(self):
        """ソフトエッジの球では面法線と違う補間した法線で、closestPointOnMesh の法線と同じ。

        頂点の真上では、その頂点の面頂点法線と同じ。面の内部では、球の中心から外への向きに面法線より近い。
        """
        mesh = self.sphere()
        transform = self.transform_of(mesh)
        cmds.xform(transform, translation=(1, 2, 3), rotation=(0, 45, 0), scale=(2, 2, 2))
        fn = mesh.mfn()
        center = Vector(1, 2, 3)
        for vertex in (5, 30):
            with self.subTest(vertex=vertex):
                position = fn.getPoint(vertex, om2.MSpace.kWorld)
                point = center + (Vector(position) - center) * 1.5
                normal = mesh.getClosestNormal(point, worldSpace=True)
                face = mesh.getClosestPoint(point, worldSpace=True)[1]
                self.assertIsInstance(normal, Vector)
                self.assertAlmostEqual(normal.length(), 1.0, places=6)
                expected = om2.MVector(fn.getFaceVertexNormal(face, vertex, om2.MSpace.kWorld)).normal()
                self.assertSequenceAlmostEqual(normal, expected, places=4)
        for point in ((3, 4, 3.5), (1.4, 4.5, 3.1)):
            with self.subTest(point=point):
                normal = mesh.getClosestNormal(point, worldSpace=True)
                closest = self.closest_node(mesh, point)
                self.assertSequenceAlmostEqual(normal, Vector(closest["normal"]).normal(), places=4)
                face_normal = Vector(fn.getPolygonNormal(closest["face"], om2.MSpace.kWorld)).normal()
                radial = (Vector(closest["position"]) - center).normal()
                self.assertGreater((normal - face_normal).length(), 1e-3)
                self.assertLess((normal - radial).length(), (face_normal - radial).length())

    def test_closest_normal_hard_edges_is_face_normal(self):
        """ハードエッジの立方体では面法線。"""
        mesh = self.cube()
        self.assertSequenceAlmostEqual(mesh.getClosestNormal((0.1, 3, 0.2)), (0, 1, 0), places=6)
        self.assertSequenceAlmostEqual(mesh.getClosestNormal((3, 0.1, 0.2)), (1, 0, 0), places=6)

    def test_errors(self):
        """入力の型・値の不正。"""
        mesh = self.cube()
        for method in (mesh.getClosestPoint, mesh.getClosestNormal, mesh.getUVAtPoint):
            with self.subTest(method=method.__name__):
                self.assertRaises(TypeError, method, "abc")
                self.assertRaises(TypeError, method, (0, 0, 0), worldSpace=1)
                self.assertRaises(ValueError, method, (0, 0))
                self.assertRaises(ValueError, method, (0, float("nan"), 0))


class IntersectTest(_MeshCase):

    def test_hits_sorted_both_sides(self):
        """外から通すと2面に近い順で当たる。内側からは裏から1面に当たる(両面)。"""
        mesh = self.cube(width=2, height=2, depth=2)
        hits = mesh.intersect((-5, 0.1, 0.2), (3, 0, 0))
        self.assertEqual(len(hits), 2)
        self.assertSequenceAlmostEqual([hit[2] for hit in hits], [4, 6], places=4)
        self.assertSequenceAlmostEqual(hits[0][0], (-1, 0.1, 0.2), places=4)
        self.assertSequenceAlmostEqual(hits[1][0], (1, 0.1, 0.2), places=4)
        fn = mesh.mfn()
        self.assertSequenceAlmostEqual(fn.getPolygonNormal(hits[0][1]), (-1, 0, 0), places=6)
        self.assertSequenceAlmostEqual(fn.getPolygonNormal(hits[1][1]), (1, 0, 0), places=6)
        inside = mesh.intersect(om2.MPoint(0, 0.1, 0.2), om2.MVector(1, 0, 0))
        self.assertEqual(len(inside), 1)
        self.assertAlmostEqual(inside[0][2], 1.0, places=4)
        self.assertEqual(inside[0][1], hits[1][1])

    def test_triangle_border_hit_once_per_face(self):
        """四角形の面の対角線(三角形の境目)を通っても、面ごとに1つだけ返す。"""
        mesh = self.cube(width=2, height=2, depth=2)
        hits = mesh.intersect((-5, 0, 0), (1, 0, 0))
        self.assertEqual(len(hits), 2)
        self.assertEqual(len({hit[1] for hit in hits}), 2)

    def test_max_distance_miss_and_world_space(self):
        """maxDistance より遠い交点は返さない。外れは空。ワールド空間は移動を反映する。"""
        mesh = self.cube(width=2, height=2, depth=2)
        self.assertEqual(len(mesh.intersect((-5, 0.1, 0.2), (1, 0, 0), maxDistance=4.5)), 1)
        self.assertEqual(mesh.intersect((-5, 0.1, 0.2), (1, 0, 0), maxDistance=3), [])
        self.assertEqual(mesh.intersect((-5, 5, 0.2), (1, 0, 0)), [])
        self.assertEqual(mesh.intersect((-5, 0.1, 0.2), (-1, 0, 0)), [])
        cmds.xform(self.transform_of(mesh), translation=(0, 10, 0))
        self.assertEqual(mesh.intersect((-5, 0.1, 0.2), (1, 0, 0), worldSpace=True), [])
        hits = mesh.intersect((-5, 10.1, 0.2), (1, 0, 0), worldSpace=True)
        self.assertSequenceAlmostEqual(hits[0][0], (-1, 10.1, 0.2), places=4)

    def test_matches_om2(self):
        """球の交点と面は om2 の allIntersections と同じ。"""
        mesh = self.sphere()
        hits = mesh.intersect((-3, 0.13, 0.21), (1, 0.05, 0))
        direction = om2.MFloatVector(1, 0.05, 0).normal()
        raw = mesh.mfn().allIntersections(om2.MFloatPoint(-3, 0.13, 0.21), direction, om2.MSpace.kObject,
                                          100, False, sortHits=True)
        self.assertEqual([hit[1] for hit in hits], list(raw[2]))
        self.assertSequenceAlmostEqual([hit[2] for hit in hits], list(raw[1]), places=5)

    def test_errors(self):
        """長さ0の向き・maxDistance の不正。"""
        mesh = self.cube()
        self.assertRaises(ValueError, mesh.intersect, (0, 0, 0), (0, 0, 0))
        self.assertRaises(ValueError, mesh.intersect, (0, 0, 0), (1, 0))
        self.assertRaises(TypeError, mesh.intersect, "abc", (1, 0, 0))
        for value in (0, -1, float("inf"), float("nan")):
            with self.subTest(maxDistance=value):
                self.assertRaises(ValueError, mesh.intersect, (0, 0, 0), (1, 0, 0), maxDistance=value)
        self.assertRaises(TypeError, mesh.intersect, (0, 0, 0), (1, 0, 0), maxDistance="1")
        self.assertRaises(TypeError, mesh.intersect, (0, 0, 0), (1, 0, 0), maxDistance=True)
        self.assertRaises(TypeError, mesh.intersect, (0, 0, 0), (1, 0, 0), worldSpace="yes")


class UVPointTest(_MeshCase):

    def test_uv_at_point_matches_closest_point_on_mesh(self):
        """最も近い点の UV は closestPointOnMesh と同じ。"""
        mesh = self.sphere()
        cmds.xform(self.transform_of(mesh), translation=(2, 0, 0))
        for point in ((2.3, 0.9, 0.2), (3.5, -0.2, 0.1)):
            with self.subTest(point=point):
                uv = mesh.getUVAtPoint(point, worldSpace=True)
                self.assertIsInstance(uv, tuple)
                self.assertSequenceAlmostEqual(uv, self.closest_node(mesh, point)["uv"], places=4)

    def test_point_at_uv_round_trip(self):
        """面の上の点の UV から点へ戻ると同じ位置。UV の無い所は None。"""
        mesh = self.sphere()
        cmds.xform(self.transform_of(mesh), translation=(0, 3, 0))
        for point in ((0.3, 0.8, 0.4), (-0.5, -0.3, 0.6)):
            with self.subTest(point=point):
                on_surface, _face = mesh.getClosestPoint(point)
                u, v = mesh.getUVAtPoint(on_surface)
                found = mesh.getPointAtUV(u, v)
                self.assertIsInstance(found, Vector)
                self.assertLess(_distance(found, on_surface), 1e-3)
                world = mesh.getPointAtUV(u, v, worldSpace=True)
                self.assertLess(_distance(world, (on_surface.x, on_surface.y + 3, on_surface.z)), 1e-3)
        self.assertIsNone(mesh.getPointAtUV(5, 5))
        self.assertIsNone(mesh.getPointAtUV(-0.5, 0.5))

    def test_uv_set_argument(self):
        """uvSet を指定すると、そのセットの UV を使う。無いセット・空のセット。"""
        mesh = self.cube()
        cmds.polyUVSet(mesh.getFullName(), copy=True, uvSet="map1", newUVSet="shifted")
        fn = mesh.mfn()
        us, vs = fn.getUVs("shifted")
        fn.setUVs([value + 2 for value in us], vs, "shifted")
        u, v = mesh.getUVAtPoint((0.1, 0.5, 0.1))
        shifted = mesh.getUVAtPoint((0.1, 0.5, 0.1), uvSet="shifted")
        self.assertSequenceAlmostEqual(shifted, (u + 2, v), places=5)
        found = mesh.getPointAtUV(u + 2, v, uvSet="shifted")
        self.assertSequenceAlmostEqual(found, (0.1, 0.5, 0.1), places=4)
        self.assertIsNone(mesh.getPointAtUV(u + 2, v))
        self.assertRaises(ValueError, mesh.getUVAtPoint, (0, 0, 0), uvSet="missing")
        self.assertRaises(ValueError, mesh.getPointAtUV, 0.5, 0.5, uvSet="missing")
        self.assertRaises(TypeError, mesh.getUVAtPoint, (0, 0, 0), uvSet=1)
        self.assertRaises(ValueError, mesh.getUVAtPoint, (0, 0, 0), uvSet="")
        self.assertRaises(TypeError, mesh.getPointAtUV, "0", 0.5)
        self.assertRaises(TypeError, mesh.getPointAtUV, 0.5, True)
        self.assertRaises(ValueError, mesh.getPointAtUV, float("inf"), 0.5)
        cmds.polyUVSet(mesh.getFullName(), create=True, uvSet="empty")
        self.assertIsNone(mesh.getPointAtUV(0.5, 0.5, uvSet="empty"))
        self.assertRaises(RuntimeError, mesh.getUVAtPoint, (0, 0, 0), uvSet="empty")


class VertexColorTest(_MeshCase):

    def test_no_color_set(self):
        """カラーセットが無ければ全て None。"""
        mesh = self.cube()
        self.assertEqual(mesh.getVertexColors(), [None] * 8)
        self.assertRaises(ValueError, mesh.getVertexColors, colorSet="missing")
        self.assertRaises(TypeError, mesh.getVertexColors, colorSet=1)

    def test_set_all_and_partial_with_undo(self):
        """全頂点・一部の書込み。RGB は A=1。cmds の照会と一致し、Undo 1回で戻る。"""
        mesh = self.cube()
        colors = [(index / 8.0, 0.5, 1 - index / 8.0) for index in range(8)]
        self.flushUndo()
        self.assertIs(mesh.setVertexColors(colors), mesh)

        def after():
            values = mesh.getVertexColors()
            for index, value in enumerate(values):
                self.assertSequenceAlmostEqual(value, colors[index] + (1.0,), places=5)
            self.assertSequenceAlmostEqual(
                cmds.polyColorPerVertex(mesh.getFullName() + ".vtx[3]", query=True, rgb=True), colors[3], places=5)

        def before():
            self.assertEqual(mesh.getVertexColors(), [None] * 8)

        self.assertUndoesInOneStep(before, after)
        mesh.setVertexColors([(1, 0, 0, 0.25), om2.MColor((0, 1, 0, 1))], mesh.getVertices([2, 5]))
        values = mesh.getVertexColors()
        self.assertSequenceAlmostEqual(values[2], (1, 0, 0, 0.25), places=5)
        self.assertSequenceAlmostEqual(values[5], (0, 1, 0, 1), places=5)
        self.assertIsNone(values[0])
        mesh.setVertexColors([(0, 0, 1)], mesh.getVertex(0))
        self.assertSequenceAlmostEqual(mesh.getVertexColors()[0], (0, 0, 1, 1), places=5)

    def test_color_set_argument(self):
        """colorSet を指定すると、そのセットへ書き、現在のカラーセットは変えない。"""
        mesh = self.cube()
        name = mesh.getFullName()
        cmds.polyColorSet(name, create=True, colorSet="first")
        cmds.polyColorSet(name, create=True, colorSet="second")
        cmds.polyColorSet(name, currentColorSet=True, colorSet="first")
        for fast in (False, True):
            with self.subTest(fast=fast):
                color = (0.2, 0.4, 0.6, 1.0) if fast else (0.9, 0.1, 0.1, 1.0)
                mesh.setVertexColors([color], [1], colorSet="second", fast=fast)
                self.assertEqual(cmds.polyColorSet(name, query=True, currentColorSet=True), ["first"])
                self.assertSequenceAlmostEqual(mesh.getVertexColors(colorSet="second")[1], color, places=5)
                self.assertIsNone(mesh.getVertexColors()[1])
        self.assertRaises(ValueError, mesh.setVertexColors, [(1, 0, 0)], [0], colorSet="missing")

    def test_fast_has_no_undo(self):
        """fast は Undo に積まず、全頂点を1回で書く。履歴のあるメッシュは NotImplementedError。"""
        mesh = self.cube()
        self.flushUndo()
        mesh.setVertexColors([(0.5, 0.5, 0.5)] * 8, fast=True)
        self.assertUndoEmpty()
        self.assertSequenceAlmostEqual(mesh.getVertexColors()[7], (0.5, 0.5, 0.5, 1), places=5)
        self.assertEqual(cmds.polyColorSet(mesh.getFullName(), query=True, allColorSets=True), ["colorSet1"])
        history = self.cube(history=True)
        self.assertRaises(NotImplementedError, history.setVertexColors, [(1, 0, 0)] * 8, fast=True)
        history.setVertexColors([(1, 0, 0)] * 8)
        self.assertSequenceAlmostEqual(history.getVertexColors()[0], (1, 0, 0, 1), places=5)

    def test_errors(self):
        """数・重複・範囲・型の不正は書き込む前に拒否する。"""
        mesh = self.cube()
        other = self.cube()
        cases = [
            (ValueError, ([(1, 0, 0)] * 7,), {}),
            (ValueError, ([(1, 0, 0)] * 2, [1, 1]), {}),
            (IndexError, ([(1, 0, 0)], [8]), {}),
            (TypeError, ([(1, 0, 0)], ["a"]), {}),
            (TypeError, ([(1, 0, 0)], [True]), {}),
            (ValueError, ([(1, 0)], [0]), {}),
            (ValueError, ([(1, 0, 0, 1, 1)], [0]), {}),
            (ValueError, ([(1, float("nan"), 0)], [0]), {}),
            (TypeError, ([("a", 0, 0)], [0]), {}),
            (TypeError, ((1, 0, 0), [0, 1, 2]), {}),
            (TypeError, ("red", [0]), {}),
            (ValueError, ([(1, 0, 0)], other.getVertices([0])), {}),
            (TypeError, ([(1, 0, 0)], [0]), {"fast": 1}),
            (TypeError, ([(1, 0, 0)], [0]), {"colorSet": 1}),
        ]
        for error, args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs):
                self.assertRaises(error, mesh.setVertexColors, *args, **kwargs)
        self.assertEqual(mesh.getVertexColors(), [None] * 8)


class UVSetTest(_MeshCase):

    def test_queries_match_cmds(self):
        """名前と現在の UV セットは cmds.polyUVSet と同じ。"""
        mesh = self.cube()
        name = mesh.getFullName()
        cmds.polyUVSet(name, create=True, uvSet="extra")
        self.assertEqual(mesh.getUVSetNames(), cmds.polyUVSet(name, query=True, allUVSets=True))
        self.assertEqual(mesh.getCurrentUVSet(), cmds.polyUVSet(name, query=True, currentUVSet=True)[0])
        self.assertEqual(mesh.getUVSetNames(), ["map1", "extra"])

    def test_edits_undo_in_one_step(self):
        """作成・複製・改名・削除・現在の切替は、それぞれ Undo 1回で戻る。"""
        mesh = self.cube(history=True)
        name = mesh.getFullName()
        mesh.createUVSet("base")

        def names(expected):
            return lambda: self.assertEqual(mesh.getUVSetNames(), expected)

        steps = [
            (lambda: mesh.createUVSet("made"), ["map1", "base"], ["map1", "base", "made"]),
            (lambda: mesh.copyUVSet("map1", "copied"), ["map1", "base"], ["map1", "base", "copied"]),
            (lambda: mesh.renameUVSet("base", "renamed"), ["map1", "base"], ["map1", "renamed"]),
            (lambda: mesh.deleteUVSet("base"), ["map1", "base"], ["map1"]),
        ]
        for action, before, after in steps:
            with self.subTest(after=after):
                self.flushUndo()
                self.assertIs(action(), mesh)
                self.assertUndoesInOneStep(names(before), names(after))
        self.flushUndo()
        self.assertIs(mesh.setCurrentUVSet("base"), mesh)
        self.assertUndoesInOneStep(lambda: self.assertEqual(mesh.getCurrentUVSet(), "map1"),
                                   lambda: self.assertEqual(mesh.getCurrentUVSet(), "base"))
        mesh.copyUVSet("map1", "copied")
        self.assertEqual([list(values) for values in mesh.mfn().getUVs("copied")],
                         [list(values) for values in mesh.mfn().getUVs("map1")])
        self.assertEqual(mesh.getCurrentUVSet(), "map1")
        self.assertEqual(cmds.polyUVSet(name, query=True, allUVSets=True), ["map1", "base", "copied"])

    def test_delete_current_and_default(self):
        """現在の UV セットを消すと既定の UV セットが現在になる。既定の UV セットは名前が違っても消せない。"""
        mesh = self.cube()
        mesh.createUVSet("other")
        mesh.setCurrentUVSet("other")
        mesh.deleteUVSet("other")
        self.assertEqual(mesh.getCurrentUVSet(), "map1")
        self.assertRaises(ValueError, mesh.deleteUVSet, "map1")
        mesh.renameUVSet("map1", "base")
        mesh.createUVSet("map1")
        self.assertRaises(ValueError, mesh.deleteUVSet, "base")
        mesh.deleteUVSet("map1")
        self.assertEqual(mesh.getUVSetNames(), ["base"])
        self.assertEqual(mesh.getCurrentUVSet(), "base")

    def test_errors(self):
        """無い名前・既にある名前・型の不正。"""
        mesh = self.cube()
        mesh.createUVSet("extra")
        cases = [
            (ValueError, mesh.setCurrentUVSet, ("missing",)),
            (ValueError, mesh.createUVSet, ("extra",)),
            (ValueError, mesh.createUVSet, ("",)),
            (TypeError, mesh.createUVSet, (None,)),
            (ValueError, mesh.copyUVSet, ("missing", "new")),
            (ValueError, mesh.copyUVSet, ("map1", "extra")),
            (ValueError, mesh.renameUVSet, ("missing", "new")),
            (ValueError, mesh.renameUVSet, ("extra", "map1")),
            (TypeError, mesh.renameUVSet, ("extra", 3)),
            (ValueError, mesh.deleteUVSet, ("missing",)),
            (TypeError, mesh.deleteUVSet, (1,)),
        ]
        for error, method, args in cases:
            with self.subTest(method=method.__name__, args=args):
                self.assertRaises(error, method, *args)
        self.assertEqual(mesh.getUVSetNames(), ["map1", "extra"])


class TopologyConversionTest(_MeshCase):

    def test_border_matches_cmds(self):
        """縁のエッジ・頂点は polyListComponentConversion(border=True) と同じ。閉じたメッシュは空。"""
        mesh = self.plane()
        name = mesh.getFullName()
        edges = mesh.getBorderEdges()
        vertices = mesh.getBorderVertices()
        self.assertIsInstance(edges, Edges)
        self.assertIsInstance(vertices, Vertices)
        self.assertEqual(list(edges.indices),
                         _indices(cmds.polyListComponentConversion(name + ".f[*]", toEdge=True, border=True)))
        border = ["{}.e[{}]".format(name, index) for index in edges.indices]
        self.assertEqual(list(vertices.indices), _indices(cmds.polyListComponentConversion(border, toVertex=True)))
        self.assertEqual(len(edges), 10)
        self.assertEqual(len(vertices), 10)
        self.assertEqual(len(self.cube().getBorderEdges()), 0)
        self.assertEqual(len(self.cube().getBorderVertices()), 0)

    def test_conversions_match_cmds(self):
        """頂点・エッジから面、面からエッジへの変換は polyListComponentConversion と同じ(番号の昇順)。"""
        mesh = self.sphere()
        name = mesh.getFullName()
        for selected in ([0], [5, 17, 3], [40, 41]):
            with self.subTest(vertices=selected):
                faces = mesh.getVertices(selected).getFaces()
                self.assertIsInstance(faces, Faces)
                expected = _indices(cmds.polyListComponentConversion(
                    ["{}.vtx[{}]".format(name, index) for index in selected], toFace=True))
                self.assertEqual(list(faces.indices), expected)
            with self.subTest(edges=selected):
                faces = mesh.getEdges(selected).getFaces()
                expected = _indices(cmds.polyListComponentConversion(
                    ["{}.e[{}]".format(name, index) for index in selected], toFace=True))
                self.assertEqual(list(faces.indices), expected)
            with self.subTest(faces=selected):
                edges = mesh.getFaces(selected).getEdges()
                self.assertIsInstance(edges, Edges)
                expected = _indices(cmds.polyListComponentConversion(
                    ["{}.f[{}]".format(name, index) for index in selected], toEdge=True))
                self.assertEqual(list(edges.indices), expected)
        self.assertEqual(mesh.getVertex(5).getFaces(), mesh.getVertices([5]).getFaces())
        self.assertEqual(mesh.getEdge(5).getFaces(), mesh.getEdges([5]).getFaces())
        self.assertEqual(mesh.getFace(5).getEdges(), mesh.getFaces([5]).getEdges())
        self.assertEqual(len(mesh.getVertices([]).getFaces()), 0)
        self.assertEqual(len(mesh.getFaces([]).getEdges()), 0)

    def test_invalid_after_topology_change(self):
        """削除で番号が範囲外になれば IndexError。"""
        mesh = self.cube()
        faces = mesh.getFaces([5])
        vertices = mesh.getVertices([7])
        cmds.delete(mesh.getFullName() + ".f[3:5]")
        self.assertRaises(IndexError, faces.getEdges)
        cmds.delete(mesh.getFullName() + ".vtx[6:7]")
        self.assertRaises(IndexError, vertices.getFaces)


if __name__ == "__main__":
    unittest.main()
