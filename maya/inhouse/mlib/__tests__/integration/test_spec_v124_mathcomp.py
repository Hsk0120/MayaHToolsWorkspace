"""12.4.0 で maths・components に足したメソッドと、新しいコンポーネント型を確かめる。

- Vector: distanceSqTo・isZero・abs・cotan・slerp(spin)・getClosestAxis・getBarycentricWeights・getCenter・isPlanar。
- EulerRotate: isGimbalLocked・reverseDirection(It)・fromYawPitch(全回転順序で基準軸が方向を向く)。
- Quaternion: lengthSq・safeLog・asRollBend/fromRollBend(往復・単一軸の曲げ・捻り)。
- Matrix: getAxis/getAxes・asTranslateMatrix/asRotateMatrix/asScaleMatrix(積が元に戻る)・as3x3・isIdentity・
  hasNonUniformScale・transposeIt・cofactor(adjoint と突き合わせ)。
- Vertex/Edge/Face: 隣接(cmds.polyListComponentConversion・polyInfo と突き合わせ)、縁、UV、形状の判定、
  ソフト/ハードエッジ(Undo 1回)、頂点の色(Undo 1回・fast)。Components.isComplete。
- SurfaceCV(s)・LatticePoint(s)・VertexFace(s): 名前・番号の変換、座標(pointPosition と突き合わせ)、
  書込み(Undo 1回・fast)、選択・名前からの解決、不正な番号の例外、削除済みシェイプ。
"""

import math
import sys
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.components import (
    Edge,
    Face,
    LatticePoint,
    LatticePoints,
    SurfaceCV,
    SurfaceCVs,
    UV,
    Vertex,
    VertexFace,
    VertexFaces,
    Vertices,
)
from mlib.core.object import Object
from mlib.maths import EulerRotate, Matrix, Quaternion, Translate, Vector
from support.specCase import NamespaceCase


def _flat(names):
    """cmds が返す範囲付きの名前を、一件ずつのコンポーネント部分(``e[3]`` 等)の集合にする。

    cmds は Transform 名・Shape 名のどちらで返すこともあるため、ノード名を除いて比べる。
    """
    return {name.rsplit(".", 1)[1] for name in cmds.ls(names, flatten=True)}


def _names(components):
    """コンポーネントの集まりのコンポーネント部分の集合を返す。"""
    return {name.rsplit(".", 1)[1] for name in components.getFullNames()}


class _Case(NamespaceCase):
    """形状を作る補助。"""

    PREFIX = "mlibV124mc_"

    def cube(self):
        """1辺2cm の履歴なし polyCube の (transform名, Mesh) を返す。"""
        transform = cmds.polyCube(name=self.name("cube#"), width=2, height=2, depth=2, constructionHistory=False)[0]
        shape = cmds.listRelatives(transform, shapes=True, fullPath=True)[0]
        return transform, mlib.getNode(shape)

    def plane(self):
        """3x2 分割の履歴なし polyPlane(縁を持つ)の Mesh を返す。"""
        transform = cmds.polyPlane(name=self.name("pp#"), subdivisionsX=3, subdivisionsY=2,
                                   constructionHistory=False)[0]
        return mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])

    def surface(self):
        """2x3 スパン・3次の履歴なし nurbsPlane(tx=1, ty=2)の NurbsSurface を返す。"""
        transform = cmds.nurbsPlane(name=self.name("plane#"), width=4, lengthRatio=1.5, patchesU=2, patchesV=3,
                                    degree=3, axis=(0, 1, 0), constructionHistory=False)[0]
        cmds.setAttr(transform + ".translate", 1, 2, 0)
        return mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])

    def lattice(self, divisions=(2, 3, 4)):
        """cube を変形するラティスを作り、移動・拡大したラティスのシェイプを返す。"""
        transform, _ = self.cube()
        lattice = cmds.lattice(transform, divisions=divisions, objectCentered=True, name=self.name("ffd#"))[1]
        cmds.setAttr(lattice + ".translate", 1, 2, 3)
        cmds.setAttr(lattice + ".scale", 2, 2, 2)
        return mlib.getNode(cmds.listRelatives(lattice, shapes=True, fullPath=True)[0])

    def assertVectorAlmostEqual(self, actual, expected, places=7):
        self.assertSequenceAlmostEqual(list(actual), list(expected), places=places)

    def assertUndoEmpty(self):
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))


