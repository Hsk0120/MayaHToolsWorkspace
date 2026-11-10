"""Transform のカーブ形状の保存・復元(getCurveShapesData・setCurveShapesData・export/importCurveShapes)を確かめる。"""

import json as std_json
import os
import shutil
import sys
import tempfile
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.json import dump
from support.specCase import NamespaceCase

#: CV位置の比較の許容誤差(cm)。
_TOLERANCE = 1e-9


class CurveShapesTest(NamespaceCase):
    """カーブ形状の往復・表示色・単位・Undo・不正なデータ。"""

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp(prefix="mlibCurveShapesTest")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)
        super().tearDown()

    def make_control(self):
        """円(periodic・次数3)と四角(次数1)の2つのShapeを持つコントローラーを作る。"""
        control = cmds.circle(name=self.name("ctrl"), degree=3, sections=8, radius=2.0, constructionHistory=False)[0]
        square = cmds.curve(degree=1, point=[(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1), (-1, 0, -1)])
        cmds.parent(cmds.listRelatives(square, shapes=True, fullPath=True), control, shape=True, relative=True)
        cmds.delete(square)
        shapes = cmds.listRelatives(control, shapes=True, fullPath=True)
        cmds.rename(shapes[0], "ctrlCircleShape")
        cmds.rename(cmds.listRelatives(control, shapes=True, fullPath=True)[1], "ctrlSquareShape")
        open_curve = cmds.curve(degree=3, point=[(0, 0, 0), (1, 1, 0), (2, -1, 0), (3, 0, 0), (4, 2, 1)])
        cmds.parent(cmds.listRelatives(open_curve, shapes=True, fullPath=True), control, shape=True, relative=True)
        cmds.delete(open_curve)
        cmds.rename(cmds.listRelatives(control, shapes=True, fullPath=True)[2], "ctrlOpenShape")
        node = mlib.getNode(control)
        circle, square_shape, open_shape = node.getShapes()
        circle.setOverrideColor(17)
        square_shape.setOverrideColor((0.25, 0.5, 1.0))
        cmds.setAttr(circle.getFullName() + ".lineWidth", 3.0)
        node.setOverrideColor(6)
        return node

    @staticmethod
    def curve_values(shape):
        """Shapeのフォーム・次数・ノット・オブジェクト空間のCV位置を返す。"""
        fn = om2.MFnNurbsCurve(shape.mpath())
        return fn.form, fn.degree, list(fn.knots()), [tuple(point)[:3] for point in fn.cvPositions(om2.MSpace.kObject)]

    def assert_points_close(self, actual, expected):
        """CV位置の並びが許容誤差内で同じであることを確かめる(MELの数値の読み取りで最下位の桁が変わり得る)。"""
        self.assertEqual(len(actual), len(expected))
        for point, point2 in zip(expected, actual):
            for value, value2 in zip(point, point2):
                self.assertAlmostEqual(value2, value, delta=_TOLERANCE)

    def assert_same_curves(self, source, target):
        """2つのTransformのカーブ形状が同じであることを確かめる。"""
        expected = [self.curve_values(shape) for shape in source.getShapes()]
        actual = [self.curve_values(shape) for shape in target.getShapes()]
        self.assertEqual(len(actual), len(expected))
        for (form, degree, knots, points), (form2, degree2, knots2, points2) in zip(expected, actual):
            self.assertEqual((form2, degree2), (form, degree))
            self.assertEqual(knots2, knots)
            self.assert_points_close(points2, points)

    def test_data_layout(self):
        control = self.make_control()
        data = control.getCurveShapesData()
        self.assertEqual(data["color"], 6)
        self.assertEqual([entry["name"] for entry in data["shapes"]], ["ctrlCircleShape", "ctrlSquareShape",
                                                                       "ctrlOpenShape"])
        circle, square, open_curve = data["shapes"]
        self.assertEqual((circle["degree"], circle["form"]), (3, "periodic"))
        self.assertEqual(len(circle["points"]), 11)
        self.assertEqual(len(circle["knots"]), 13)
        self.assertEqual(square["degree"], 1)
        self.assertEqual((open_curve["degree"], open_curve["form"]), (3, "open"))
        self.assertEqual(circle["color"], 17)
        for value, expected in zip(square["color"], (0.25, 0.5, 1.0)):
            self.assertAlmostEqual(value, expected, places=6)
        self.assertIsNone(open_curve["color"])
        self.assertEqual(circle["lineWidth"], 3.0)
        self.assertEqual(open_curve["lineWidth"], -1.0)
        std_json.dumps(data, allow_nan=False)

    def test_round_trip_through_file(self):
        control = self.make_control()
        path = control.exportCurveShapes(os.path.join(self.folder, "ctrl.json"))
        with open(str(path), encoding="utf-8") as stream:
            self.assertEqual(std_json.load(stream)["header"]["format"], "mlib.curveShapes")
        # 読み込み先は別のShapeを1つ(既定の色・線幅)持つ。
        target = mlib.getNode(cmds.circle(name=self.name("target"), radius=5.0, constructionHistory=False)[0])
        cmds.setAttr(target.getFullName() + ".translate", 3, 4, 5)
        self.assertIs(target.importCurveShapes(path), target)
        self.assert_same_curves(control, target)
        shapes = target.getShapes()
        # 別の親の下では同じ短い名前を使える(Mayaは同じ親の下の重複だけ番号で避ける)。
        self.assertEqual([shape.getName() for shape in shapes],
                         [self.name("ctrlCircleShape"), self.name("ctrlSquareShape"), self.name("ctrlOpenShape")])
        self.assertEqual(shapes[0].getOverrideColor(), 17)
        for value, expected in zip(shapes[1].getOverrideColor(), (0.25, 0.5, 1.0)):
            self.assertAlmostEqual(value, expected, places=6)
        self.assertIsNone(shapes[2].getOverrideColor())
        self.assertEqual(cmds.getAttr(shapes[0].getFullName() + ".lineWidth"), 3.0)
        self.assertEqual(cmds.getAttr(shapes[2].getFullName() + ".lineWidth"), -1.0)
        self.assertEqual(target.getOverrideColor(), 6)
        self.assertEqual(list(target.getTranslation()), [3.0, 4.0, 5.0])

    def test_shape_names_after_source_removed(self):
        control = self.make_control()
        data = control.getCurveShapesData()
        cmds.delete(control.getFullName())
        target = mlib.getNode(cmds.createNode("transform", name=self.name("target")))
        target.setCurveShapesData(data)
        self.assertEqual([shape.getName() for shape in target.getShapes()],
                         [self.name("ctrlCircleShape"), self.name("ctrlSquareShape"), self.name("ctrlOpenShape")])

    def test_fewer_shapes_and_colors_cleared(self):
        control = self.make_control()
        data = control.getCurveShapesData()
        data["shapes"] = data["shapes"][1:2]
        data["color"] = None
        control.setCurveShapesData(data)
        self.assertEqual(len(control.getShapes()), 1)
        self.assertEqual(self.curve_values(control.getShapes()[0])[1], 1)
        self.assertIsNone(control.getOverrideColor())

    def test_linear_unit_independent(self):
        control = self.make_control()
        data = control.getCurveShapesData()
        target = mlib.getNode(cmds.createNode("transform", name=self.name("target")))
        cmds.currentUnit(linear="m")
        target.setCurveShapesData(data)
        self.assertEqual(cmds.currentUnit(query=True, linear=True), "m")
        self.assert_points_close(target.getCurveShapesData()["shapes"][0]["points"], data["shapes"][0]["points"])
        cmds.currentUnit(linear="cm")
        self.assert_same_curves(control, target)

    def test_one_undo_restores_previous_shapes(self):
        control = self.make_control()
        data = control.getCurveShapesData()
        target = mlib.getNode(cmds.circle(name=self.name("target"), radius=5.0, constructionHistory=False)[0])
        before = target.getCurveShapesData()
        cmds.flushUndo()
        target.setCurveShapesData(data)
        self.assertEqual(len(target.getShapes()), 3)
        cmds.undo()
        self.assertEqual(target.getCurveShapesData(), before)
        cmds.redo()
        self.assert_same_curves(control, target)

    def test_other_shape_types_are_kept(self):
        control = self.make_control()
        data = control.getCurveShapesData()
        target = mlib.getNode(cmds.spaceLocator(name=self.name("target"))[0])
        locator = target.getShapes()[0].getFullName()
        target.setCurveShapesData(data)
        self.assertTrue(cmds.objExists(locator))
        self.assertEqual(len(target.getShapes()), 4)
        target.setCurveShapesData({"color": None, "shapes": []})
        self.assertEqual([shape.getFullName() for shape in target.getShapes()], [locator])

    def test_joint(self):
        control = self.make_control()
        data = control.getCurveShapesData()
        cmds.select(clear=True)
        joint = mlib.getNode(cmds.joint(name=self.name("jnt"), position=(1, 2, 3)))
        self.assertIsInstance(joint, mlib.Joint)
        joint.setCurveShapesData(data)
        self.assert_same_curves(control, joint)
        self.assertEqual(joint.getOverrideColor(), 6)
        for entry, expected in zip(joint.getCurveShapesData()["shapes"], data["shapes"]):
            self.assert_points_close(entry.pop("points"), expected["points"])
            self.assertEqual(entry, {key: value for key, value in expected.items() if key != "points"})

    def test_malformed_data_changes_nothing(self):
        control = self.make_control()
        good = control.getCurveShapesData()
        target = mlib.getNode(cmds.circle(name=self.name("target"), radius=5.0, constructionHistory=False)[0])
        before = target.getCurveShapesData()

        def broken(**changes):
            data = std_json.loads(std_json.dumps(good))
            data["shapes"][1].update(changes)
            return data

        cases = {
            "no shapes": {"color": None},
            "shapes not list": {"color": None, "shapes": {}},
            "bad color": dict(good, color=99),
            "bad name": broken(name="a|b"),
            "empty name": broken(name=""),
            "bad degree": broken(degree=0),
            "bool degree": broken(degree=True),
            "bad form": broken(form="loop"),
            "few points": broken(points=[[0, 0, 0]]),
            "point size": broken(points=[[0, 0]] * 5),
            "nan point": broken(points=[[0, 0, float("nan")]] * 5),
            "knot count": broken(knots=[0.0, 1.0]),
            "knots decrease": broken(knots=[0.0, 2.0, 1.0, 3.0, 4.0]),
            "shape color": broken(color=(2.0, 0.0, 0.0)),
            "line width": broken(lineWidth="thick"),
            "missing key": {"color": None, "shapes": [{"name": "a"}]},
        }
        for label, data in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                target.setCurveShapesData(data)
            self.assertEqual(target.getCurveShapesData(), before)
        with self.assertRaises(TypeError):
            target.setCurveShapesData([])
        wrong = os.path.join(self.folder, "wrong.json")
        dump({"shapes": []}, wrong, "mlib.other", 1)
        with self.assertRaises(ValueError):
            target.importCurveShapes(wrong)
        self.assertEqual(target.getCurveShapesData(), before)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
