"""コントローラー作成の補助(NurbsCurve.create・setCvPositions・Transform.replaceShapes・DagNode.setColor)の仕様テスト。

cmdsで独立に照会した値と比べ、Undo 1回で戻ること・不正入力の例外型・現在のUI単位に依存しないことを確かめる。
"""

import sys
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import NurbsCurve
from mlib.nodes import Transform
from support.specCase import NamespaceCase

SQUARE = [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]


def _cvs(shape):
    """cmdsでCVのローカル座標(現在のUI単位)を取得する。"""
    values = cmds.getAttr(shape + ".cv[*]")
    return [tuple(value) for value in values]


def _world_cvs(shape):
    """cmds.xformでCVのワールド座標(現在のUI単位)を取得する。"""
    values = cmds.xform(shape + ".cv[*]", query=True, worldSpace=True, translation=True)
    return [tuple(values[index:index + 3]) for index in range(0, len(values), 3)]


class _Case(NamespaceCase):
    PREFIX = "mlibSpecControls_"
    CLEAR_SELECTION = True

    def curve(self, points=SQUARE, **kwargs):
        """名前空間内にカーブを作成して返す。"""
        kwargs.setdefault("name", self.name("crv#"))
        return mlib.createCurve(points, **kwargs)

    def assertPointsAlmostEqual(self, actual, expected, places=9):
        actual, expected = list(actual), list(expected)
        self.assertEqual(len(actual), len(expected))
        for a, e in zip(actual, expected):
            self.assertSequenceAlmostEqual(tuple(a)[:3], tuple(e)[:3], places=places)


class NurbsCurveCreateTest(_Case):
    """点列からのカーブ作成。"""

    def test_open_and_closed_forms_match_cmds(self):
        """開いた・閉じたカーブの次数・形式・CVをcmdsで照会した値と比べる。"""
        # cmdsのformは 0=open・2=periodic、getForm()はMFnNurbsCurveの定数。
        cases = (
            (dict(degree=1), 1, 0, 4, SQUARE),
            (dict(degree=3), 3, 0, 4, SQUARE),
            (dict(degree=1, closed=True), 1, 2, 5, SQUARE + SQUARE[:1]),
            (dict(degree=2, closed=True), 2, 2, 6, SQUARE + SQUARE[:2]),
            (dict(degree=3, closed=True), 3, 2, 7, SQUARE + SQUARE[:3]),
        )
        forms = {0: om2.MFnNurbsCurve.kOpen, 2: om2.MFnNurbsCurve.kPeriodic}
        for flags, degree, form, count, points in cases:
            with self.subTest(flags=flags):
                shape = self.curve(**flags)
                self.assertIsInstance(shape, NurbsCurve)
                name = shape.getFullName()
                self.assertEqual(cmds.nodeType(name), "nurbsCurve")
                self.assertEqual(cmds.getAttr(name + ".degree"), degree)
                self.assertEqual(cmds.getAttr(name + ".form"), form)
                self.assertEqual(shape.getForm(), forms[form])
                self.assertEqual(shape.getNumCVs(), count)
                self.assertPointsAlmostEqual(shape.getCvPositions(), points)
                self.assertIsInstance(shape.getTransform(), Transform)
        self.assertEqual(cmds.ls(selection=True), [])

    def test_name_parent_and_units(self):
        """名前はTransform・<名前>Shapeへ付き、親の空間に置かれ、点はUI単位によらずcm。"""
        parent = self.make("transform", "parent")
        cmds.setAttr(parent + ".translate", 5, 0, 0)
        cmds.currentUnit(linear="mm")
        shape = mlib.createCurve([(0, 0, 0), (2, 0, 0)], name=self.name("ctl"), parent=parent)
        transform = shape.getTransform()
        self.assertEqual(transform.getName().rsplit(":", 1)[-1], "ctl")
        self.assertEqual(shape.getName().rsplit("|", 1)[-1].rsplit(":", 1)[-1], "ctlShape")
        self.assertEqual(transform.getParent().getFullName(), cmds.ls(parent, long=True)[0])
        self.assertSequenceAlmostEqual(cmds.getAttr(transform.getFullName() + ".translate")[0], (0, 0, 0))
        cmds.currentUnit(linear="cm")
        self.assertPointsAlmostEqual(_cvs(shape.getFullName()), [(0, 0, 0), (2, 0, 0)])
        self.assertPointsAlmostEqual(_world_cvs(shape.getFullName()), [(5, 0, 0), (7, 0, 0)])

    def test_point_types(self):
        """MPoint・MVector・listを受け付け、MPointはwで割らない。"""
        shape = self.curve([om2.MPoint(1, 2, 3, 2), om2.MVector(4, 5, 6), [7, 8, 9]])
        self.assertPointsAlmostEqual(shape.getCvPositions(), [(1, 2, 3), (4, 5, 6), (7, 8, 9)])

    def test_undo_once(self):
        """作成はUndo 1回で消える。"""
        self.flushUndo()
        shape = self.curve()
        name = shape.getFullName()
        self.assertUndoesInOneStep(lambda: self.assertFalse(cmds.objExists(name)),
                                   lambda: self.assertTrue(cmds.objExists(name)))

    def test_invalid_inputs(self):
        """不正な入力は作成前に型付きの例外になる。"""
        before = set(cmds.ls(type="nurbsCurve"))
        cases = (
            (TypeError, dict(points=5)),
            (TypeError, dict(points="abc")),
            (TypeError, dict(points=[(0, 0, "x"), (1, 0, 0)])),
            (TypeError, dict(points=[(0, 0, True), (1, 0, 0)])),
            (ValueError, dict(points=[(0, 0), (1, 0)])),
            (ValueError, dict(points=[(0, 0, float("nan")), (1, 0, 0)])),
            (ValueError, dict(points=[(0, 0, 0)])),
            (ValueError, dict(points=SQUARE[:3], degree=3)),
            (ValueError, dict(points=SQUARE[:2], closed=True)),
            (ValueError, dict(points=SQUARE, degree=4)),
            (TypeError, dict(points=SQUARE, degree=1.0)),
            (TypeError, dict(points=SQUARE, degree=True)),
            (TypeError, dict(points=SQUARE, closed=1)),
            (TypeError, dict(points=SQUARE, name=3)),
        )
        for error, kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(error):
                    mlib.createCurve(**kwargs)
        self.assertEqual(set(cmds.ls(type="nurbsCurve")), before)


