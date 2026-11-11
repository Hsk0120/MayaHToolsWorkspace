"""12.3.0 で足したメソッド・引数の名前を確かめる。

- NurbsSurface: 数・次数・形式・パラメーター範囲、CV の位置の取得・設定(Undo 1回/fast)、最近点・位置・法線(cmds の
  closestPointOnSurface・pointOnSurface と突き合わせ)、不正な入力の例外。
- GeometryFilter.getGeometry: skinCluster・cluster・deltaMush で変形する形状を返す。
- Transform.getRotateOrder/setRotateOrder: 向きを保つ変更(xform の preserve と一致)と保たない変更、Undo 1回。
- Transform.getMatrix/getQuaternion/setQuaternion の長名(parent・inverse・rotateAxis・rotate・jointOrient)が
  短縮名と同じ結果になり、同時指定は TypeError。setQuaternion・getClosestAxisToVector の入力検証。
- Vector.projected/orthogonal/orthogonalIt。
- Face.getCenter/getNormal/getArea、Edge.getLength/getCenter、Vertex.getNormal(cmds・om2 と突き合わせ)。
- PointComponent(s).moveBy(Undo 1回・fast)と PointComponents.getCenter。
- Joint.getPreferredAngle、AnimCurve.isStatic、Constraint.removeTarget(Undo 1回・未登録は ValueError)。
"""

import math
import sys
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from support.specCase import NamespaceCase


class _Case(NamespaceCase):
    """形状を作る補助。"""

    PREFIX = "mlibV123_"

    def surface(self):
        """2x3 スパン・3次の NURBS 平面を作り、シェイプのラッパーを返す。"""
        transform = cmds.nurbsPlane(name=self.name("plane#"), width=4, lengthRatio=1.5, patchesU=2, patchesV=3,
                                    degree=3, axis=(0, 1, 0), constructionHistory=False)[0]
        cmds.setAttr(transform + ".translate", 1, 2, 3)
        return mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])

    def cube(self):
        """1辺2cm の polyCube を作り、(transform, shape) のラッパーを返す。"""
        transform = cmds.polyCube(name=self.name("cube#"), width=2, height=2, depth=2, constructionHistory=False)[0]
        shape = cmds.listRelatives(transform, shapes=True, fullPath=True)[0]
        return mlib.getNode(transform), mlib.getNode(shape)


