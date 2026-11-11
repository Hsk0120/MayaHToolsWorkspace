"""頂点・CV・UVの座標の書込みと、Mesh・NurbsCurve・Transformの形状の反転を確かめる。

対象: ``PointComponent.setPosition/X/Y/Z``・``PointComponents.setPosition/setPositions/setPositionX/Y/Z/mirror``・
``UV.setPosition/setU/setV``・``UVs.setPosition/setPositions/setU/setV``・``Mesh.mirror``・``NurbsCurve.mirror``・
``Transform.mirrorGeometry``。

各メソッドについて、オブジェクト/ワールド空間(移動・回転・非一様スケールしたTransform)、UIの距離単位に
よらないcmの値、Undo 1 回での復元、fast の結果の一致と Undo に積まないこと、不正な入力の例外型と
シーンを変えないことを確かめる。期待値は mlib を通さず OpenMaya から読む。
"""

import sys
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from support.specCase import NamespaceCase

#: Meshの点は単精度で保持されるため、比べる桁数を抑える。
PLACES = 4


def _path(name):
    """名前からDAGパスを取得する。"""
    selection = om2.MSelectionList()
    selection.add(name)
    return selection.getDagPath(0)


def _points(name, worldSpace=False):
    """MeshまたはNurbsCurveの全点をcmのXYZのlistで返す(mlibを通さない)。"""
    path = _path(name)
    space = om2.MSpace.kWorld if worldSpace else om2.MSpace.kObject
    if path.node().hasFn(om2.MFn.kMesh):
        values = om2.MFnMesh(path).getPoints(space)
    else:
        values = om2.MFnNurbsCurve(path).cvPositions(space)
    return [(point.x, point.y, point.z) for point in values]


def _uvs(name, uvSet=None):
    """現在(または指定)のUVセットの全UVを(u, v)のlistで返す(mlibを通さない)。"""
    fn = om2.MFnMesh(_path(name))
    us, vs = fn.getUVs(uvSet or fn.currentUVSetName())
    return list(zip(us, vs))


def _mirrored(points, indices, axis, pivot):
    """指定番号の点の指定軸を ``2 * pivot - 値`` にした新しい点列を返す。"""
    result = [list(point) for point in points]
    for index in indices:
        result[index][axis] = 2.0 * pivot[axis] - result[index][axis]
    return [tuple(point) for point in result]


class _Case(NamespaceCase):
    """移動・回転・非一様スケールしたcubeとカーブを作る補助。"""

    def assertPointsAlmostEqual(self, actual, expected, places=PLACES):
        actual, expected = list(actual), list(expected)
        self.assertEqual(len(actual), len(expected))
        for index, (a, e) in enumerate(zip(actual, expected)):
            for axis in range(len(e)):
                self.assertAlmostEqual(a[axis], e[axis], places=places,
                                       msg=f"point {index} axis {axis}: {tuple(a)} != {tuple(e)}")

    def cube(self, text="cube", history=False):
        """移動・回転・非一様スケールしたpolyCubeのShapeを返す。"""
        transform = cmds.polyCube(name=self.name(text), constructionHistory=history)[0]
        cmds.xform(transform, translation=(1, 2, 3), rotation=(10, 30, 45), scale=(2, 1, 0.5))
        return mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])

    def curve(self, text="crv", periodic=False):
        """移動・回転したnurbsCurve(3次)のShapeを返す。periodic=Trueは周期カーブ。"""
        points = [(0, 0, 0), (2, 1, 0), (3, 0, 2), (1, -1, 3), (-1, 0, 2)]
        if periodic:
            transform = cmds.curve(name=self.name(text), degree=3, periodic=True,
                                   point=points + points[:3], knot=list(range(-2, 8)))
        else:
            transform = cmds.curve(name=self.name(text), degree=3, point=points)
        cmds.xform(transform, translation=(-1, 2, 0), rotation=(0, 0, 30), scale=(1, 2, 1))
        return mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])

    def check_undo(self, name, action, uv=False):
        """actionがUndo 1回で戻り、キューに他の項目を残さないことを確かめる。"""
        read = _uvs if uv else _points
        before = read(name)
        self.flushUndo()
        action()
        after = read(name)
        self.assertNotEqual(after, before)
        self.assertUndoesInOneStep(lambda: self.assertPointsAlmostEqual(read(name), before, places=6),
                                   lambda: self.assertPointsAlmostEqual(read(name), after, places=6))

    def check_fast(self, make, action, uv=False):
        """同じ形状の2つへ通常とfastで同じ操作をし、結果の一致とfastがUndoに積まないことを確かめる。"""
        read = _uvs if uv else _points
        normal, fast = make("normal"), make("fast")
        action(normal, False)
        self.flushUndo()
        action(fast, True)
        self.assertUndoEmpty()
        self.assertPointsAlmostEqual(read(fast.getFullName()), read(normal.getFullName()))
        if not uv:
            self.assertPointsAlmostEqual(read(fast.getFullName(), True), read(normal.getFullName(), True))

    def check_rejects(self, name, cases, uv=False):
        """不正な入力が指定の例外型で拒否され、形状を変えないことを確かめる。"""
        read = _uvs if uv else _points
        before = read(name)
        for error, action in cases:
            with self.subTest(error=error.__name__, action=action):
                with self.assertRaises(error):
                    action()
                self.assertEqual(read(name), before)


