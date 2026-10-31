"""シーン操作の角度の既定を度にした約束(5.0.0)を固定する。

Plug.get/setの角度の数値・Transform.setRotate/getRotate・DrivenKey.setKey・Node.addAttrの範囲と既定値・
AnimCurveの角度出力は既定で度、``unit="rad"`` でラジアン。EulerRotate・Quaternionは内部rad(om2と同じ)で、
自身の単位を持つため換算しない。uiUnits=Trueは現在のUI単位で、unitとは同時に指定できない。
"""

import math
import sys
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common.drivenKey import DrivenKey
from mlib.maths import EulerRotate, Quaternion
from support.specCase import NamespaceCase


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、共通基底からの差分。"""

    PREFIX = "mlibSpecAngle_"

    def setUp(self):
        super().setUp()
        cmds.currentUnit(angle="deg")
        self.transform = mlib.getNode(self.make("transform", "node"))
        self.node_name = self.transform.getFullName()


class ScalarAnglePlugTest(_SpecCase):
    """rotateX・独自のdoubleAngleのget/set。"""

    def test_default_degrees_and_rad_unit(self):
        """既定は度、unit="rad"(別名を含む)はラジアン。通常・fastとも同じ値になる。"""
        rx = self.transform.getPlug("rx")
        for fast in (False, True):
            with self.subTest(fast=fast):
                rx.set(90, fast=fast)
                self.assertAlmostEqual(cmds.getAttr(self.node_name + ".rx"), 90.0)
                self.assertAlmostEqual(rx.get(), 90.0)
                for name in ("rad", "radian", "radians"):
                    self.assertAlmostEqual(rx.get(unit=name), math.pi / 2)
                for name in ("deg", "degree", "degrees"):
                    self.assertAlmostEqual(rx.get(unit=name), 90.0)
                rx.set(math.pi / 4, unit="rad", fast=fast)
                self.assertAlmostEqual(cmds.getAttr(self.node_name + ".rx"), 45.0)
                rx.set(30, unit="degrees", fast=fast)
                self.assertAlmostEqual(cmds.getAttr(self.node_name + ".rx"), 30.0)

    def test_ui_units_are_independent_of_degrees_default(self):
        """UI単位がradでも既定の数値は度。uiUnits=TrueはUI単位で、unitとの同時指定はValueError。"""
        rx = self.transform.getPlug("rx")
        cmds.currentUnit(angle="rad")
        rx.set(90)
        self.assertAlmostEqual(cmds.getAttr(self.node_name + ".rx"), math.pi / 2)
        self.assertAlmostEqual(rx.get(), 90.0)
        self.assertAlmostEqual(rx.get(uiUnits=True), math.pi / 2)
        rx.set(1.0, uiUnits=True)
        self.assertAlmostEqual(rx.get(), math.degrees(1.0))
        with self.assertRaises(ValueError):
            rx.get(unit="deg", uiUnits=True)
        with self.assertRaises(ValueError):
            rx.set(1.0, unit="rad", uiUnits=True)

    def test_invalid_unit(self):
        """未対応の単位名はValueError、文字列以外はTypeError。safe=Trueは値を変えず1を返す。"""
        rx = self.transform.getPlug("rx")
        rx.set(10)
        for bad, error in (("grad", ValueError), ("Deg", ValueError), (1, TypeError)):
            with self.subTest(bad=bad):
                with self.assertRaises(error):
                    rx.get(unit=bad)
                with self.assertRaises(error):
                    rx.set(20, unit=bad)
                with self.assertRaises(error):
                    rx.set(20, unit=bad, fast=True)
                self.assertEqual(rx.set(20, unit=bad, safe=True), 1)
        self.assertAlmostEqual(cmds.getAttr(self.node_name + ".rx"), 10.0)

    def test_safe_and_single_undo(self):
        """safe=Trueも度で書き、通常の設定は1回のUndoで戻る。fastはUndoに記録しない。"""
        rx = self.transform.getPlug("rx")
        self.assertEqual(rx.set(45, safe=True), 0)
        self.assertAlmostEqual(cmds.getAttr(self.node_name + ".rx"), 45.0)
        cmds.flushUndo()
        rx.set(60)
        cmds.undo()
        self.assertAlmostEqual(cmds.getAttr(self.node_name + ".rx"), 45.0)
        cmds.flushUndo()
        rx.set(70, fast=True)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertAlmostEqual(cmds.getAttr(self.node_name + ".rx"), 70.0)

    def test_dynamic_angle_and_multi(self):
        """独自のdoubleAngleとマルチアトリビュートの要素も度。reset・setIfChangedも既定の単位で往復する。"""
        angle = self.transform.addAttr("swing", attributeType="doubleAngle", defaultValue=15)
        self.assertAlmostEqual(angle.get(), 15.0)
        angle.set(40)
        self.assertFalse(angle.setIfChanged(40))
        self.assertTrue(angle.setIfChanged(41))
        self.assertAlmostEqual(cmds.getAttr(angle.getFullName()), 41.0)
        angle.reset()
        self.assertAlmostEqual(cmds.getAttr(angle.getFullName()), 15.0)
        multi = self.transform.addAttr("angles", attributeType="doubleAngle", multi=True)
        multi[2].set(120)
        self.assertEqual({key: round(value, 9) for key, value in multi.get().items()}, {2: 120.0})
        self.assertAlmostEqual(multi.get(unit="rad")[2], math.radians(120))


class CompoundAnglePlugTest(_SpecCase):
    """jointOrient・rotateAxisなど角度の子を持つコンパウンドアトリビュートと、rotateのEulerRotate。"""

    def test_joint_orient_is_degrees(self):
        """jointOrientのgetは度のVector、setは度の数値列。unit="rad"・safe・fastも同じ。"""
        joint = mlib.createNode("joint", name=self.name("jnt"))
        plug = joint.getPlug("jointOrient")
        plug.set((10, 20, 30))
        self.assertEqual([round(v, 9) for v in cmds.getAttr(joint.getFullName() + ".jo")[0]], [10.0, 20.0, 30.0])
        value = plug.get()
        self.assertIsInstance(value, mlib.maths.Vector)
        self.assertEqual([round(v, 9) for v in value], [10.0, 20.0, 30.0])
        self.assertEqual([round(v, 9) for v in plug.get(unit="rad")],
                         [round(math.radians(v), 9) for v in (10, 20, 30)])
        plug.set((0.1, 0.2, 0.3), unit="rad", fast=True)
        self.assertAlmostEqual(cmds.getAttr(joint.getFullName() + ".joz"), math.degrees(0.3))
        joint.getPlug("jointOrientY").setLocked(True)
        self.assertEqual(plug.set((1, 2, 3), safe=True), 1)
        self.assertAlmostEqual(cmds.getAttr(joint.getFullName() + ".jox"), 1.0)
        self.assertAlmostEqual(cmds.getAttr(joint.getFullName() + ".joz"), 3.0)
        self.assertAlmostEqual(joint.getPlug("rotateAxis").set((0, 45, 0)).get()[1], 45.0)

    def test_rotate_returns_euler_rotate_and_accepts_typed_values(self):
        """rotateのgetはEulerRotate(内部rad)。数値列は度、型付きの回転はunitに関係なく自身の単位で書く。"""
        rotate = self.transform.getPlug("rotate")
        rotate.set((90, 0, 0))
        value = rotate.get()
        self.assertIsInstance(value, EulerRotate)
        self.assertAlmostEqual(value.x, math.pi / 2)
        self.assertEqual(tuple(round(v, 9) for v in rotate.get(unit="deg")), (90.0, 0.0, 0.0))
        self.assertAlmostEqual(rotate.get(unit="rad")[0], math.pi / 2)
        for unit in (None, "deg", "rad"):
            with self.subTest(unit=unit):
                cmds.setAttr(self.node_name + ".r", 0, 0, 0)
                rotate.set(EulerRotate(0, 60, 0, unit="deg"), unit=unit)
                self.assertAlmostEqual(cmds.getAttr(self.node_name + ".ry"), 60.0)
                rotate.set(Quaternion.fromAxisAngle((0, 0, 1), 30, unit="deg"), unit=unit)
                self.assertAlmostEqual(cmds.getAttr(self.node_name + ".rz"), 30.0)
        rotate.set(value)
        self.assertAlmostEqual(cmds.getAttr(self.node_name + ".rx"), 90.0)

    def test_rotate_fast_safe_and_undo_once(self):
        """rotateへの度の数値列は通常・fast・safeで同じ値になり、通常は1回のUndoで戻る。"""
        rotate = self.transform.getPlug("rotate")
        for options in ({}, {"fast": True}, {"safe": True}):
            with self.subTest(**options):
                cmds.setAttr(self.node_name + ".r", 0, 0, 0)
                rotate.set((10, 20, 30), **options)
                self.assertEqual([round(v, 9) for v in cmds.getAttr(self.node_name + ".r")[0]], [10.0, 20.0, 30.0])
        cmds.flushUndo()
        rotate.set((40, 50, 60))
        cmds.undo()
        self.assertEqual([round(v, 9) for v in cmds.getAttr(self.node_name + ".r")[0]], [10.0, 20.0, 30.0])


class TransformRotateTest(_SpecCase):
    """Transform.setRotate/getRotate/setQuaternionの単位。"""

    def test_set_rotate_defaults_to_degrees(self):
        """setRotateは既定で度、unit="rad"でラジアン。get=Trueはunitの単位のlist。"""
        self.transform.setRotate((0, 45, 0))
        self.assertAlmostEqual(cmds.getAttr(self.node_name + ".ry"), 45.0)
        self.transform.setRotate((0, math.pi / 2, 0), unit="rad", fast=True)
        self.assertAlmostEqual(cmds.getAttr(self.node_name + ".ry"), 90.0)
        cmds.setAttr(self.node_name + ".r", 0, 0, 0)
        planned = self.transform.setRotate((0, 0, 30), get=True)
        self.assertEqual([round(v, 9) for v in planned], [0.0, 0.0, 30.0])
        planned = self.transform.setRotate((0, 0, math.radians(30)), get=True, unit="rad")
        self.assertAlmostEqual(planned[2], math.radians(30))
        self.transform.setRotate(EulerRotate(0, 0, math.pi / 3))
        self.assertAlmostEqual(cmds.getAttr(self.node_name + ".rz"), 60.0)
        with self.assertRaises(ValueError):
            self.transform.setRotate((0, 0, 0), unit="grad")

    def test_get_rotate_always_returns_euler_rotate(self):
        """getRotateは常にEulerRotateを返し、unit引数を持たない。度はasDegrees()で得る。"""
        cmds.setAttr(self.node_name + ".r", 10, 20, 30)
        rotation = self.transform.getRotate()
        self.assertIsInstance(rotation, EulerRotate)
        self.assertIsInstance(self.transform.getRotate(worldSpace=True, order="zyx"), EulerRotate)
        self.assertEqual([round(v, 9) for v in rotation.asDegrees()], [10.0, 20.0, 30.0])
        for unit in ("deg", "rad", None):
            with self.subTest(unit=unit), self.assertRaises(TypeError):
                self.transform.getRotate(unit=unit)
        self.transform.setRotate(self.transform.getRotate().asDegrees())
        self.assertEqual([round(v, 9) for v in cmds.getAttr(self.node_name + ".r")[0]], [10.0, 20.0, 30.0])
        self.transform.setRotate(self.transform.getRotate())
        self.assertEqual([round(v, 9) for v in cmds.getAttr(self.node_name + ".r")[0]], [10.0, 20.0, 30.0])

    def test_set_quaternion_get_unit(self):
        """setQuaternion(get=True)は既定で度のlist。"""
        q = Quaternion.fromAxisAngle((1, 0, 0), 90, unit="deg")
        self.assertAlmostEqual(self.transform.setQuaternion(q, get=True)[0], 90.0)
        self.assertAlmostEqual(self.transform.setQuaternion(q, get=True, unit="rad")[0], math.pi / 2)


class MathValueUnitTest(_SpecCase):
    """数学型は既定rad(om2互換)のまま、unit="deg"で度から作れる。"""

    def test_euler_rotate_unit(self):
        """EulerRotate(..., unit="deg")は度を受け取り、内部はrad。"""
        value = EulerRotate(0, 60, 0, unit="deg")
        self.assertAlmostEqual(value.y, math.radians(60))
        self.assertEqual(EulerRotate(1, 2, 3).y, 2)
        self.assertEqual(EulerRotate((0, 90, 0), "zyx", unit="deg").order, 5)
        self.assertAlmostEqual(EulerRotate(x=180, unit="degrees").x, math.pi)
        with self.assertRaises(ValueError):
            EulerRotate(0, 0, 0, unit="grad")
        with self.assertRaises(ValueError):
            EulerRotate(om2.MEulerRotation(0, 1, 0), unit="deg")

    def test_quaternion_from_axis_angle_unit(self):
        """Quaternion.fromAxisAngleは既定rad、unit="deg"で度。"""
        expected = Quaternion.fromAxisAngle((0, 1, 0), math.pi / 2)
        self.assertTrue(Quaternion.fromAxisAngle((0, 1, 0), 90, unit="deg").isEquivalent(expected, 1e-12))
        with self.assertRaises(ValueError):
            Quaternion.fromAxisAngle((0, 1, 0), 90, unit="grad")


class DrivenKeyAngleTest(_SpecCase):
    """DrivenKey.setKeyの角度は既定で度。単位なしのドライバーはそのまま。"""

    def test_angle_driver_and_driven(self):
        """角度ドライバー・角度の駆動先とも度。unit="rad"はラジアン。単位なしはそのまま。"""
        driver = self.transform.getPlug("rx")
        target = mlib.getNode(self.make("transform", "target"))
        key = DrivenKey(driver, target.getPlug("ry"))
        key.setKey(0, 0).setKey(90, 45)
        driver.set(90)
        self.assertAlmostEqual(cmds.getAttr(target.getFullName() + ".ry"), 45.0)
        driver.set(45)
        self.assertAlmostEqual(cmds.getAttr(target.getFullName() + ".ry"), 22.5)
        curve = key.getCurves()[0]
        self.assertEqual([round(v, 9) for v in curve.getKeyValues()], [0.0, 45.0])
        key.setKey(math.pi, math.pi / 2, unit="rad")
        driver.set(180)
        self.assertAlmostEqual(cmds.getAttr(target.getFullName() + ".ry"), 90.0)
        unitless = DrivenKey(self.transform.addAttr("blend"), target.getPlug("rz"))
        unitless.setKey(0, 0).setKey(1, 30)
        self.transform.getPlug("blend").set(1)
        self.assertAlmostEqual(cmds.getAttr(target.getFullName() + ".rz"), 30.0)
        with self.assertRaises(ValueError):
            unitless.setKey(0, 0, unit="grad")

    def test_set_key_undo_once(self):
        """setKeyは1回のUndoでキーの追加を戻す。"""
        target = mlib.getNode(self.make("transform", "target"))
        key = DrivenKey(self.transform.getPlug("rx"), target.getPlug("ry"))
        cmds.flushUndo()
        key.setKey(10, 20)
        self.assertTrue(key.exists())
        cmds.undo()
        self.assertFalse(key.exists())


class AddAttrAngleTest(_SpecCase):
    """Node.addAttrの角度の範囲・既定値と、Plug.getMin等の単位。"""

    def test_limits_and_default_in_degrees(self):
        """doubleAngleのmin/max/soft・既定値は既定で度。cmds.attributeQueryの度と一致する。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                plug = self.transform.addAttr("bend%d" % fast, attributeType="doubleAngle", minValue=-45,
                                              maxValue=90, softMinValue=-10, softMaxValue=60, defaultValue=30,
                                              fast=fast)
                name = plug.getLongName()
                self.assertAlmostEqual(cmds.attributeQuery(name, node=self.node_name, minimum=True)[0], -45.0)
                self.assertAlmostEqual(cmds.attributeQuery(name, node=self.node_name, maximum=True)[0], 90.0)
                self.assertAlmostEqual(cmds.attributeQuery(name, node=self.node_name, softMin=True)[0], -10.0)
                self.assertAlmostEqual(cmds.attributeQuery(name, node=self.node_name, softMax=True)[0], 60.0)
                self.assertAlmostEqual(plug.get(), 30.0)
                self.assertIsInstance(plug.getMin(), float)
                self.assertAlmostEqual(plug.getMin(), -45.0)
                self.assertAlmostEqual(plug.getMin(unit="deg"), -45.0)
                self.assertAlmostEqual(plug.getMax(unit="rad"), math.pi / 2)
                self.assertAlmostEqual(plug.getSoftMin(unit="deg"), -10.0)
                self.assertAlmostEqual(plug.getSoftMax(unit="deg"), 60.0)
                self.assertAlmostEqual(plug.getDefault(unit="deg"), 30.0)

    def test_rad_unit_and_angle_children(self):
        """unit="rad"はラジアン。subType="doubleAngle"の子へ配る値も同じ単位で換算する。"""
        plug = self.transform.addAttr("twist", attributeType="doubleAngle", maxValue=math.pi, unit="rad")
        self.assertAlmostEqual(plug.getMax(unit="deg"), 180.0)
        for fast in (False, True):
            with self.subTest(fast=fast):
                compound = self.transform.addAttr("aim%d" % fast, type="double3", subType="doubleAngle",
                                                  defaultValue=(10, 20, 30), maxValue=90, fast=fast)
                child = compound[1]
                self.assertEqual(child.getType(), "doubleAngle")
                self.assertAlmostEqual(child.get(), 20.0)
                self.assertAlmostEqual(child.getMax(unit="deg"), 90.0)
        with self.assertRaises(ValueError):
            self.transform.addAttr("badUnit", attributeType="doubleAngle", unit="grad")
        self.assertFalse(self.transform.hasAttr("badUnit"))