class NurbsSurfaceTest(_Case):
    """NurbsSurface の照会と CV の書込み。"""

    def test_counts_and_range(self):
        """CV 数・スパン数・次数・形式・パラメーター範囲がアトリビュート・om2 と一致する。"""
        shape = self.surface()
        name = shape.getFullName()
        self.assertEqual(shape.getNumSpans(), (cmds.getAttr(name + ".spansU"), cmds.getAttr(name + ".spansV")))
        self.assertEqual(shape.getDegree(), (cmds.getAttr(name + ".degreeU"), cmds.getAttr(name + ".degreeV")))
        self.assertEqual(shape.getNumCVs(), (2 + 3, 3 + 3))
        self.assertEqual(shape.getForm(), (om2.MFnNurbsSurface.kOpen, om2.MFnNurbsSurface.kOpen))
        (u0, u1), (v0, v1) = shape.getParamRange()
        self.assertSequenceAlmostEqual((u0, u1), cmds.getAttr(name + ".minMaxRangeU")[0])
        self.assertSequenceAlmostEqual((v0, v1), cmds.getAttr(name + ".minMaxRangeV")[0])

    def test_cv_positions_match_cmds(self):
        """getCvPositions は cv[u][v] の順で、ローカルとワールドが pointPosition と一致する。"""
        shape = self.surface()
        name = shape.getFullName()
        count_u, count_v = shape.getNumCVs()
        local = shape.getCvPositions()
        world = shape.getCvPositions(ws=True)
        self.assertEqual(len(local), count_u * count_v)
        for u, v in ((0, 0), (1, 2), (count_u - 1, count_v - 1)):
            with self.subTest(u=u, v=v):
                index = u * count_v + v
                self.assertSequenceAlmostEqual(local[index], cmds.pointPosition(f"{name}.cv[{u}][{v}]", local=True))
                self.assertSequenceAlmostEqual(world[index], cmds.pointPosition(f"{name}.cv[{u}][{v}]", world=True))

    def test_set_cv_positions_undo_and_fast(self):
        """setCvPositions は全CVを書き、通常はUndo 1回で戻り、fast はUndoに残らない。ワールド指定も往復する。"""
        shape = self.surface()
        before = shape.getCvPositions()
        moved = [mlib.Vector(p) + mlib.Vector(0.0, 1.0, 0.0) for p in before]
        self.flushUndo()
        self.assertIs(shape.setCvPositions(moved), shape)
        self.assertUndoesInOneStep(
            lambda: self.assertSequenceAlmostEqual(shape.getCvPositions()[3], before[3]),
            lambda: self.assertSequenceAlmostEqual(shape.getCvPositions()[3], moved[3]))
        world = shape.getCvPositions(worldSpace=True)
        shape.setCvPositions([mlib.Vector(p) + mlib.Vector(1.0, 0.0, 0.0) for p in world], worldSpace=True)
        self.assertSequenceAlmostEqual(shape.getCvPositions(ws=True)[5], mlib.Vector(world[5]) + mlib.Vector(1, 0, 0))
        self.flushUndo()
        shape.setCvPositions(before, fast=True)
        self.assertUndoEmpty()
        self.assertSequenceAlmostEqual(shape.getCvPositions()[7], before[7])

    def test_set_cv_positions_errors(self):
        """点の数・型・fast の型の誤りは例外で、CV は変わらない。履歴のある形状の fast は NotImplementedError。"""
        shape = self.surface()
        before = shape.getCvPositions()
        for points, flags, error in ((before[:-1], {}, ValueError), (["abc"] * len(before), {}, TypeError),
                                     (before, {"fast": 1}, TypeError), (before, {"worldSpace": True, "ws": True},
                                                                         TypeError)):
            with self.subTest(flags=flags, error=error):
                with self.assertRaises(error):
                    shape.setCvPositions(points, **flags)
                self.assertSequenceAlmostEqual(shape.getCvPositions()[4], before[4])
        transform = cmds.nurbsPlane(name=self.name("history#"), constructionHistory=True)[0]
        history = mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])
        with self.assertRaises(NotImplementedError):
            history.setCvPositions(history.getCvPositions(), fast=True)

    def test_closest_point_and_params_match_cmds(self):
        """最近点・(u, v) の位置・法線が closestPointOnSurface・pointOnSurface と一致する。"""
        shape = self.surface()
        name = shape.getFullName()
        found, u, v = shape.getClosestPoint((1.5, 9.0, 3.5), worldSpace=True)
        node = cmds.createNode("closestPointOnSurface", name=self.name("cpos#"))
        cmds.connectAttr(name + ".worldSpace[0]", node + ".inputSurface")
        cmds.setAttr(node + ".inPosition", 1.5, 9.0, 3.5)
        self.assertSequenceAlmostEqual(found, cmds.getAttr(node + ".result.position")[0], places=5)
        self.assertAlmostEqual(u, cmds.getAttr(node + ".result.parameterU"), places=5)
        self.assertAlmostEqual(v, cmds.getAttr(node + ".result.parameterV"), places=5)
        for space, flag in ((False, {}), (True, {"ws": True})):
            with self.subTest(worldSpace=space):
                point = shape.getPointAtParam(0.5, 1.0, **flag)
                # pointOnSurface はワールド座標を返す(transform は平行移動 (1, 2, 3) だけ)。
                expected = cmds.pointOnSurface(name, parameterU=0.5, parameterV=1.0, position=True)
                if not space:
                    expected = [value - offset for value, offset in zip(expected, (1, 2, 3))]
                self.assertSequenceAlmostEqual(point, expected, places=6)
                normal = shape.getNormalAtParam(0.5, 1.0, **flag)
                self.assertAlmostEqual(normal.length(), 1.0)
                self.assertSequenceAlmostEqual(
                    normal, cmds.pointOnSurface(name, parameterU=0.5, parameterV=1.0, normalizedNormal=True), places=6)

    def test_param_errors_and_empty_shape(self):
        """範囲外・有限でないパラメーターは ValueError、数値以外は TypeError、形状データの無い曲面は RuntimeError。"""
        shape = self.surface()
        (u0, u1), (v0, v1) = shape.getParamRange()
        for u, v, error in ((u1 + 1.0, v0, ValueError), (u0, float("nan"), ValueError), ("a", v0, TypeError)):
            with self.subTest(u=u, v=v):
                with self.assertRaises(error):
                    shape.getPointAtParam(u, v)
                with self.assertRaises(error):
                    shape.getNormalAtParam(u, v)
        with self.assertRaises(TypeError):
            shape.getClosestPoint((0, 0, 0), worldSpace=1)
        empty = mlib.createNode("nurbsSurface", name=self.name("empty#"))
        self.assertIsInstance(empty, mlib.NurbsSurface)
        for call in (empty.getNumCVs, empty.getParamRange, empty.getCvPositions):
            with self.subTest(call=call.__name__):
                with self.assertRaises(RuntimeError):
                    call()