class VectorTest(_Case):
    """Vector の追加メソッド。"""

    def test_scalar_helpers(self):
        v = Vector(1.0, -2.0, 3.0)
        self.assertAlmostEqual(v.distanceSqTo((2.0, 0.0, 3.0)), 5.0)
        self.assertAlmostEqual(v.distanceSqTo(om2.MPoint(1, -2, 3)), 0.0)
        self.assertTrue(Vector(1e-12, 0, 0).isZero())
        self.assertFalse(Vector(1e-6, 0, 0).isZero())
        self.assertTrue(Vector(1e-6, 0, 0).isZero(tolerance=1e-5))
        absolute = Translate(-1.0, 2.0, -3.0).abs()
        self.assertIsInstance(absolute, Translate)
        self.assertEqual(list(absolute), [1.0, 2.0, 3.0])
        self.assertAlmostEqual(Vector(1, 0, 0).cotan((1, 1, 0)), 1.0)
        self.assertAlmostEqual(Vector(1, 0, 0).cotan((-1, math.sqrt(3), 0)), -1.0 / math.sqrt(3))
        for call, error in ((lambda: v.isZero(-1.0), ValueError), (lambda: v.isZero("x"), TypeError),
                            (lambda: v.cotan((2, -4, 6)), ValueError), (lambda: v.cotan((0, 0, 0)), ValueError)):
            with self.subTest(error=error):
                with self.assertRaises(error):
                    call()

    def test_slerp(self):
        a = Vector(2.0, 0.0, 0.0)
        b = Vector(0.0, 4.0, 0.0)
        middle = a.slerp(b, 0.5)
        self.assertVectorAlmostEqual(middle, (3.0 * math.sqrt(0.5), 3.0 * math.sqrt(0.5), 0.0))
        self.assertVectorAlmostEqual(a.slerp(b, 0.0), a)
        self.assertVectorAlmostEqual(a.slerp(b, 1.0), b)
        # spin=-1 は逆回り(270度回る)。中間では -X・-Y 側を通る。
        self.assertVectorAlmostEqual(a.slerp(b, 0.5, spin=-1), (-3.0 * math.sqrt(0.5), -3.0 * math.sqrt(0.5), 0.0))
        self.assertVectorAlmostEqual(a.slerp(b, 1.0, spin=-1), b)
        # 反平行でも長さを保った垂直な向きを通る。
        half = a.slerp((-2.0, 0.0, 0.0), 0.5)
        self.assertAlmostEqual(half.length(), 2.0)
        self.assertAlmostEqual(half.dot(a), 0.0)
        for args, error in (((b, "0.5"), TypeError), ((b, 0.5, 1.0), TypeError), ((b, 0.5, True), TypeError),
                            (((0, 0, 0), 0.5), ValueError), ((b, float("nan")), ValueError)):
            with self.subTest(args=args):
                with self.assertRaises(error):
                    a.slerp(*args)

    def test_closest_axis(self):
        cases = (((0.2, -0.9, 0.1), True, "-y"), ((0.2, -0.9, 0.1), False, "x"), ((1, 1, 0), True, "x"),
                 ((0, 0, -3), True, "-z"), ((0, 0.5, 0.4), False, "y"))
        for value, negative, expected in cases:
            with self.subTest(value=value, negative=negative):
                self.assertEqual(Vector(value).getClosestAxis(includeNegative=negative), expected)
                self.assertEqual(Vector.fromAxis(expected).getClosestAxis(), expected)
        with self.assertRaises(ValueError):
            Vector().getClosestAxis()
        with self.assertRaises(TypeError):
            Vector(1, 0, 0).getClosestAxis(includeNegative=1)

    def test_barycentric_center_planar(self):
        p0, p1, p2 = (0, 0, 0), (4, 0, 0), (0, 2, 0)
        weights = Vector(1.0, 0.5, 3.0).getBarycentricWeights(p0, p1, p2)
        self.assertSequenceAlmostEqual(weights, (0.5, 0.25, 0.25))
        rebuilt = sum((Vector(p) * w for p, w in zip((p0, p1, p2), weights)), Vector())
        self.assertVectorAlmostEqual(rebuilt, (1.0, 0.5, 0.0))
        self.assertSequenceAlmostEqual(Vector(3, 1, 0).getBarycentricWeights(p0, p1), (0.25, 0.75))
        self.assertSequenceAlmostEqual(Vector(-4, 0, 0).getBarycentricWeights(p0, p1), (2.0, -1.0))
        for args, error in (((p0,), TypeError), ((p0, p0), ValueError), ((p0, p1, (8, 0, 0)), ValueError)):
            with self.subTest(args=args):
                with self.assertRaises(error):
                    Vector(1, 1, 1).getBarycentricWeights(*args)
        center = Translate.getCenter([(0, 0, 0), om2.MPoint(2, 4, 6), Vector(1, 2, 3)])
        self.assertIsInstance(center, Translate)
        self.assertVectorAlmostEqual(center, (1.0, 2.0, 3.0))
        with self.assertRaises(ValueError):
            Vector.getCenter([])
        with self.assertRaises(TypeError):
            Vector.getCenter(Vector(1, 2, 3))
        square = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
        self.assertTrue(Vector.isPlanar(square))
        self.assertFalse(Vector.isPlanar(square + [(0.5, 0.5, 0.01)]))
        self.assertTrue(Vector.isPlanar(square + [(0.5, 0.5, 0.01)], tolerance=0.02))
        self.assertTrue(Vector.isPlanar([(0, 0, 0), (1, 1, 1), (2, 2, 2), (3, 3, 3)]))
        self.assertTrue(Vector.isPlanar([(0, 0, 0), (0, 0, 0), (1, 0, 0), (0, 1, 0), (5, 5, 0)]))
        with self.assertRaises(ValueError):
            Vector.isPlanar(square, tolerance=-1)