class SetCvPositionsTest(_Case):
    """CV位置の一括書込み。"""

    def test_object_and_world_space_match_cmds(self):
        shape = self.curve(degree=3)
        transform = shape.getTransform().getFullName()
        cmds.setAttr(transform + ".translate", 1, 2, 3)
        cmds.setAttr(transform + ".scale", 2, 2, 2)
        local = [(0, 1, 0), (1, 1, 0), (2, 1, 0), (3, 1, 0)]
        self.assertIs(shape.setCvPositions(local), shape)
        self.assertPointsAlmostEqual(_cvs(shape.getFullName()), local)
        world = [(5, 0, 0), (7, 0, 0), (9, 0, 0), (11, 0, 0)]
        shape.setCvPositions(world, worldSpace=True)
        self.assertPointsAlmostEqual(_world_cvs(shape.getFullName()), world)
        self.assertPointsAlmostEqual(shape.getCvPositions(worldSpace=True), world)

    def test_round_trip_with_get_and_mm_units(self):
        shape = self.curve()
        cmds.currentUnit(linear="mm")
        moved = [om2.MPoint(point.x + 1, point.y, point.z) for point in shape.getCvPositions()]
        shape.setCvPositions(moved)
        cmds.currentUnit(linear="cm")
        self.assertPointsAlmostEqual(_cvs(shape.getFullName()), [(x + 1, y, z) for x, y, z in SQUARE])

    def test_periodic_curve_accepts_both_counts(self):
        shape = self.curve(degree=3, closed=True)
        independent = [(x * 2, y, z * 2) for x, y, z in SQUARE]
        shape.setCvPositions(independent)
        self.assertPointsAlmostEqual(shape.getCvPositions(), independent + independent[:3])
        shape.setCvPositions(independent + independent[:3])
        self.assertEqual(shape.getForm(), om2.MFnNurbsCurve.kPeriodic)
        with self.assertRaises(ValueError):
            shape.setCvPositions(independent + [(9, 9, 9)] + independent[1:3])
        with self.assertRaises(ValueError):
            shape.setCvPositions(independent[:3])

    def test_undo_once(self):
        shape = self.curve()
        self.flushUndo()
        shape.setCvPositions([(0, 5, 0)] * 4)
        self.assertUndoesInOneStep(
            lambda: self.assertPointsAlmostEqual(_cvs(shape.getFullName()), SQUARE),
            lambda: self.assertPointsAlmostEqual(_cvs(shape.getFullName()), [(0, 5, 0)] * 4))

    def test_invalid_inputs(self):
        shape = self.curve()
        for error, args, kwargs in (
                (ValueError, ([(0, 0, 0)] * 3,), {}),
                (ValueError, ([(0, 0, 0)] * 5,), {}),
                (TypeError, ([(0, 0, "a")] * 4,), {}),
                (ValueError, ([(0, 0, float("inf"))] * 4,), {}),
                (TypeError, (SQUARE,), {"worldSpace": 1})):
            with self.subTest(args=args, kwargs=kwargs):
                with self.assertRaises(error):
                    shape.setCvPositions(*args, **kwargs)
        self.assertPointsAlmostEqual(_cvs(shape.getFullName()), SQUARE)
        cv = shape.getCV(0)
        self.assertFalse(hasattr(cv, "setPosition"))