class GeometryFilterGeometryTest(_Case):
    """GeometryFilter.getGeometry はすべてのデフォーマーで変形する形状を返す。"""

    def test_get_geometry(self):
        """skinCluster・cluster・deltaMush の getGeometry が変形する形状(deformer -q -g)と一致する。"""
        transform, shape = self.cube()
        cmds.select(clear=True)
        joint = cmds.joint(name=self.name("jnt#"))
        skin = mlib.getNode(cmds.skinCluster(joint, transform.getFullName(), name=self.name("skin#"))[0])
        cluster = mlib.getNode(cmds.cluster(transform.getFullName(), name=self.name("cluster#"))[0])
        mush = mlib.getNode(cmds.deltaMush(transform.getFullName(), name=self.name("mush#"))[0])
        expected = cmds.ls(cmds.deformer(skin.getFullName(), query=True, geometry=True), long=True)
        for deformer in (skin, cluster, mush):
            with self.subTest(deformer=deformer.getType()):
                self.assertIsInstance(deformer, mlib.GeometryFilter)
                self.assertEqual([node.getFullName() for node in deformer.getGeometry()], expected)
        for name in cmds.ls(type="dagPose") or []:
            if not cmds.listConnections(name + ".members"):
                cmds.delete(name)


class RotateOrderTest(_Case):
    """Transform.getRotateOrder/setRotateOrder。"""

    def test_set_rotate_order_preserve(self):
        """preserve=True は向きを保ち(xform の preserve と同じ rotate)、Undo 1回で戻る。"""
        node = mlib.getNode(self.make("transform", "roo#"))
        twin = self.make("transform", "twin#")
        for name in (node.getFullName(), twin):
            cmds.setAttr(name + ".rotate", 30, 45, 60)
        before = node.getMatrix(worldSpace=True)
        self.assertEqual(node.getRotateOrder(), "xyz")
        cmds.xform(twin, rotateOrder="zxy", preserve=True)
        self.flushUndo()
        self.assertIs(node.setRotateOrder("ZXY"), node)
        self.assertEqual(node.getRotateOrder(), "zxy")
        self.assertSequenceAlmostEqual(cmds.getAttr(node.getFullName() + ".rotate")[0], cmds.getAttr(twin + ".rotate")[0],
                                       places=6)
        self.assertTrue(node.getMatrix(worldSpace=True).isEquivalent(before, 1e-9))
        self.assertUndoesInOneStep(lambda: self.assertEqual(node.getRotateOrder(), "xyz"),
                                   lambda: self.assertEqual(node.getRotateOrder(), "zxy"))

    def test_set_rotate_order_without_preserve(self):
        """preserve=False は rotateOrder だけを変え、rotate はそのまま(番号でも指定できる)。"""
        node = mlib.getNode(self.make("transform", "roo#"))
        cmds.setAttr(node.getFullName() + ".rotate", 30, 45, 60)
        node.setRotateOrder(5, preserve=False)
        self.assertEqual(node.getRotateOrder(), "zyx")
        self.assertSequenceAlmostEqual(cmds.getAttr(node.getFullName() + ".rotate")[0], (30, 45, 60), places=6)

    def test_set_rotate_order_errors(self):
        """未対応の順序は ValueError、preserve の型違いは TypeError で、rotateOrder は変わらない。"""
        node = mlib.getNode(self.make("transform", "roo#"))
        for order, flags, error in (("abc", {}, ValueError), (6, {}, ValueError), ("xyz", {"preserve": 1}, TypeError)):
            with self.subTest(order=order, flags=flags):
                with self.assertRaises(error):
                    node.setRotateOrder(order, **flags)
                self.assertEqual(node.getRotateOrder(), "xyz")