class AnimCurveAngleTest(_SpecCase):
    """角度出力のアニメーションカーブの値・接線の角度は既定で度。"""

    def test_angle_curve_values(self):
        """animCurveTAのsetKey/getKeyValues/evaluateは既定で度、unit="rad"でラジアン。fastも同じ。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                curve = mlib.createNode("animCurveTA", name=self.name("curve%d" % fast))
                curve.setKey(0, 0, fast=fast).setKey(1, 90, fast=fast)
                self.assertEqual([round(v, 9) for v in curve.getKeyValues()], [0.0, 90.0])
                self.assertAlmostEqual(curve.getKeyValues(unit="rad")[1], math.pi / 2)
                self.assertAlmostEqual(curve.evaluate(1), 90.0)
                self.assertAlmostEqual(curve.evaluate(1, unit="rad"), math.pi / 2)
                curve.setKey(2, math.pi, unit="rad", fast=fast)
                self.assertAlmostEqual(curve.getKeyValues()[2], 180.0)
                curve.moveKey(timeOffset=0, valueOffset=10)
                self.assertAlmostEqual(curve.getKeyValues()[1], 100.0)
        linear = mlib.createNode("animCurveTL", name=self.name("linear"))
        linear.setKey(0, 2.5)
        self.assertEqual(linear.getKeyValues(), [2.5])

    def test_tangent_angles(self):
        """getTangent/setTangentの角度は既定で度。cmds.keyTangentの度と一致する。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                curve = mlib.createNode("animCurveTU", name=self.name("tangent%d" % fast))
                curve.setKey(0, 0).setKey(1, 1)
                curve.setTangent(0, inTangentType="fixed", outTangentType="fixed", fast=fast)
                curve.setTangent(0, outAngle=30, fast=fast)
                self.assertAlmostEqual(cmds.keyTangent(str(curve), q=True, index=(0, 0), outAngle=True)[0], 30.0)
                self.assertAlmostEqual(curve.getTangent(0)["outAngle"], 30.0)
                self.assertAlmostEqual(curve.getTangent(0, unit="rad")["outAngle"], math.radians(30))
                curve.setTangent(0, outAngle=math.radians(20), unit="rad", fast=fast)
                self.assertAlmostEqual(curve.getTangent(0)["outAngle"], 20.0)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