class ReplaceShapesTest(_Case):
    """Shapeの差し替え。"""

    def test_moves_shapes_and_deletes_old_ones(self):
        control = self.curve(name=self.name("ctl")).getTransform()
        cmds.setAttr(control.getFullName() + ".translate", 1, 2, 3)
        old = control.getShape()
        source = self.curve([(0, 0, 0), (0, 3, 0)], name=self.name("src")).getTransform()
        source_name = source.getFullName()
        self.assertIs(control.replaceShapes(source), control)
        shapes = control.getShapes()
        self.assertEqual(len(shapes), 1)
        self.assertFalse(old.isValid())
        self.assertFalse(cmds.objExists(source_name))
        self.assertEqual(shapes[0].getFullName().rsplit("|", 1)[-1], control.getFullName().rsplit("|", 1)[-1] + "Shape")
        self.assertPointsAlmostEqual(_cvs(shapes[0].getFullName()), [(0, 0, 0), (0, 3, 0)])
        self.assertSequenceAlmostEqual(cmds.getAttr(control.getFullName() + ".translate")[0], (1, 2, 3))

    def test_keep_source_and_world_space(self):
        control = self.curve(name=self.name("ctl")).getTransform()
        cmds.setAttr(control.getFullName() + ".translate", 1, 0, 0)
        cmds.setAttr(control.getFullName() + ".scale", 2, 2, 2)
        source = self.curve([(0, 0, 0), (0, 4, 0)], name=self.name("src")).getTransform()
        cmds.setAttr(source.getFullName() + ".translate", 5, 0, 0)
        expected = _world_cvs(source.getShape().getFullName())
        control.replaceShapes(source, keepSource=True, worldSpace=True)
        self.assertTrue(source.isValid())
        self.assertEqual(len(source.getShapes()), 1)
        self.assertPointsAlmostEqual(_world_cvs(control.getShape().getFullName()), expected)
        self.assertSequenceAlmostEqual(cmds.getAttr(control.getFullName() + ".scale")[0], (2, 2, 2))

    def test_source_shape_keeps_other_shapes_of_its_transform(self):
        control = self.make("transform", "grp")
        first = self.curve(name=self.name("src"))
        holder = first.getTransform()
        second = mlib.createCurve([(0, 0, 0), (1, 1, 1)])
        temporary = second.getTransform().getFullName()
        cmds.parent(second.getFullName(), holder.getFullName(), shape=True, relative=True)
        cmds.delete(temporary)
        target = mlib.getNode(control)
        target.replaceShapes(first)
        self.assertTrue(holder.isValid())
        self.assertEqual(len(target.getShapes()), 1)
        self.assertEqual(target.getShape().getNumCVs(), 4)

    def test_undo_once(self):
        control = self.curve(name=self.name("ctl")).getTransform()
        old = control.getShape().getFullName()
        source = self.curve([(0, 0, 0), (0, 3, 0)], name=self.name("src")).getTransform()
        source_name = source.getFullName()
        self.flushUndo()
        control.replaceShapes(source, worldSpace=True)

        def before():
            self.assertTrue(cmds.objExists(old))
            self.assertTrue(cmds.objExists(source_name))
            self.assertEqual([shape.getFullName() for shape in control.getShapes()], [old])

        self.assertUndoesInOneStep(before, lambda: self.assertFalse(cmds.objExists(source_name)))

    def test_invalid_inputs(self):
        control = self.curve(name=self.name("ctl")).getTransform()
        empty = mlib.getNode(self.make("transform", "empty"))
        network = self.make("network", "net")
        for error, args, kwargs in (
                (ValueError, (control,), {}),
                (ValueError, (control.getShape(),), {}),
                (ValueError, (empty,), {}),
                (TypeError, (network,), {}),
                (TypeError, (empty,), {"keepSource": 1}),
                (TypeError, (empty,), {"worldSpace": "yes"})):
            with self.subTest(args=args, kwargs=kwargs):
                with self.assertRaises(error):
                    control.replaceShapes(*args, **kwargs)
        self.assertEqual(len(control.getShapes()), 1)