class LongArgumentNameTest(_Case):
    """getMatrix・getQuaternion・setQuaternion の長名と、入力の検証。"""

    def setUp(self):
        super().setUp()
        cmds.select(clear=True)
        self.parent = cmds.joint(name=self.name("parent#"), position=(1, 0, 0))
        self.child = mlib.getNode(cmds.joint(name=self.name("child#"), position=(2, 1, 0)))
        cmds.setAttr(self.parent + ".rotate", 10, 20, 30)
        cmds.setAttr(self.child.getFullName() + ".rotate", 5, 15, 25)
        cmds.setAttr(self.child.getFullName() + ".rotateAxis", 3, 6, 9)

    def test_get_matrix_long_names(self):
        """parent・inverse が p・inv と同じ結果になり、同時指定は TypeError。"""
        for space in (False, True):
            for long, short in (({"parent": True}, {"p": True}), ({"inverse": True}, {"inv": True}),
                                ({"parent": True, "inverse": True}, {"p": True, "inv": True})):
                with self.subTest(worldSpace=space, flags=long):
                    self.assertTrue(self.child.getMatrix(space, **long).isEquivalent(
                        self.child.getMatrix(space, **short), 1e-12))
        for flags in ({"parent": True, "p": True}, {"inverse": False, "inv": True}):
            with self.subTest(flags=flags):
                with self.assertRaises(TypeError):
                    self.child.getMatrix(**flags)

    def test_quaternion_long_names(self):
        """rotateAxis・rotate・jointOrient が ra・r・jo と同じ結果になり、同時指定は TypeError。"""
        for space in (False, True):
            with self.subTest(worldSpace=space):
                self.assertSameRotation(
                    self.child.getQuaternion(space, rotateAxis=True, rotate=True, jointOrient=True),
                    self.child.getQuaternion(space, ra=True, r=True, jo=True))
        self.assertSameRotation(self.child.getQuaternion(rotate=False), self.child.getQuaternion(r=False))
        value = mlib.Quaternion(0.1, 0.2, 0.3, 0.9).normal()
        self.assertSequenceAlmostEqual(self.child.setQuaternion(value, rotate=False, get=True),
                                       self.child.setQuaternion(value, r=False, get=True))
        for call in (lambda: self.child.getQuaternion(rotate=True, r=True),
                     lambda: self.child.setQuaternion(value, jointOrient=True, jo=True)):
            with self.assertRaises(TypeError):
                call()

    def test_set_quaternion_value_errors(self):
        """クォータニオンでも数値の列でもない値は TypeError、成分数・有限でない値は ValueError で、rotate は変わらない。"""
        before = cmds.getAttr(self.child.getFullName() + ".rotate")[0]
        for value, error in (("abcd", TypeError), (5, TypeError), (("a", 0, 0, 1), TypeError),
                             ((0, 0, 0), ValueError), ((0, 0, 0, float("inf")), ValueError)):
            with self.subTest(value=value):
                with self.assertRaises(error):
                    self.child.setQuaternion(value)
                self.assertSequenceAlmostEqual(cmds.getAttr(self.child.getFullName() + ".rotate")[0], before)

    def test_closest_axis_errors(self):
        """getClosestAxisToVector は不正な型を TypeError、成分数・ゼロベクトルを ValueError にする。"""
        self.assertIn(self.child.getClosestAxisToVector((1, 0, 0)), ("x", "y", "z", "-x", "-y", "-z"))
        for value, flags, error in (("abc", {}, TypeError), ((1, 0), {}, ValueError), ((0, 0, 0), {}, ValueError),
                                    ((1, 0, 0), {"includeNegative": 1}, TypeError)):
            with self.subTest(value=value, flags=flags):
                with self.assertRaises(error):
                    self.child.getClosestAxisToVector(value, **flags)