class EulerRotateTest(_Case):
    """EulerRotate の追加メソッド。"""

    def test_gimbal_lock(self):
        self.assertTrue(EulerRotate.fromDegrees(10, 90, 30).isGimbalLocked())
        self.assertTrue(EulerRotate.fromDegrees(10, -270, 30).isGimbalLocked())
        self.assertFalse(EulerRotate.fromDegrees(90, 0, 90).isGimbalLocked())
        # yzx の中間の軸は z。
        self.assertTrue(EulerRotate.fromDegrees(0, 0, -90, "yzx").isGimbalLocked())
        self.assertFalse(EulerRotate.fromDegrees(0, 89, 0).isGimbalLocked())
        self.assertTrue(EulerRotate.fromDegrees(0, 89, 0).isGimbalLocked(tolerance=math.radians(1.5)))
        with self.assertRaises(ValueError):
            EulerRotate().isGimbalLocked(-0.1)

    def test_reverse_direction(self):
        rotation = EulerRotate.fromDegrees(30, -120, 45, "zxy")
        reversed_rotation = rotation.reverseDirection()
        self.assertEqual(reversed_rotation.order, rotation.order)
        self.assertSequenceAlmostEqual(reversed_rotation.asDegrees(), (30, 240, 45))
        self.assertTrue(reversed_rotation.asMatrix().isEquivalent(rotation.asMatrix(), 1e-9))
        q0 = rotation.asQuaternion()
        q1 = reversed_rotation.asQuaternion()
        self.assertAlmostEqual(q0.dot(q1), -1.0)
        self.assertIs(rotation.reverseDirectionIt(), rotation)
        self.assertSequenceAlmostEqual(rotation.asDegrees(), (30, 240, 45))

    def test_from_yaw_pitch(self):
        direction = Vector(1.0, 2.0, -3.0)
        for order in ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx"):
            with self.subTest(order=order):
                rotation = EulerRotate.fromYawPitch(direction, order)
                self.assertEqual(rotation.orderName, order)
                base = "xyz".index(order[0])
                self.assertEqual(rotation[base], 0.0)
                axis = rotation.asMatrix().getAxis(base)
                self.assertVectorAlmostEqual(axis, direction.unit())
        self.assertIsInstance(EulerRotate.fromYawPitch((0, 0, 5)), EulerRotate)
        self.assertVectorAlmostEqual(EulerRotate.fromYawPitch((0, 0, 5)).asMatrix().getAxis("x"), (0, 0, 1))
        for args, error in ((((0, 0, 0),), ValueError), (((1, 0),), ValueError), (((1, 0, 0), "abc"), ValueError),
                            ((("a", 0, 0),), TypeError)):
            with self.subTest(args=args):
                with self.assertRaises(error):
                    EulerRotate.fromYawPitch(*args)


class QuaternionTest(_Case):
    """Quaternion の追加メソッド。"""

    def test_length_and_safe_log(self):
        q = Quaternion(1.0, 2.0, 2.0, 4.0)
        self.assertAlmostEqual(q.lengthSq(), 25.0)
        rotation = Quaternion.fromAxisAngle((0, 0, 1), math.radians(300))
        self.assertLess(rotation.w, 0.0)
        log = rotation.safeLog()
        self.assertAlmostEqual(math.sqrt(log.x ** 2 + log.y ** 2 + log.z ** 2), math.radians(30))
        self.assertTrue(log.exp().isEquivalent(-rotation, 1e-9))
        self.assertLess(rotation.w, 0.0)

    def test_roll_bend_single_axis(self):
        rx = Quaternion.fromAxisAngle((1, 0, 0), 40, unit="deg")
        self.assertSequenceAlmostEqual(rx.asRollBend(), (40.0, 0.0, 0.0))
        ry = Quaternion.fromAxisAngle((0, 1, 0), 30, unit="deg")
        self.assertSequenceAlmostEqual(ry.asRollBend(), (0.0, 30.0, 0.0))
        rz = Quaternion.fromAxisAngle((0, 0, 1), -50, unit="deg")
        self.assertSequenceAlmostEqual(rz.asRollBend(), (0.0, 0.0, -50.0))
        self.assertSequenceAlmostEqual(rz.asRollBend(unit="rad"), (0.0, 0.0, math.radians(-50)))
        # aimAxis="y"・upAxis="z": 横の軸は x。
        self.assertSequenceAlmostEqual(rx.asRollBend("y", "z"), (0.0, 0.0, 40.0))

    def test_roll_bend_round_trip(self):
        for aim, up in (("x", "y"), ("-y", "x"), ("z", "-x")):
            for angles in ((10.0, 20.0, -30.0), (-170.0, 60.0, 45.0), (0.0, -80.0, 10.0)):
                with self.subTest(aim=aim, up=up, angles=angles):
                    q = Quaternion.fromRollBend(*angles, aimAxis=aim, upAxis=up)
                    self.assertAlmostEqual(q.length(), 1.0)
                    self.assertSequenceAlmostEqual(q.asRollBend(aim, up), angles, places=6)
                    # 捻り(aim周り)を先に適用し、続けて曲げる。aimの行き先は捻りによらない。
                    aim_vector = Vector.fromAxis(aim)
                    bent = aim_vector.rotateBy(q)
                    no_roll = Quaternion.fromRollBend(0.0, angles[1], angles[2], aimAxis=aim, upAxis=up)
                    self.assertVectorAlmostEqual(bent, aim_vector.rotateBy(no_roll))
        self.assertIsInstance(Quaternion.fromRollBend(0, 0, 0), Quaternion)
        for call, error in ((lambda: Quaternion().asRollBend("x", "-x"), ValueError),
                            (lambda: Quaternion().asRollBend("w"), ValueError),
                            (lambda: Quaternion().asRollBend(1), TypeError),
                            (lambda: Quaternion(0, 0, 0, 0).asRollBend(), ValueError),
                            (lambda: Quaternion.fromRollBend("1", 0, 0), TypeError),
                            (lambda: Quaternion.fromRollBend(0, float("inf"), 0), ValueError),
                            (lambda: Quaternion().asRollBend(unit="sec"), ValueError)):
            with self.subTest(error=error):
                with self.assertRaises(error):
                    call()