class SetColorTest(_Case):
    """描画のオーバーライド色。"""

    def test_index_and_rgb_on_shapes(self):
        shape = self.curve()
        transform = shape.getTransform()
        name = shape.getFullName()
        self.assertIsNone(transform.getColor())
        self.assertIs(transform.setColor(13), transform)
        self.assertTrue(cmds.getAttr(name + ".overrideEnabled"))
        self.assertFalse(cmds.getAttr(name + ".overrideRGBColors"))
        self.assertEqual(cmds.getAttr(name + ".overrideColor"), 13)
        self.assertFalse(cmds.getAttr(transform.getFullName() + ".overrideEnabled"))
        self.assertEqual(transform.getColor(), 13)
        self.assertEqual(shape.getColor(), 13)
        transform.setColor((1.0, 0.5, 0.25))
        self.assertTrue(cmds.getAttr(name + ".overrideRGBColors"))
        self.assertSequenceAlmostEqual(cmds.getAttr(name + ".overrideColorRGB")[0], (1.0, 0.5, 0.25), places=6)
        self.assertSequenceAlmostEqual(transform.getColor(), (1.0, 0.5, 0.25), places=6)
        transform.setColor(4)
        self.assertFalse(cmds.getAttr(name + ".overrideRGBColors"))
        self.assertEqual(transform.getColor(), 4)

    def test_transform_without_shapes_and_joint(self):
        group = mlib.getNode(self.make("transform", "grp"))
        group.setColor(6)
        self.assertEqual(cmds.getAttr(group.getFullName() + ".overrideColor"), 6)
        joint = mlib.getNode(self.make("joint", "jnt"))
        joint.setColor([0, 1, 0])
        self.assertSequenceAlmostEqual(joint.getColor(), (0, 1, 0))

    def test_undo_once(self):
        shape = self.curve()
        transform = shape.getTransform()
        self.flushUndo()
        transform.setColor((0.2, 0.4, 0.6))
        self.assertUndoesInOneStep(lambda: self.assertIsNone(transform.getColor()),
                                   lambda: self.assertIsNotNone(transform.getColor()))

    def test_invalid_inputs(self):
        shape = self.curve()
        for error, value in ((TypeError, True), (TypeError, "red"), (TypeError, None), (TypeError, 1.5),
                             (ValueError, -1), (ValueError, 32), (ValueError, (1, 0)), (ValueError, (1, 0, 2)),
                             (TypeError, (1, "0", 0)), (ValueError, (0, float("nan"), 0))):
            with self.subTest(value=value):
                with self.assertRaises(error):
                    shape.setColor(value)
        self.assertIsNone(shape.getColor())

    def test_locked_attribute_rolls_back(self):
        shape = self.curve()
        transform = shape.getTransform()
        second = mlib.createCurve([(0, 0, 0), (1, 1, 1)])
        temporary = second.getTransform().getFullName()
        cmds.parent(second.getFullName(), transform.getFullName(), shape=True, relative=True)
        cmds.delete(temporary)
        second_name = transform.getShapes()[1].getFullName()
        cmds.setAttr(second_name + ".overrideColor", lock=True)
        with self.assertRaises(RuntimeError):
            transform.setColor(9)
        self.assertFalse(cmds.getAttr(shape.getFullName() + ".overrideEnabled"))
        cmds.setAttr(second_name + ".overrideColor", lock=False)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