class VectorProjectionTest(NamespaceCase):
    """Vector.projected/orthogonal/orthogonalIt。"""

    def test_projection(self):
        """軸の成分と直交する成分に分かれ、合計が元の値になる。軸の長さは結果に影響しない。"""
        value = mlib.Vector(3.0, 4.0, 5.0)
        for axis in ((0, 2, 0), mlib.Vector(1, 1, 0), om2.MVector(0, 0, -3)):
            with self.subTest(axis=axis):
                along = value.projected(axis)
                across = value.orthogonal(axis)
                self.assertAlmostEqual(across.dot(axis), 0.0)
                self.assertAlmostEqual(along.cross(axis).length(), 0.0)
                self.assertTrue((along + across).isEquivalent(value, 1e-12))
        self.assertTrue(value.orthogonal((0, 1, 0)).isEquivalent((3, 0, 5)))
        self.assertTrue(mlib.Vector(0, 2, 0).orthogonal((0, 1, 0)).isEquivalent((0, 0, 0)))

    def test_orthogonal_it_and_errors(self):
        """orthogonalIt は自身を書き換えて返し、ゼロ軸は ValueError で自身を変えない。派生型でも基底 Vector を返す。"""
        value = mlib.Translate(1.0, 2.0, 3.0)
        self.assertIs(value.orthogonalIt((1, 0, 0)), value)
        self.assertSequenceAlmostEqual(value, (0, 2, 3))
        self.assertIs(type(mlib.Translate(1, 2, 3).orthogonal((0, 0, 1))), mlib.Vector)
        for method in ("projected", "orthogonal", "orthogonalIt"):
            with self.subTest(method=method):
                with self.assertRaises(ValueError):
                    getattr(value, method)((0, 0, 0))
                self.assertSequenceAlmostEqual(value, (0, 2, 3))