class PointComponentTest(_Case):
    """単数の頂点・CVの書込み。"""

    def test_set_position_object_and_world_space(self):
        shape = self.cube()
        name = shape.getFullName()
        vertex = shape.getVertex(2)
        self.assertIs(vertex.setPosition((1.5, -2.0, 0.25)), vertex)
        self.assertPointsAlmostEqual([_points(name)[2]], [(1.5, -2.0, 0.25)])
        vertex.setPosition(om2.MPoint(4, 5, 6), worldSpace=True)
        self.assertPointsAlmostEqual([_points(name, True)[2]], [(4, 5, 6)])
        cv = self.curve().getCV(1)
        cv.setPosition((7, 8, 9), worldSpace=True)
        self.assertPointsAlmostEqual([_points(cv.shape.getFullName(), True)[1]], [(7, 8, 9)])
        cv.setPosition((1, 2, 3))
        self.assertPointsAlmostEqual([_points(cv.shape.getFullName())[1]], [(1, 2, 3)])

    def test_set_position_axis_keeps_other_axes_in_the_same_space(self):
        shape = self.cube()
        name = shape.getFullName()
        vertex = shape.getVertex(3)
        for axis, method in enumerate((vertex.setPositionX, vertex.setPositionY, vertex.setPositionZ)):
            for worldSpace in (False, True):
                with self.subTest(axis=axis, worldSpace=worldSpace):
                    before = list(_points(name, worldSpace)[3])
                    self.assertIs(method(2.5, worldSpace=worldSpace), vertex)
                    before[axis] = 2.5
                    self.assertPointsAlmostEqual([_points(name, worldSpace)[3]], [before])

    def test_values_are_cm_regardless_of_the_linear_unit(self):
        shape = self.cube()
        name = shape.getFullName()
        cmds.currentUnit(linear="m")
        shape.getVertex(0).setPosition((100, 0, 0))
        shape.getVertex(1).setPositionY(50)
        points = _points(name)
        self.assertPointsAlmostEqual([points[0]], [(100, 0, 0)])
        self.assertAlmostEqual(points[1][1], 50, places=PLACES)
        self.assertAlmostEqual(shape.getVertex(0).getPositionX(), 100, places=PLACES)
        curve = self.curve()
        curve.getCV(0).setPosition((10, 20, 30), worldSpace=True)
        self.assertPointsAlmostEqual([_points(curve.getFullName(), True)[0]], [(10, 20, 30)])

    def test_undo_once(self):
        shape = self.cube()
        name = shape.getFullName()
        vertex = shape.getVertex(4)
        self.check_undo(name, lambda: vertex.setPosition((3, 3, 3)))
        self.check_undo(name, lambda: vertex.setPosition((3, 1, 3), worldSpace=True))
        self.check_undo(name, lambda: vertex.setPositionX(-4))
        self.check_undo(name, lambda: vertex.setPositionY(-4, worldSpace=True))
        self.check_undo(name, lambda: vertex.setPositionZ(-4))
        curve = self.curve()
        self.check_undo(curve.getFullName(), lambda: curve.getCV(2).setPosition((5, 5, 5), worldSpace=True))

    def test_fast_matches_normal_without_undo(self):
        for method, args in (("setPosition", ((1, 2, 3),)), ("setPositionX", (4.0,)), ("setPositionY", (-1.0,)),
                             ("setPositionZ", (0.5,))):
            for worldSpace in (False, True):
                with self.subTest(method=method, worldSpace=worldSpace):
                    self.check_fast(
                        lambda text: self.cube(text + "#"),
                        lambda shape, fast: getattr(shape.getVertex(5), method)(*args, worldSpace=worldSpace,
                                                                                fast=fast))
                    self.check_fast(
                        lambda text: self.curve(text + "#"),
                        lambda shape, fast: getattr(shape.getCV(1), method)(*args, worldSpace=worldSpace,
                                                                            fast=fast))

    def test_fast_periodic_curve_keeps_overlapping_cvs(self):
        curve = self.curve(periodic=True)
        name = curve.getFullName()
        count = len(_points(name))
        curve.getCV(count - 1).setPosition((9, 9, 9), fast=True)  # 末尾の重複CVは先頭の独立CVを書く
        points = _points(name)
        self.assertPointsAlmostEqual([points[2], points[count - 1]], [(9, 9, 9), (9, 9, 9)])

    def test_invalid_inputs_do_not_change_the_shape(self):
        shape = self.cube()
        vertex = shape.getVertex(0)
        self.check_rejects(shape.getFullName(), (
            (TypeError, lambda: vertex.setPosition("abc")),
            (TypeError, lambda: vertex.setPosition(1.0)),
            (ValueError, lambda: vertex.setPosition((1, 2))),
            (ValueError, lambda: vertex.setPosition((1, 2, float("inf")))),
            (TypeError, lambda: vertex.setPosition((1, 2, 3), worldSpace=1)),
            (TypeError, lambda: vertex.setPosition((1, 2, 3), fast=1)),
            (TypeError, lambda: vertex.setPosition((1, 2, 3), worldSpace=True, ws=True)),
            (TypeError, lambda: vertex.setPositionX("1")),
            (TypeError, lambda: vertex.setPositionY(True)),
            (ValueError, lambda: vertex.setPositionZ(float("nan"))),
        ))

    def test_fast_rejects_input_history_and_singular_world_matrix(self):
        shape = self.cube(history=True)
        self.check_rejects(shape.getFullName(), (
            (NotImplementedError, lambda: shape.getVertex(0).setPosition((1, 2, 3), fast=True)),
        ))
        flat = self.cube("flat")
        cmds.setAttr(flat.getTransform().getFullName() + ".scaleX", 0)
        self.check_rejects(flat.getFullName(), (
            (ValueError, lambda: flat.getVertex(0).setPosition((1, 2, 3), worldSpace=True)),
            (ValueError, lambda: flat.getVertex(0).setPosition((1, 2, 3), worldSpace=True, fast=True)),
        ))


