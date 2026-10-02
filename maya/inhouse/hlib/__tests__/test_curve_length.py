"""カーブ長の空間・インスタンス・評価更新をMayaで検証する。"""
import math
import sys
import unittest
import maya.cmds as cmds
import hlib


class CurveLengthTest(unittest.TestCase):
    """テスト用namespace内のカーブを使用する。"""

    def setUp(self):
        """namespaceと距離単位を保存する。"""
        self.old_namespace = cmds.namespaceInfo(currentNamespace=True)
        self.old_unit = cmds.currentUnit(query=True, linear=True)
        cmds.currentUnit(linear="cm")
        self.namespace = cmds.namespace(add="hlibCurveLengthTest")
        cmds.namespace(set=self.namespace)

    def tearDown(self):
        """対象を削除して環境を復元する。"""
        cmds.namespace(set=self.old_namespace)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        cmds.currentUnit(linear=self.old_unit)

    def test_world_space_instances_and_no_edits(self):
        """非均等スケールとシアー、別インスタンスを正しく評価する。"""
        transform = hlib.getNode(cmds.curve(d=1, p=[(0, 0, 0), (1, 1, 0)]))
        instance = hlib.getNode(cmds.instance(transform.full_name())[0])
        transform.plug("scale").set((2, 3, 1))
        transform.plug("shearXY").set(.5)
        curve = transform.shape()
        before = set(cmds.ls())
        undo_before = cmds.undoInfo(query=True, undoName=True)
        self.assertAlmostEqual(curve.length(1e-6), math.sqrt(2))
        end = cmds.pointPosition(curve.full_name() + ".cv[1]", world=True)
        expected = math.sqrt(sum(v*v for v in end))
        self.assertAlmostEqual(curve.length(ws=True), expected)
        self.assertAlmostEqual(instance.shape().length(ws=True), math.sqrt(2))
        self.assertEqual(set(cmds.ls()), before)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_before)
        cmds.currentUnit(linear="m")
        self.assertAlmostEqual(curve.length(ws=True), expected / 100)
        self.assertAlmostEqual(curve.length(ws=True, unit="cm"), expected)
        self.assertAlmostEqual(curve.length(unit="mm"), math.sqrt(2) * 10)
        self.assertAlmostEqual(curve.length(unit="meter"), math.sqrt(2) / 100)
        self.assertEqual(cmds.currentUnit(query=True, linear=True), "m")

    def test_units_conversion(self):
        """UnitsのUI照会と明示変換を検証する。"""
        from hlib.utils import units
        from hlib.environment import Preferences
        self.assertEqual(Preferences.get_linear_unit(), "cm")
        for unit, centimeters in (("mm", .1), ("cm", 1), ("m", 100),
                                  ("km", 100000), ("in", 2.54), ("ft", 30.48),
                                  ("yd", 91.44), ("mi", 160934.4)):
            self.assertAlmostEqual(units.convert_distance(1, unit, "cm"), centimeters)
            self.assertAlmostEqual(units.convert_distance(centimeters, "cm", unit), 1)
        cmds.currentUnit(linear="m")
        self.assertEqual(Preferences.get_linear_unit(), "m")
        self.assertAlmostEqual(units.convert_distance(100, "cm"), 1)
        self.assertAlmostEqual(units.convert_distance(1, to_unit="cm"), 100)

    def test_curved_history_and_updates(self):
        """曲線の弧長と履歴・親の変更を評価する。"""
        transform, history = cmds.circle(radius=2, constructionHistory=True)
        curve = hlib.getNode(transform).shape()
        cmds.setAttr(transform + ".scale", 2, 3, 1)
        info = cmds.createNode("curveInfo")
        cmds.connectAttr(curve.full_name() + ".worldSpace[0]", info + ".inputCurve")
        self.assertAlmostEqual(curve.length(ws=True), cmds.getAttr(info + ".arcLength"), places=4)
        original = curve.length(ws=True)
        cmds.setAttr(history + ".radius", 4)
        self.assertAlmostEqual(curve.length(ws=True), original * 2, places=4)

    def test_validation(self):
        """不正な許容誤差と空間フラグを拒否する。"""
        curve = hlib.getNode(cmds.curve(d=1, p=[(0, 0, 0), (1, 0, 0)])).shape()
        for tolerance in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                curve.length(tolerance)
        with self.assertRaises(TypeError):
            curve.length(ws=1)
        with self.assertRaises(TypeError):
            curve.length(unit=1)
        with self.assertRaises(ValueError):
            curve.length(unit="invalid")

    def test_rational_curve(self):
        """ウェイト付きCVを持つ曲線も標準curveInfoの評価と一致する。"""
        transform = cmds.curve(d=2, pw=[(1, 0, 0, 1),
                                       (1, 1, 0, math.sqrt(.5)), (0, 1, 0, 1)],
                               k=[0, 0, 1, 1])
        cmds.setAttr(transform + ".scale", 2, 3, 1)
        curve = hlib.getNode(transform).shape()
        info = cmds.createNode("curveInfo")
        cmds.connectAttr(curve.full_name() + ".worldSpace[0]", info + ".inputCurve")
        self.assertAlmostEqual(curve.length(ws=True), cmds.getAttr(info + ".arcLength"), places=4)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