class MeshComponentQueryTest(_Case):
    """Face・Edge・Vertex の幾何の照会。"""

    def test_face_queries(self):
        """面の中心・法線・面積が polyInfo・om2 と一致し、ワールド指定は transform を含む。Faces は各面のリスト。"""
        transform, shape = self.cube()
        cmds.setAttr(transform.getFullName() + ".translate", 0, 5, 0)
        cmds.setAttr(transform.getFullName() + ".scale", 2, 2, 2)
        face = shape.getFace(1)  # polyCube の f[1] は +Y の面。
        self.assertSequenceAlmostEqual(face.getCenter(), (0, 1, 0))
        self.assertSequenceAlmostEqual(face.getCenter(ws=True), (0, 7, 0))
        self.assertSequenceAlmostEqual(face.getNormal(), (0, 1, 0))
        self.assertSequenceAlmostEqual(face.getNormal(worldSpace=True), (0, 1, 0))
        self.assertAlmostEqual(face.getArea(), 4.0)
        self.assertAlmostEqual(face.getArea(worldSpace=True), 16.0)
        centers = shape.getFaces([0, 1]).getCenter()
        self.assertEqual(len(centers), 2)
        self.assertSequenceAlmostEqual(centers[1], (0, 1, 0))

    def test_edge_and_vertex_queries(self):
        """エッジの長さ・中点と頂点の法線(om2 の getVertexNormal と同じ)。"""
        transform, shape = self.cube()
        cmds.setAttr(transform.getFullName() + ".scale", 3, 1, 1)
        edge = shape.getEdge(0)
        a, b = [cmds.pointPosition(f"{shape.getFullName()}.vtx[{i}]", world=True) for i in
                cmds.polyInfo(edge.getFullName(), edgeToVertex=True)[0].split(":")[1].split()[:2]]
        self.assertAlmostEqual(edge.getLength(), 2.0)
        self.assertAlmostEqual(edge.getLength(ws=True), math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b))))
        self.assertSequenceAlmostEqual(edge.getCenter(worldSpace=True), [(x + y) / 2 for x, y in zip(a, b)])
        fn = om2.MFnMesh(shape.mpath())
        for weighted in (False, True):
            with self.subTest(angleWeighted=weighted):
                normal = shape.getVertex(0).getNormal(angleWeighted=weighted)
                expected = om2.MVector(fn.getVertexNormal(0, weighted, om2.MSpace.kObject)).normal()
                self.assertSequenceAlmostEqual(normal, expected)
                self.assertAlmostEqual(normal.length(), 1.0)
        with self.assertRaises(TypeError):
            shape.getVertex(0).getNormal(angleWeighted=1)

    def test_query_errors(self):
        """範囲外の番号は IndexError、worldSpace の型違い・ws との同時指定は TypeError、削除済みは RuntimeError。"""
        transform, shape = self.cube()
        calls = (lambda c, **f: shape.getFace(c).getCenter(**f), lambda c, **f: shape.getFace(c).getNormal(**f),
                 lambda c, **f: shape.getFace(c).getArea(**f), lambda c, **f: shape.getEdge(c).getLength(**f),
                 lambda c, **f: shape.getEdge(c).getCenter(**f), lambda c, **f: shape.getVertex(c).getNormal(**f))
        for number, call in enumerate(calls):
            with self.subTest(call=number):
                with self.assertRaises(IndexError):
                    call(999)
                with self.assertRaises(TypeError):
                    call(0, worldSpace=1)
                with self.assertRaises(TypeError):
                    call(0, worldSpace=True, ws=True)
        face = shape.getFace(0)
        cmds.delete(transform.getFullName())
        with self.assertRaises(RuntimeError):
            face.getCenter()


class PointMoveTest(_Case):
    """PointComponent(s).moveBy と PointComponents.getCenter。"""

    def test_move_by_single_and_undo(self):
        """1点の moveBy は相対移動で、Undo 1回で戻り、fast はUndoに残らない。ワールド指定は親の変換を含む。"""
        transform, shape = self.cube()
        vertex = shape.getVertex(2)
        before = vertex.getPosition()
        self.flushUndo()
        self.assertIs(vertex.moveBy((1, 2, 3)), vertex)
        self.assertUndoesInOneStep(
            lambda: self.assertSequenceAlmostEqual(vertex.getPosition(), before),
            lambda: self.assertSequenceAlmostEqual(vertex.getPosition(), mlib.Vector(before) + mlib.Vector(1, 2, 3)))
        cmds.setAttr(transform.getFullName() + ".scale", 2, 2, 2)
        world = vertex.getPosition(worldSpace=True)
        vertex.moveBy((0, 1, 0), ws=True)
        self.assertSequenceAlmostEqual(vertex.getPosition(worldSpace=True), mlib.Vector(world) + mlib.Vector(0, 1, 0))
        self.flushUndo()
        vertex.moveBy((0, -1, 0), worldSpace=True, fast=True)
        self.assertUndoEmpty()
        self.assertSequenceAlmostEqual(vertex.getPosition(worldSpace=True), world)

    def test_move_by_collection_and_center(self):
        """複数の moveBy は全点を同じだけ動かし Undo 1回で戻る。getCenter は位置の平均。CV でも使える。"""
        transform, shape = self.cube()
        top = shape.getVertices([2, 3, 4, 5])
        before = top.getPosition()
        self.assertSequenceAlmostEqual(top.getCenter(), mlib.Vector(sum(p.x for p in before), sum(p.y for p in before),
                                                                    sum(p.z for p in before)) / 4.0)
        self.flushUndo()
        self.assertIs(top.moveBy(om2.MVector(0, 1, 0)), top)
        self.assertUndoesInOneStep(
            lambda: self.assertSequenceAlmostEqual(top.getPosition()[0], before[0]),
            lambda: self.assertSequenceAlmostEqual(top.getPosition()[0], mlib.Vector(before[0]) + mlib.Vector(0, 1, 0)))
        curve = mlib.getNode(cmds.listRelatives(cmds.curve(name=self.name("crv#"), degree=1,
                                                           point=[(0, 0, 0), (2, 0, 0), (2, 4, 0)]),
                                                shapes=True, fullPath=True)[0])
        self.assertSequenceAlmostEqual(curve.getCVs().getCenter(), (4.0 / 3.0, 4.0 / 3.0, 0))
        self.assertEqual(list(shape.getVertices([]).moveBy((1, 0, 0)).indices), [])

    def test_move_by_errors(self):
        """移動量の型・成分数・空の集まりの getCenter の誤りは例外で、位置は変わらない。"""
        transform, shape = self.cube()
        vertices = shape.getVertices([0, 1])
        before = vertices.getPosition()
        for offset, flags, error in (("abc", {}, TypeError), ((1, 2), {}, ValueError),
                                     ((1, 0, float("nan")), {}, ValueError), ((1, 0, 0), {"fast": 1}, TypeError)):
            with self.subTest(offset=offset, flags=flags):
                with self.assertRaises(error):
                    vertices.moveBy(offset, **flags)
                with self.assertRaises(error):
                    vertices[0].moveBy(offset, **flags)
                self.assertSequenceAlmostEqual(vertices.getPosition()[0], before[0])
        with self.assertRaises(ValueError):
            shape.getVertices([]).getCenter()