class PointComponentsTest(_Case):
    """頂点・CVの集まりの書込み。"""

    def test_set_positions_and_set_position(self):
        shape = self.cube()
        name = shape.getFullName()
        vertices = shape.getVertices([5, 1, 3])
        rows = [(1, 0, 0), (0, 2, 0), (0, 0, 3)]
        self.assertIs(vertices.setPositions(rows), vertices)
        points = _points(name)
        self.assertPointsAlmostEqual([points[5], points[1], points[3]], rows)
        vertices.setPositions(rows, worldSpace=True)
        points = _points(name, True)
        self.assertPointsAlmostEqual([points[5], points[1], points[3]], rows)
        vertices.setPosition((7, 7, 7), worldSpace=True)
        points = _points(name, True)
        self.assertPointsAlmostEqual([points[5], points[1], points[3]], [(7, 7, 7)] * 3)
        vertices.setPositions(vertices.getPosition())  # getPositionの結果をそのまま渡せる

    def test_set_position_axis_accepts_a_scalar_or_values(self):
        shape = self.curve()
        name = shape.getFullName()
        cvs = shape.getCVs([0, 2])
        for worldSpace in (False, True):
            with self.subTest(worldSpace=worldSpace):
                before = _points(name, worldSpace)
                cvs.setPositionY(1.5, worldSpace=worldSpace)
                cvs.setPositionZ([-1, -2], worldSpace=worldSpace)
                expected = [list(point) for point in before]
                expected[0][1:] = [1.5, -1]
                expected[2][1:] = [1.5, -2]
                self.assertPointsAlmostEqual(_points(name, worldSpace), expected)
        cvs.setPositionX((3, 4))
        self.assertEqual([round(x, 6) for x in cvs.getPositionX()], [3, 4])

    def test_values_are_cm_regardless_of_the_linear_unit(self):
        shape = self.cube()
        name = shape.getFullName()
        cmds.currentUnit(linear="m")
        shape.getVertices([0, 1]).setPositions([(100, 0, 0), (0, 200, 0)], worldSpace=True)
        self.assertPointsAlmostEqual(_points(name, True)[:2], [(100, 0, 0), (0, 200, 0)])
        before = _points(name)
        shape.getVertices([2, 3]).mirror("x", pivot=(50, 0, 0))
        self.assertPointsAlmostEqual(_points(name), _mirrored(before, [2, 3], 0, (50, 0, 0)))

    def test_mirror_subset(self):
        for worldSpace in (False, True):
            with self.subTest(worldSpace=worldSpace):
                shape = self.cube("cube#")
                name = shape.getFullName()
                before = _points(name, worldSpace)
                vertices = shape.getVertices([0, 2, 4])
                self.assertIs(vertices.mirror("XZ", worldSpace=worldSpace, pivot=(0, 1, 0)), vertices)
                self.assertPointsAlmostEqual(_points(name, worldSpace), _mirrored(before, [0, 2, 4], 1, (0, 1, 0)))

    def test_empty_collection_validates_but_does_nothing(self):
        shape = self.cube()
        empty = shape.getVertices([])
        self.flushUndo()
        self.assertIs(empty.setPositions([]), empty)
        self.assertIs(empty.setPosition((1, 2, 3)), empty)
        self.assertIs(empty.mirror(), empty)
        self.assertUndoEmpty()
        with self.assertRaises(ValueError):
            empty.setPosition((1, 2))
        with self.assertRaises(ValueError):
            empty.mirror("w")

    def test_undo_once(self):
        shape = self.cube()
        name = shape.getFullName()
        vertices = shape.getVertices([0, 1, 6])
        self.check_undo(name, lambda: vertices.setPositions([(1, 1, 1), (2, 2, 2), (3, 3, 3)]))
        self.check_undo(name, lambda: vertices.setPosition((4, 4, 4), worldSpace=True))
        self.check_undo(name, lambda: vertices.setPositionX(5))
        self.check_undo(name, lambda: vertices.setPositionY([1, 2, 3], worldSpace=True))
        self.check_undo(name, lambda: vertices.setPositionZ(-1))
        self.check_undo(name, lambda: vertices.mirror("z", pivot=(0, 0, 1)))
        curve = self.curve(periodic=True)
        self.check_undo(curve.getFullName(), lambda: curve.getCVs().mirror("y", worldSpace=True))

    def test_fast_matches_normal_without_undo(self):
        actions = (
            ("setPositions", lambda items, ws, fast: items.setPositions([(1, 2, 3), (4, 5, 6)], worldSpace=ws,
                                                                        fast=fast)),
            ("setPosition", lambda items, ws, fast: items.setPosition((1, 2, 3), worldSpace=ws, fast=fast)),
            ("setPositionX", lambda items, ws, fast: items.setPositionX([1, 2], worldSpace=ws, fast=fast)),
            ("setPositionY", lambda items, ws, fast: items.setPositionY(3, worldSpace=ws, fast=fast)),
            ("setPositionZ", lambda items, ws, fast: items.setPositionZ(-3, worldSpace=ws, fast=fast)),
            ("mirror", lambda items, ws, fast: items.mirror("x", worldSpace=ws, pivot=(1, 0, 0), fast=fast)),
        )
        for label, action in actions:
            for worldSpace in (False, True):
                with self.subTest(method=label, worldSpace=worldSpace):
                    self.check_fast(lambda text: self.cube(text + "#"),
                                    lambda shape, fast: action(shape.getVertices([1, 6]), worldSpace, fast))
                    self.check_fast(lambda text: self.curve(text + "#"),
                                    lambda shape, fast: action(shape.getCVs([0, 3]), worldSpace, fast))
                    self.check_fast(lambda text: self.curve(text + "#", periodic=True),
                                    lambda shape, fast: action(shape.getCVs([1, 6]), worldSpace, fast))

    def test_invalid_inputs_do_not_change_the_shape(self):
        shape = self.cube()
        vertices = shape.getVertices([0, 1])
        self.check_rejects(shape.getFullName(), (
            (ValueError, lambda: vertices.setPositions([(1, 2, 3)])),
            (TypeError, lambda: vertices.setPositions([(1, 2, 3), (1, 2, "a")])),
            (ValueError, lambda: vertices.setPositions([(1, 2, 3), (1, 2, float("inf"))])),
            (TypeError, lambda: vertices.setPositions(5)),
            (ValueError, lambda: vertices.setPosition((1, 2, 3, 4))),
            (ValueError, lambda: vertices.setPositionX([1, 2, 3])),
            (TypeError, lambda: vertices.setPositionX("ab")),
            (TypeError, lambda: vertices.setPositionY([1, None])),
            (TypeError, lambda: vertices.setPositions([(1, 2, 3)] * 2, worldSpace="yes")),
            (TypeError, lambda: vertices.setPositions([(1, 2, 3)] * 2, fast=None)),
            (ValueError, lambda: vertices.mirror("q")),
            (TypeError, lambda: vertices.mirror(None)),
            (ValueError, lambda: vertices.mirror("x", pivot=(1, 2))),
            (ValueError, lambda: vertices.mirror("x", pivot=5)),
            (TypeError, lambda: vertices.mirror("x", worldSpace=1)),
            (TypeError, lambda: vertices.mirror("x", fast="no")),
        ))

    def test_fast_rejects_input_history(self):
        shape = self.cube(history=True)
        self.check_rejects(shape.getFullName(), (
            (NotImplementedError, lambda: shape.getVertices([0, 1]).setPositions([(0, 0, 0)] * 2, fast=True)),
            (NotImplementedError, lambda: shape.getVertices([0, 1]).mirror(fast=True)),
        ))
        # 通常経路は入力履歴があってもtweakとして書き込める。
        shape.getVertices([0]).setPosition((3, 3, 3))
        self.assertPointsAlmostEqual([_points(shape.getFullName())[0]], [(3, 3, 3)])