class MatrixTest(_Case):
    """Matrix の追加メソッド。"""

    def matrix(self):
        return Matrix.compose(translate=(1, 2, 3), rotate=(0.3, -0.4, 1.1), scale=(2, 3, 4), shear=(0.2, 0, 0.1))

    def test_axes(self):
        m = self.matrix()
        rows = m.rows
        for index, name in enumerate("xyz"):
            with self.subTest(axis=name):
                self.assertVectorAlmostEqual(m.getAxis(name), rows[index][:3])
                self.assertVectorAlmostEqual(m.getAxis(index), rows[index][:3])
                self.assertVectorAlmostEqual(m.getAxis("-" + name), [-v for v in rows[index][:3]])
        self.assertEqual([list(a) for a in m.getAxes()], [list(m.getAxis(n)) for n in "xyz"])
        for axis, error in ((3, ValueError), (True, TypeError), ("w", ValueError), (1.0, TypeError)):
            with self.subTest(axis=axis):
                with self.assertRaises(error):
                    m.getAxis(axis)

    def test_split_matrices(self):
        m = self.matrix()
        t, r, s = m.asTranslateMatrix(), m.asRotateMatrix(), m.asScaleMatrix()
        self.assertTrue((s * r * t).isEquivalent(m, 1e-9))
        self.assertTrue(t.as3x3().isIdentity())
        self.assertVectorAlmostEqual(t.translate, (1, 2, 3))
        self.assertTrue((r * r.transpose()).isIdentity(1e-9))
        self.assertVectorAlmostEqual(s.translate, (0, 0, 0))
        mirrored = Matrix.compose(rotate=(0.2, 0.1, 0.3), scale=(1, 1, -1))
        self.assertTrue((mirrored.asScaleMatrix() * mirrored.asRotateMatrix()).isEquivalent(mirrored, 1e-9))
        three = m.as3x3()
        self.assertEqual(three.rows[3], (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(three.rows[0][:3], m.rows[0][:3])
        with self.assertRaises(ValueError):
            Matrix.compose(scale=(1, 0, 1)).asRotateMatrix()

    def test_predicates(self):
        self.assertTrue(Matrix().isIdentity())
        almost = Matrix()
        almost[1, 2] = 1e-12
        self.assertTrue(almost.isIdentity())
        self.assertFalse(almost.isIdentity(tolerance=0.0))
        self.assertFalse(Matrix.compose(translate=(0, 0, 1e-6)).isIdentity())
        self.assertFalse(Matrix.compose(rotate=(0.3, 0.2, 0.1), scale=(2, 2, 2)).hasNonUniformScale())
        self.assertFalse(Matrix.compose(scale=(2, 2, -2)).hasNonUniformScale())
        self.assertTrue(Matrix.compose(scale=(2, 2, 2.001)).hasNonUniformScale())
        self.assertFalse(Matrix.compose(scale=(2, 2, 2.001)).hasNonUniformScale(tolerance=0.01))
        self.assertTrue(Matrix.compose(shear=(0.1, 0, 0)).hasNonUniformScale())
        for call, error in ((lambda: Matrix().isIdentity(-1), ValueError),
                            (lambda: Matrix().hasNonUniformScale("a"), TypeError),
                            (lambda: Matrix.compose(scale=(0, 1, 1)).hasNonUniformScale(), ValueError)):
            with self.subTest(error=error):
                with self.assertRaises(error):
                    call()

    def test_transpose_it_and_cofactor(self):
        m = self.matrix()
        expected = m.transpose()
        self.assertIs(m.transposeIt(), m)
        self.assertEqual(m.values, expected.values)
        m[0, 3] = 0.5
        adjoint = m.adjoint()
        for row in range(4):
            for column in range(4):
                with self.subTest(row=row, column=column):
                    self.assertAlmostEqual(m.cofactor(row, column), adjoint[column, row], places=9)
        self.assertAlmostEqual(m.cofactor(-1, -1), m.cofactor(3, 3))
        determinant = sum(m[0, c] * m.cofactor(0, c) for c in range(4))
        self.assertAlmostEqual(determinant, m.det4x4(), places=9)
        for args, error in (((4, 0), IndexError), ((0, "a"), TypeError)):
            with self.subTest(args=args):
                with self.assertRaises(error):
                    m.cofactor(*args)


class MeshComponentTest(_Case):
    """Vertex・Edge・Face・UV の追加メソッド。"""

    def convert(self, component, **flags):
        return _flat(cmds.polyListComponentConversion(component.getFullName(), **flags))

    def names(self, components):
        return _names(components)

    def test_adjacency_matches_cmds(self):
        _, mesh = self.cube()
        vertex = mesh.getVertex(3)
        self.assertEqual(self.names(vertex.getEdges()), self.convert(vertex, toEdge=True))
        self.assertEqual(list(vertex.getEdges().indices), sorted(vertex.getEdges().indices))
        connected = vertex.getConnectedVertices()
        expected = self.convert(vertex, toEdge=True)
        expected = _flat(cmds.polyListComponentConversion([mesh.getFullName() + "." + part for part in expected],
                                                          toVertex=True))
        expected.discard(vertex.getFullName().rsplit(".", 1)[1])
        self.assertEqual(self.names(connected), expected)
        edge = Edge(mesh, 0)
        neighbors = edge.getConnectedEdges()
        expected = _flat(cmds.polyListComponentConversion(
            [mesh.getFullName() + "." + part for part in self.convert(edge, toVertex=True)], toEdge=True))
        expected.discard(edge.getFullName().rsplit(".", 1)[1])
        self.assertEqual(self.names(neighbors), expected)
        face = Face(mesh, 0)
        expected = _flat(cmds.polyListComponentConversion(
            [mesh.getFullName() + "." + part for part in self.convert(face, toEdge=True)], toFace=True))
        expected.discard(face.getFullName().rsplit(".", 1)[1])
        self.assertEqual(self.names(face.getConnectedFaces()), expected)
        # 複数形は単数のメソッドを要素ごとに呼ぶ。
        self.assertEqual([len(item) for item in mesh.getVertices([0, 1]).getEdges()], [3, 3])

    def test_boundary(self):
        mesh = self.plane()
        border_edges = set(mesh.getBorderEdges().indices)
        border_vertices = set(mesh.getBorderVertices().indices)
        self.assertEqual({e for e in range(mesh.getNumEdges()) if Edge(mesh, e).isOnBoundary()}, border_edges)
        self.assertEqual({v for v in range(mesh.getNumVertices()) if Vertex(mesh, v).isOnBoundary()},
                         border_vertices)
        self.assertEqual(sum(Face(mesh, f).isOnBoundary() for f in range(mesh.getNumPolygons())), 6)
        _, cube = self.cube()
        self.assertFalse(any(cube.getVertices().isOnBoundary()))

    def test_uvs(self):
        _, mesh = self.cube()
        face = Face(mesh, 1)
        uvs = face.getUVs()
        self.assertEqual(self.names(uvs), self.convert(face, toUV=True))
        vertex = mesh.getVertex(0)
        self.assertEqual(self.names(vertex.getUVs()), self.convert(vertex, toUV=True))
        for uv in vertex.getUVs():
            with self.subTest(uv=uv.index):
                self.assertEqual(uv.getVertex(), vertex)
        for index in range(mesh.getNumUVs()):
            with self.subTest(index=index):
                expected = self.convert(UV(mesh, index), toVertex=True)
                self.assertEqual({UV(mesh, index).getVertex().getFullName().rsplit(".", 1)[1]}, expected)
        name = mesh.getFullName()
        cmds.polyMapDel(name + ".f[0]")
        self.assertEqual(len(Face(mesh, 0).getUVs()), 0)

    def test_face_shape_checks(self):
        _, mesh = self.cube()
        face = Face(mesh, 0)
        self.assertTrue(face.isPlanar())
        self.assertTrue(face.isConvex())
        self.assertFalse(face.isLamina())
        self.assertFalse(face.isHoled())
        self.assertFalse(face.isZeroArea())
        self.assertEqual(face.getTriangleCount(), 2)
        self.assertEqual(sum(mesh.getFaces().getTriangleCount()), cmds.polyEvaluate(mesh.getFullName(), triangle=True))
        mesh.getVertex(0).moveBy((0.0, 0.0, 0.5))
        self.assertFalse(face.isPlanar())
        flat = mesh.getVertices(Face(mesh, 1).getVertices().indices)
        flat.setPosition((0.0, 5.0, 0.0))
        self.assertTrue(Face(mesh, 1).isZeroArea())
        self.assertFalse(Face(mesh, 2).isZeroArea())
        self.assertTrue(Face(mesh, 2).isZeroArea(tolerance=100.0))
        with self.assertRaises(ValueError):
            Face(mesh, 2).isZeroArea(-1.0)

    def test_smooth_edges(self):
        _, mesh = self.cube()
        edge = Edge(mesh, 0)
        self.assertFalse(edge.isSmooth())
        self.assertIn("Hard", cmds.polyInfo(edge.getFullName(), edgeToVertex=True)[0])
        self.flushUndo()
        self.assertIs(edge.setSmooth(), edge)
        self.assertUndoesInOneStep(lambda: self.assertFalse(edge.isSmooth()),
                                   lambda: self.assertTrue(edge.isSmooth()))
        self.assertEqual(cmds.listHistory(mesh.getFullName()), [mesh.getFullName().split("|")[-1]])
        edge.setSmooth(True)
        edge.setSmooth(False)
        self.assertFalse(edge.isSmooth())
        with self.assertRaises(TypeError):
            edge.setSmooth(1)
        history_transform = cmds.polyCube(name=self.name("hist#"))[0]
        history = Edge(mlib.getNode(cmds.listRelatives(history_transform, shapes=True, fullPath=True)[0]), 2)
        history.setSmooth(True)
        self.assertTrue(history.isSmooth())

    def test_vertex_color(self):
        _, mesh = self.cube()
        vertex = mesh.getVertex(2)
        self.assertIsNone(vertex.getColor())
        self.flushUndo()
        self.assertIs(vertex.setColor((1.0, 0.5, 0.0)), vertex)
        self.assertSequenceAlmostEqual(vertex.getColor(), (1.0, 0.5, 0.0, 1.0), places=5)
        self.assertSequenceAlmostEqual(cmds.polyColorPerVertex(vertex.getFullName(), query=True, rgb=True),
                                       (1.0, 0.5, 0.0), places=5)
        self.assertIsNone(mesh.getVertex(3).getColor())
        cmds.undo()
        self.assertIsNone(vertex.getColor())
        cmds.redo()
        self.flushUndo()
        vertex.setColor((0.0, 0.0, 1.0, 0.5), fast=True)
        self.assertUndoEmpty()
        self.assertSequenceAlmostEqual(vertex.getColor(), (0.0, 0.0, 1.0, 0.5), places=5)
        for call, error in ((lambda: vertex.setColor((1, 0)), ValueError),
                            (lambda: vertex.getColor(colorSet="missing"), ValueError),
                            (lambda: vertex.setColor((1, 0, 0), fast=1), TypeError)):
            with self.subTest(error=error):
                with self.assertRaises(error):
                    call()

    def test_is_complete(self):
        _, mesh = self.cube()
        self.assertTrue(mesh.getVertices().isComplete())
        self.assertTrue(Vertices(mesh, list(reversed(range(8)))).isComplete())
        self.assertFalse(mesh.getVertices([0, 1]).isComplete())
        self.assertTrue(mesh.getFaces().isComplete())
        self.assertFalse((mesh.getVertices([0]) + mesh.getVertices([1])).isComplete())

    def test_deleted_shape(self):
        transform, mesh = self.cube()
        vertex, edge, face = mesh.getVertex(0), Edge(mesh, 0), Face(mesh, 0)
        vertices = mesh.getVertices([0, 1])
        cmds.delete(transform)
        for call in (vertex.getEdges, vertex.getConnectedVertices, vertex.isOnBoundary, vertex.getUVs,
                     vertex.getColor, edge.isSmooth, edge.getConnectedEdges, face.getUVs, face.isPlanar,
                     face.getTriangleCount, vertices.isComplete):
            with self.subTest(call=call.__name__):
                with self.assertRaises(RuntimeError):
                    call()


class SurfaceCVTest(_Case):
    """SurfaceCV・SurfaceCVs。"""

    def test_index_and_names(self):
        shape = self.surface()
        count_u, count_v = shape.getNumCVs()
        cv = SurfaceCV(shape, (2, 3))
        self.assertEqual(cv.index, 2 * count_v + 3)
        self.assertEqual(cv.getMultiIndex(), (2, 3))
        self.assertEqual(SurfaceCV(shape, cv.index), cv)
        self.assertTrue(cv.getFullName().endswith(".cv[2][3]"))
        self.assertTrue(cmds.objExists(cv.getFullName()))
        self.assertIn("cv[2][3]", repr(cv))
        cvs = SurfaceCVs(shape)
        self.assertEqual(len(cvs), count_u * count_v)
        self.assertTrue(cvs.isComplete())
        self.assertEqual(_flat(cvs.getFullNames()), _flat(shape.getFullName() + ".cv[*][*]"))
        mixed = SurfaceCVs(shape, [(0, 0), 7, (0, 0)])
        self.assertEqual(mixed.indices, (0, 7))
        self.assertEqual(mixed.getMultiIndex(), [(0, 0), (1, 7 - count_v)])
        self.assertIn("SurfaceCVs(", repr(cvs))
        self.assertIn("count=", repr(cvs))
        for index, error in (((count_u, 0), IndexError), ((0, -1), IndexError), ((1, 2, 3), ValueError),
                             ((1, True), TypeError), (count_u * count_v, IndexError), ("1", TypeError)):
            with self.subTest(index=index):
                with self.assertRaises(error):
                    SurfaceCV(shape, index)
        with self.assertRaises(TypeError):
            SurfaceCV(self.cube()[1], 0)

    def test_resolve_from_names_and_selection(self):
        shape = self.surface()
        name = shape.getFullName()
        resolved = Object(name + ".cv[1][4]")
        self.assertIsInstance(resolved, SurfaceCV)
        self.assertEqual(resolved.getMultiIndex(), (1, 4))
        found = mlib.ls(name + ".cv[0:1][2]", flatten=True)
        self.assertEqual([item.getMultiIndex() for item in found], [(0, 2), (1, 2)])
        mlib.select(SurfaceCVs(shape, [(0, 0), (3, 1)]))
        self.assertEqual(_flat(cmds.ls(selection=True)), {"cv[0][0]", "cv[3][1]"})

    def test_positions_and_write(self):
        shape = self.surface()
        name = shape.getFullName()
        cv = SurfaceCV(shape, (1, 2))
        self.assertVectorAlmostEqual(cv.getPosition(), cmds.pointPosition(name + ".cv[1][2]", local=True))
        self.assertVectorAlmostEqual(cv.getPosition(ws=True), cmds.pointPosition(name + ".cv[1][2]", world=True))
        cvs = SurfaceCVs(shape, [(0, 0), (1, 2)])
        self.assertEqual(len(cvs.getPosition(worldSpace=True)), 2)
        before = cv.getPosition()
        self.flushUndo()
        self.assertIs(cv.setPosition((5.0, 6.0, 7.0), worldSpace=True), cv)
        self.assertUndoesInOneStep(
            lambda: self.assertVectorAlmostEqual(cv.getPosition(), before),
            lambda: self.assertVectorAlmostEqual(cmds.pointPosition(name + ".cv[1][2]", world=True), (5, 6, 7)))
        self.flushUndo()
        cvs.moveBy((0.0, 1.0, 0.0), fast=True)
        self.assertUndoEmpty()
        self.assertVectorAlmostEqual(cv.getPosition(), before + Vector(0, 1, 0))
        self.flushUndo()
        cvs.mirror("x")
        self.assertVectorAlmostEqual(cv.getPosition(), (-before.x, before.y + 1, before.z))
        cmds.undo()
        self.assertVectorAlmostEqual(cv.getPosition(), before + Vector(0, 1, 0))
        self.assertAlmostEqual(cvs.getCenter().y, (shape.getCvPositions()[0].y + cv.getPosition().y) / 2.0)

    def test_periodic_surface(self):
        transform = cmds.sphere(name=self.name("sphere#"), sections=8, spans=4, constructionHistory=False)[0]
        shape = mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])
        count_u, count_v = shape.getNumCVs()
        cvs = SurfaceCVs(shape)
        self.assertEqual(len(cvs), count_u * count_v)
        duplicate = SurfaceCV(shape, (2, 9))
        self.assertTrue(duplicate.getFullName().endswith(".cv[2][1]"))
        self.assertEqual(duplicate.getMultiIndex(), (2, 9))
        self.assertVectorAlmostEqual(duplicate.getPosition(), SurfaceCV(shape, (2, 1)).getPosition())
        duplicate.setPosition((0.0, 3.0, 0.0))
        self.assertVectorAlmostEqual(SurfaceCV(shape, (2, 1)).getPosition(), (0, 3, 0))
        self.assertVectorAlmostEqual(cmds.pointPosition(shape.getFullName() + ".cv[2][1]", local=True), (0, 3, 0))
        SurfaceCV(shape, (3, 0)).setPosition((0.0, -3.0, 0.0), fast=True)
        self.assertVectorAlmostEqual(SurfaceCV(shape, (3, 8)).getPosition(), (0, -3, 0))
        self.assertEqual(len(_flat(cvs.getFullNames())), len(_flat(shape.getFullName() + ".cv[*][*]")))

    def test_fast_rejects_history_and_deleted(self):
        transform = cmds.nurbsPlane(name=self.name("hist#"), constructionHistory=True)[0]
        shape = mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])
        cv = SurfaceCV(shape, (0, 0))
        with self.assertRaises(NotImplementedError):
            cv.setPosition((1, 1, 1), fast=True)
        cv.setPosition((1, 1, 1))
        self.assertVectorAlmostEqual(cv.getPosition(), (1, 1, 1))
        cmds.delete(transform)
        for call in (cv.getPosition, cv.getFullName, cv.getMultiIndex):
            with self.subTest(call=call.__name__):
                with self.assertRaises(RuntimeError):
                    call()
        self.assertFalse(cv.isValid())
        self.assertEqual(repr(cv), "<SurfaceCV invalid>")