class RigQueryAdditionsTest(_Case):
    """Joint.getPreferredAngle・AnimCurve.isStatic・Constraint.removeTarget。"""

    def test_preferred_angle(self):
        """setPreferredAngle で設定した値を度・ラジアンで読み戻せる。"""
        cmds.select(clear=True)
        joint = mlib.getNode(cmds.joint(name=self.name("jnt#")))
        joint.setPreferredAngle((10, 20, 30))
        self.assertSequenceAlmostEqual(joint.getPreferredAngle(), (10, 20, 30))
        self.assertSequenceAlmostEqual(joint.getPreferredAngle(unit="rad"), [math.radians(v) for v in (10, 20, 30)])
        with self.assertRaises(ValueError):
            joint.getPreferredAngle(unit="furlong")

    def test_anim_curve_is_static(self):
        """同じ値のキーだけのカーブは一定、値の違うキーがあれば一定でない。"""
        node = self.make("transform", "keyed#")
        cmds.setKeyframe(node, attribute="tx", time=1, value=2.0)
        cmds.setKeyframe(node, attribute="tx", time=10, value=2.0)
        cmds.setKeyframe(node, attribute="ty", time=1, value=0.0)
        cmds.setKeyframe(node, attribute="ty", time=10, value=5.0)
        flat = mlib.getNode(cmds.listConnections(node + ".tx", source=True)[0])
        moving = mlib.getNode(cmds.listConnections(node + ".ty", source=True)[0])
        self.assertIs(flat.isStatic(), True)
        self.assertIs(moving.isStatic(), False)

    def test_constraint_remove_target(self):
        """removeTarget はターゲットを外し、Undo 1回で戻る。未登録・未指定は例外で何も外さない。"""
        a, b, driven = (self.make("transform", text) for text in ("a#", "b#", "driven#"))
        constraint = mlib.getNode(cmds.parentConstraint(a, b, driven)[0])

        def names():
            return [node.getFullName() for node in constraint.getTargets()]
        both = names()
        self.flushUndo()
        self.assertIs(constraint.removeTarget(b), constraint)
        self.assertUndoesInOneStep(lambda: self.assertEqual(names(), both),
                                   lambda: self.assertEqual(names(), both[:1]))
        stranger = self.make("transform", "stranger#")
        for args, error in (((stranger,), ValueError), ((), TypeError)):
            with self.subTest(args=args):
                with self.assertRaises(error):
                    constraint.removeTarget(*args)
                self.assertEqual(names(), both)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