class ShapeMirrorTest(_Case):
    """Mesh.mirror・NurbsCurve.mirror・Transform.mirrorGeometry。"""

    def test_mesh_mirror_spaces_indices_and_pivot(self):
        for worldSpace in (False, True):
            for indices in (None, [1, 3, 3, 5]):
                with self.subTest(worldSpace=worldSpace, indices=indices):
                    shape = self.cube("cube#")
                    name = shape.getFullName()
                    before = _points(name, worldSpace)
                    self.assertIs(shape.mirror("x", worldSpace=worldSpace, pivot=(0.5, 0, 0), indices=indices), shape)
                    targets = range(len(before)) if indices is None else [1, 3, 5]
                    self.assertPointsAlmostEqual(_points(name, worldSpace),
                                                 _mirrored(before, targets, 0, (0.5, 0, 0)))

    def test_axis_spellings_are_equivalent(self):
        results = []
        for axis in ("z", "XY", "yx", 2):
            shape = self.cube("cube#")
            shape.mirror(axis, pivot=(0, 0, 0.25))
            results.append(_points(shape.getFullName()))
        for result in results[1:]:
            self.assertPointsAlmostEqual(result, results[0])

    def test_curve_mirror_open_and_periodic(self):
        for periodic in (False, True):
            for worldSpace in (False, True):
                with self.subTest(periodic=periodic, worldSpace=worldSpace):
                    shape = self.curve("crv#", periodic=periodic)
                    name = shape.getFullName()
                    before = _points(name, worldSpace)
                    self.assertIs(shape.mirror("y", worldSpace=worldSpace, pivot=(0, 1, 0)), shape)
                    self.assertPointsAlmostEqual(_points(name, worldSpace),
                                                 _mirrored(before, range(len(before)), 1, (0, 1, 0)))
        shape = self.curve("sub")
        before = _points(shape.getFullName())
        shape.mirror("z", indices=[0, 4])
        self.assertPointsAlmostEqual(_points(shape.getFullName()), _mirrored(before, [0, 4], 2, (0, 0, 0)))

    def test_mirror_twice_restores(self):
        shape = self.curve(periodic=True)
        before = _points(shape.getFullName())
        shape.mirror("x", worldSpace=True, pivot=(3, 0, 0)).mirror("x", worldSpace=True, pivot=(3, 0, 0))
        self.assertPointsAlmostEqual(_points(shape.getFullName()), before)

    def test_transform_mirror_geometry_applies_to_every_shape(self):
        mesh = self.cube()
        transform = mesh.getTransform()
        curve = self.curve()
        cmds.parent(curve.getFullName(), transform.getFullName(), shape=True, relative=True)
        names = [shape.getFullName() for shape in transform.getShapes()]
        self.assertEqual(len(names), 2)
        for worldSpace in (False, True):
            with self.subTest(worldSpace=worldSpace):
                before = [_points(name, worldSpace) for name in names]
                self.assertIs(transform.mirrorGeometry("YZ", worldSpace=worldSpace, pivot=(1, 0, 0), indices=[0, 2]),
                              transform)
                for name, points in zip(names, before):
                    self.assertPointsAlmostEqual(_points(name, worldSpace), _mirrored(points, [0, 2], 0, (1, 0, 0)))

    def test_transform_mirror_geometry_uses_iterators_for_every_shape(self):
        mesh = self.cube()
        transform = mesh.getTransform()
        curve = self.curve()
        cmds.parent(curve.getFullName(), transform.getFullName(), shape=True, relative=True)
        names = [shape.getFullName() for shape in transform.getShapes()]
        before = [_points(name) for name in names]
        transform.mirrorGeometry("y", pivot=iter((0, 1, 0)), indices=iter([1]))
        for name, points in zip(names, before):
            self.assertPointsAlmostEqual(_points(name), _mirrored(points, [1], 1, (0, 1, 0)))

    def test_undo_once(self):
        mesh = self.cube()
        self.check_undo(mesh.getFullName(), lambda: mesh.mirror("y", worldSpace=True))
        curve = self.curve(periodic=True)
        self.check_undo(curve.getFullName(), lambda: curve.mirror("x", indices=[0, 1]))
        transform = self.cube("other").getTransform()
        self.check_undo(transform.getShape().getFullName(), lambda: transform.mirrorGeometry("z", pivot=(0, 0, 1)))
        # 2つのShapeも1回のUndoでまとめて戻る。
        cmds.parent(self.curve("crv2").getFullName(), transform.getFullName(), shape=True, relative=True)
        names = [shape.getFullName() for shape in transform.getShapes()]
        before = [_points(name) for name in names]
        self.flushUndo()
        transform.mirrorGeometry()
        cmds.undo()
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        for name, points in zip(names, before):
            self.assertPointsAlmostEqual(_points(name), points, places=6)

    def test_fast_matches_normal_without_undo(self):
        for worldSpace in (False, True):
            with self.subTest(worldSpace=worldSpace):
                self.check_fast(lambda text: self.cube(text + "#"),
                                lambda shape, fast: shape.mirror("x", worldSpace=worldSpace, pivot=(1, 0, 0),
                                                                 indices=[0, 1, 2], fast=fast))
                self.check_fast(lambda text: self.curve(text + "#", periodic=True),
                                lambda shape, fast: shape.mirror("z", worldSpace=worldSpace, fast=fast))
                self.check_fast(lambda text: self.cube(text + "#"),
                                lambda shape, fast: shape.getTransform().mirrorGeometry(
                                    "y", worldSpace=worldSpace, pivot=(0, 2, 0), fast=fast))

    def test_invalid_inputs_do_not_change_the_shape(self):
        mesh = self.cube()
        transform = mesh.getTransform()
        curve = self.curve()
        self.check_rejects(mesh.getFullName(), (
            (IndexError, lambda: mesh.mirror(indices=[0, 99])),
            (IndexError, lambda: mesh.mirror(indices=[-1])),
            (TypeError, lambda: mesh.mirror(indices=[True])),
            (TypeError, lambda: mesh.mirror(indices=["0"])),
            (TypeError, lambda: mesh.mirror(indices=5)),
            (ValueError, lambda: mesh.mirror("xy z")),
            (ValueError, lambda: mesh.mirror("xyz")),
            (TypeError, lambda: mesh.mirror(1.0)),
            (ValueError, lambda: mesh.mirror(pivot=(0, 0, float("nan")))),
            (TypeError, lambda: mesh.mirror(worldSpace=None)),
            (TypeError, lambda: mesh.mirror(fast=0)),
            (TypeError, lambda: mesh.mirror(worldSpace=True, ws=True)),
            (IndexError, lambda: transform.mirrorGeometry(indices=[99])),
            (TypeError, lambda: transform.mirrorGeometry(fast=1)),
            (ValueError, lambda: transform.mirrorGeometry("w")),
        ))
        self.check_rejects(curve.getFullName(), (
            (IndexError, lambda: curve.mirror(indices=[0, 5])),
            (ValueError, lambda: curve.mirror(pivot=(1, 2, 3, 4))),
        ))

    def test_transform_validates_every_shape_before_writing(self):
        # 2つ目のShape(CV 5個)で範囲外の番号は、1つ目のMesh(頂点8個)も変更せずに拒否する。
        mesh = self.cube()
        transform = mesh.getTransform()
        curve = self.curve()
        cmds.parent(curve.getFullName(), transform.getFullName(), shape=True, relative=True)
        names = [shape.getFullName() for shape in transform.getShapes()]
        before = [_points(name) for name in names]
        for error, kwargs in ((IndexError, {"indices": [6]}), (ValueError, {"worldSpace": True})):
            with self.subTest(error=error.__name__):
                if kwargs.get("worldSpace"):
                    cmds.setAttr(transform.getFullName() + ".scaleY", 0)
                with self.assertRaises(error):
                    transform.mirrorGeometry(**kwargs)
                self.assertEqual([_points(name) for name in names], before)
        # 対応しないShape(locator)があれば、どのShapeも変更せずにValueError。
        other = self.cube("other")
        cmds.createNode("locator", name=self.name("locShape"), parent=other.getTransform().getFullName(),
                        skipSelect=True)
        self.check_rejects(other.getFullName(), (
            (ValueError, lambda: other.getTransform().mirrorGeometry()),
        ))

    def test_fast_rejects_input_history_before_writing(self):
        mesh = self.cube(history=True)
        self.check_rejects(mesh.getFullName(), (
            (NotImplementedError, lambda: mesh.mirror(fast=True)),
            (NotImplementedError, lambda: mesh.getTransform().mirrorGeometry(fast=True)),
        ))
        # 2つ目のShapeだけ入力履歴を持つ場合も、1つ目を変更しない。
        clean = self.cube("clean")
        transform = clean.getTransform()
        history = cmds.circle(name=self.name("circle"), constructionHistory=True)[0]
        history_shape = cmds.listRelatives(history, shapes=True, fullPath=True)[0]
        cmds.parent(history_shape, transform.getFullName(), shape=True, relative=True)
        self.check_rejects(clean.getFullName(), (
            (NotImplementedError, lambda: transform.mirrorGeometry(fast=True)),
        ))

    def test_transform_without_shapes_does_nothing(self):
        transform = mlib.getNode(self.make("transform", "empty"))
        self.flushUndo()
        self.assertIs(transform.mirrorGeometry(), transform)
        self.assertUndoEmpty()