class LatticePointTest(_Case):
    """LatticePoint・LatticePoints。"""

    def test_index_names_positions(self):
        shape = self.lattice((2, 3, 4))
        name = shape.getFullName()
        points = LatticePoints(shape)
        self.assertEqual(len(points), 24)
        self.assertTrue(points.isComplete())
        self.assertEqual(_flat(points.getFullNames()), _flat(name + ".pt[*][*][*]"))
        for stu in ((0, 0, 0), (1, 0, 0), (0, 2, 1), (1, 2, 3)):
            with self.subTest(stu=stu):
                point = LatticePoint(shape, stu)
                self.assertEqual(point.getMultiIndex(), stu)
                self.assertEqual(point.index, stu[0] + 2 * (stu[1] + 3 * stu[2]))
                component = "{}.pt[{}][{}][{}]".format(name, *stu)
                self.assertTrue(point.getFullName().endswith(component.split("|")[-1].split(".")[-1]))
                self.assertVectorAlmostEqual(point.getPosition(), cmds.pointPosition(component, local=True))
                self.assertVectorAlmostEqual(point.getPosition(ws=True), cmds.pointPosition(component, world=True))
        resolved = Object(name + ".pt[1][2][3]")
        self.assertIsInstance(resolved, LatticePoint)
        self.assertEqual(resolved, LatticePoint(shape, 23))
        self.assertEqual([p.getMultiIndex() for p in mlib.ls(name + ".pt[0:1][0][0]", flatten=True)],
                         [(0, 0, 0), (1, 0, 0)])
        for index, error in (((2, 0, 0), IndexError), ((0, 0), ValueError), (24, IndexError), (-1, IndexError)):
            with self.subTest(index=index):
                with self.assertRaises(error):
                    LatticePoint(shape, index)

    def test_write_undo_fast(self):
        shape = self.lattice((2, 2, 2))
        name = shape.getFullName()
        points = LatticePoints(shape, [(0, 0, 0), (1, 1, 1)])
        before = points.getPosition()
        self.flushUndo()
        points.setPositions([(-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)])
        self.assertUndoesInOneStep(
            lambda: self.assertVectorAlmostEqual(points.getPosition()[1], before[1]),
            lambda: self.assertVectorAlmostEqual(cmds.pointPosition(name + ".pt[1][1][1]", local=True), (1, 1, 1)))
        point = LatticePoint(shape, (1, 0, 1))
        point.setPosition((3.0, 4.0, 5.0), ws=True)
        self.assertVectorAlmostEqual(cmds.pointPosition(name + ".pt[1][0][1]", world=True), (3, 4, 5))
        self.flushUndo()
        point.setPositionY(0.25, fast=True)
        self.assertUndoEmpty()
        self.assertAlmostEqual(cmds.pointPosition(name + ".pt[1][0][1]", local=True)[1], 0.25)
        self.assertVectorAlmostEqual(LatticePoint(shape, 0).getPosition(), before[0])
        divisions = [cmds.getAttr(name + "." + axis + "Divisions") for axis in "stu"]
        self.assertEqual(len(LatticePoints(shape)), divisions[0] * divisions[1] * divisions[2])
        cmds.delete(cmds.listRelatives(name, parent=True, fullPath=True))
        with self.assertRaises(RuntimeError):
            point.getPosition()
        self.assertEqual(repr(points), "<LatticePoints invalid>")