class UVTest(_Case):
    """UVの書込み。"""

    def test_set_position_u_v(self):
        shape = self.cube()
        name = shape.getFullName()
        uv = shape.getUV(3)
        self.assertIs(uv.setPosition((0.25, 1.5)), uv)
        self.assertPointsAlmostEqual([_uvs(name)[3]], [(0.25, 1.5)])
        self.assertIs(uv.setU(-0.5), uv)
        self.assertIs(uv.setV(2.0), uv)
        self.assertPointsAlmostEqual([_uvs(name)[3]], [(-0.5, 2.0)])

    def test_collection_setters(self):
        shape = self.cube()
        name = shape.getFullName()
        uvs = shape.getUVs([0, 5, 2])
        self.assertIs(uvs.setPositions([(0.1, 0.2), (0.3, 0.4), (0.5, 0.6)]), uvs)
        values = _uvs(name)
        self.assertPointsAlmostEqual([values[0], values[5], values[2]], [(0.1, 0.2), (0.3, 0.4), (0.5, 0.6)])
        uvs.setU(0.75)
        uvs.setV([1, 2, 3])
        values = _uvs(name)
        self.assertPointsAlmostEqual([values[0], values[5], values[2]], [(0.75, 1), (0.75, 2), (0.75, 3)])
        uvs.setPosition((0.5, 0.5))
        values = _uvs(name)
        self.assertPointsAlmostEqual([values[0], values[5], values[2]], [(0.5, 0.5)] * 3)
        uvs.setPositions(uvs.getPosition())  # getPositionの結果をそのまま渡せる

    def test_writes_the_current_uv_set(self):
        shape = self.cube()
        name = shape.getFullName()
        cmds.polyUVSet(name, copy=True, uvSet="map1", newUVSet="uv2")
        cmds.polyUVSet(name, currentUVSet=True, uvSet="uv2")
        map1 = _uvs(name, "map1")
        for fast in (False, True):
            with self.subTest(fast=fast):
                shape.getUV(1).setPosition((0.9, 0.1), fast=fast)
                shape.getUVs([2]).setU(0.8, fast=fast)
                self.assertPointsAlmostEqual(_uvs(name, "uv2")[1:3], [(0.9, 0.1), (0.8, _uvs(name, "uv2")[2][1])])
                self.assertEqual(_uvs(name, "map1"), map1)

    def test_undo_once(self):
        shape = self.cube()
        name = shape.getFullName()
        self.check_undo(name, lambda: shape.getUV(0).setPosition((0.9, 0.9)), uv=True)
        self.check_undo(name, lambda: shape.getUV(1).setU(0.7), uv=True)
        self.check_undo(name, lambda: shape.getUV(1).setV(0.7), uv=True)
        uvs = shape.getUVs([2, 3])
        self.check_undo(name, lambda: uvs.setPositions([(0.1, 0.1), (0.2, 0.2)]), uv=True)
        self.check_undo(name, lambda: uvs.setPosition((0.3, 0.3)), uv=True)
        self.check_undo(name, lambda: uvs.setU([0.4, 0.5]), uv=True)
        self.check_undo(name, lambda: uvs.setV(0.6), uv=True)

    def test_fast_matches_normal_without_undo(self):
        actions = (
            ("UV.setPosition", lambda shape, fast: shape.getUV(4).setPosition((0.3, 0.7), fast=fast)),
            ("UV.setU", lambda shape, fast: shape.getUV(4).setU(0.3, fast=fast)),
            ("UV.setV", lambda shape, fast: shape.getUV(4).setV(0.3, fast=fast)),
            ("UVs.setPositions", lambda shape, fast: shape.getUVs([1, 4]).setPositions([(0, 1), (1, 0)], fast=fast)),
            ("UVs.setPosition", lambda shape, fast: shape.getUVs([1, 4]).setPosition((0.2, 0.4), fast=fast)),
            ("UVs.setU", lambda shape, fast: shape.getUVs([1, 4]).setU([0.1, 0.9], fast=fast)),
            ("UVs.setV", lambda shape, fast: shape.getUVs([1, 4]).setV(0.6, fast=fast)),
        )
        for label, action in actions:
            with self.subTest(method=label):
                self.check_fast(lambda text: self.cube(text + "#"), action, uv=True)

    def test_invalid_inputs_do_not_change_the_uvs(self):
        shape = self.cube()
        uv = shape.getUV(0)
        uvs = shape.getUVs([0, 1])
        self.check_rejects(shape.getFullName(), (
            (ValueError, lambda: uv.setPosition((1, 2, 3))),
            (TypeError, lambda: uv.setPosition("ab")),
            (ValueError, lambda: uv.setPosition((0, float("inf")))),
            (TypeError, lambda: uv.setU("0.5")),
            (TypeError, lambda: uv.setV(False)),
            (TypeError, lambda: uv.setPosition((0, 0), fast=1)),
            (ValueError, lambda: uvs.setPositions([(0, 0)])),
            (TypeError, lambda: uvs.setPositions([(0, 0), (0, "a")])),
            (TypeError, lambda: uvs.setPositions("abcd")),
            (ValueError, lambda: uvs.setU([1, 2, 3])),
            (TypeError, lambda: uvs.setV("ab")),
        ), uv=True)
        history = self.cube("history", history=True)
        self.check_rejects(history.getFullName(), (
            (NotImplementedError, lambda: history.getUV(0).setPosition((0, 0), fast=True)),
            (NotImplementedError, lambda: history.getUVs([0, 1]).setU(0.5, fast=True)),
        ), uv=True)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