class VertexFaceTest(_Case):
    """VertexFace・VertexFaces。"""

    def test_index_names(self):
        _, mesh = self.cube()
        name = mesh.getFullName()
        all_faces = VertexFaces(mesh)
        self.assertEqual(len(all_faces), 24)
        self.assertTrue(all_faces.isComplete())
        self.assertEqual(_flat(all_faces.getFullNames()), _flat(name + ".vtxFace[*][*]"))
        item = VertexFace(mesh, (3, 1))
        self.assertEqual(item.getMultiIndex(), (3, 1))
        self.assertEqual(item.getVertex(), mesh.getVertex(3))
        self.assertEqual(item.getFace(), Face(mesh, 1))
        self.assertTrue(item.getFullName().endswith(".vtxFace[3][1]"))
        self.assertEqual(VertexFace(mesh, item.index), item)
        resolved = Object(name + ".vtxFace[3][1]")
        self.assertIsInstance(resolved, VertexFace)
        self.assertEqual(resolved, item)
        self.assertEqual(_names(mesh.getVertex(3).getVertexFaces()),
                         _flat(cmds.polyListComponentConversion(name + ".vtx[3]", toVertexFace=True)))
        self.assertEqual(_names(Face(mesh, 2).getVertexFaces()),
                         _flat(cmds.polyListComponentConversion(name + ".f[2]", toVertexFace=True)))
        self.assertEqual([vf.getMultiIndex()[0] for vf in Face(mesh, 2).getVertexFaces()],
                         list(Face(mesh, 2).getVertices().indices))
        for index, error in (((0, 1), IndexError), ((0, 6), IndexError), ((0,), ValueError), (24, IndexError)):
            with self.subTest(index=index):
                with self.assertRaises(error):
                    VertexFace(mesh, index)

    def test_normal(self):
        transform, mesh = self.cube()
        cmds.setAttr(transform + ".rotateZ", 90)
        name = mesh.getFullName()
        for vertex, face in ((2, 0), (7, 3)):
            with self.subTest(vertex=vertex, face=face):
                item = VertexFace(mesh, (vertex, face))
                expected = cmds.polyNormalPerVertex("{}.vtxFace[{}][{}]".format(name, vertex, face), query=True,
                                                    xyz=True)
                self.assertVectorAlmostEqual(item.getNormal(), expected, places=5)
                self.assertVectorAlmostEqual(item.getNormal(ws=True), Vector(expected).rotateBy(
                    om2.MEulerRotation(0, 0, math.pi / 2)), places=5)
        cmds.delete(transform)
        with self.assertRaises(RuntimeError):
            item.getNormal()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
