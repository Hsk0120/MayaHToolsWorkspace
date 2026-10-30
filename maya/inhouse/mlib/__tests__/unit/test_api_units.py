"""公開層間の単位境界とfast/Undoの同値性をMayaで検証する。"""
from maya.api.OpenMaya import MSpace
import math
import sys
import unittest
import maya.cmds as cmds
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import mlib


class ApiUnitsTest(unittest.TestCase):
    """UI設定を変えてもオブジェクト値が一定であることを確認する。"""

    def setUp(self):
        """テスト専用シーンとUndoを初期化する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        cmds.undoInfo(state=True)

    def tearDown(self):
        """表示単位を戻す。"""
        cmds.currentUnit(linear="cm", angle="deg", time="film")

    def test_scalar_compound_roundtrip_and_undo(self):
        """単位型のスカラー・コンパウンドアトリビュートの値は度/cm/秒で往復する(unit="rad"はラジアン)。"""
        node = mlib.createNode("transform")
        time = node.addAttr("sampleTime", attributeType="time")
        for linear, angle, frame in (("cm", "deg", "film"), ("m", "rad", "ntsc")):
            cmds.currentUnit(linear=linear, angle=angle, time=frame)
            for fast in (False, True):
                node.getPlug("rx").set(90, fast=fast)
                node.getPlug("translate").set((25, 50, 75), fast=fast)
                time.set(2, fast=fast)
                self.assertAlmostEqual(node.getPlug("rx").get(), 90)
                self.assertAlmostEqual(node.getPlug("rx").get(unit="rad"), math.pi / 2)
                self.assertEqual(tuple(node.getPlug("translate").get()), (25, 50, 75))
                self.assertEqual(time.get(), 2)
                self.assertEqual(time.mplug().asMTime().asUnits(om2.MTime.kSeconds), 2)
                self.assertAlmostEqual(mlib.getPlug(node.getPlug('rx')).get(uiUnits=True), 90 if angle == 'deg' else math.pi / 2)
                self.assertAlmostEqual(mlib.getPlug(node.getPlug('tx')).get(uiUnits=True), 25 if linear == 'cm' else 0.25)
                self.assertAlmostEqual(mlib.getPlug(time).get(uiUnits=True), 48 if frame == 'film' else 60)
            node.getPlug("rx").set(.1, unit="rad")
            cmds.undo()
            self.assertAlmostEqual(node.getPlug("rx").get(), 90)
            cmds.redo()
            self.assertAlmostEqual(node.getPlug("rx").get(unit="rad"), .1)

    def test_creation_limits_and_reset(self):
        """生成と範囲は内部単位。addAttr固有のcmds仕様も維持する。"""
        cmds.currentUnit(linear="m", angle="deg")
        node = mlib.createNode("network")
        angle = node.addAttr("angle", attributeType="doubleAngle", defaultValue=.5, minValue=0, maxValue=1)
        command = mlib.getNode(node).addAttr(longName="commandAngle", attributeType="doubleAngle", defaultValue=90)
        self.assertAlmostEqual(angle.get(), .5)
        self.assertAlmostEqual(command.get(), 90)
        for fast in (False, True):
            angle.set(.75, fast=fast)
            with self.assertRaises(RuntimeError):
                angle.set(1.1, fast=fast)
            angle.reset(fast=fast)
            self.assertAlmostEqual(angle.get(), .5)

    def test_geometry_and_transform_units(self):
        """頂点・CV・行列の位置は表示単位によらずcmで返す。"""
        for shape_name in (cmds.polyCube(ch=False)[0], cmds.curve(d=1, p=[(0, 0, 0), (1, 2, 3)])):
            node = mlib.getNode(shape_name)
            shape = node.getShape()
            item = shape.getVertex(0) if shape.getType() == "mesh" else shape.getCV(0)
            cmds.currentUnit(linear="m")
            for fast in (False, True):
                node.setTranslation((25, 50, 75), fast=fast, at=4)
                self.assertEqual(tuple(node.getTranslation(at=4)), (25, 50, 75))
                self.assertEqual(tuple(node.getPlug("translate").get()), (25, 50, 75))
                # 表示単位mでの0.01・0.02・0.03 = 1・2・3cm。
                cmds.xform(item.getFullName(), objectSpace=True, translation=(0.01, 0.02, 0.03))
                for actual, expected in zip(item.getPosition(), (1, 2, 3)):
                    self.assertAlmostEqual(actual, expected)
                for actual, expected in zip(item.getPosition(worldSpace=True), (26, 52, 78)):
                    self.assertAlmostEqual(actual, expected)
            cmds.currentUnit(linear="cm")

    def test_periodic_cv_index_and_undo(self):
        """API末尾の重複CVを正しい独立CVへ対応付けてUndoする。"""
        shape = mlib.getNode(cmds.circle(ch=False)[0]).getShape()
        fn = shape.mfn()
        index = fn.numCVs - fn.degree
        cv = shape.getCV(index)
        before = cv.getPosition()
        self.assertEqual(cv.getPosition(), shape.getCV(0).getPosition())
        self.assertEqual(cv.getFullName(), shape.getCV(0).getFullName())
        shape.scaleGeometry(2, indices=[index])
        for a, b in zip(cv.getPosition(), before):
            self.assertAlmostEqual(a, b * 2)
        cmds.undo()
        for a, b in zip(cv.getPosition(), before):
            self.assertAlmostEqual(a, b)

    def test_animation_matches_api_for_all_types(self):
        """8種類のキーの入力・出力をMFnAnimCurveの内部単位と比較する。"""
        cmds.currentUnit(linear="m", angle="deg", time="ntsc")
        for suffix in ("TA", "TL", "TT", "TU", "UA", "UL", "UT", "UU"):
            with self.subTest(suffix=suffix):
                curve = mlib.createNode("animCurve" + suffix)
                curve.setKey(0, 0).setKey(2, .5, unit="rad")
                fn = oma2.MFnAnimCurve(curve.mnode())
                input = fn.input(1)
                if isinstance(input, om2.MTime):
                    input = input.asUnits(om2.MTime.kSeconds)
                self.assertAlmostEqual(input, 2)
                if suffix.endswith("T"):
                    # 旧版MFnAnimCurve.evaluateの時間出力には版差があるため、
                    # DG評価されたMTimeをAPIから直接読み取って比較する。
                    if suffix.startswith("T"):
                        cmds.currentTime(om2.MTime(2, om2.MTime.kSeconds).asUnits(om2.MTime.uiUnit()))
                    else:
                        curve.getPlug("input").set(2)
                    evaluated = curve.getPlug("output").mplug().asMTime()
                    self.assertAlmostEqual(evaluated.asUnits(om2.MTime.kSeconds), .5)
                else:
                    self.assertAlmostEqual(fn.value(1), .5)
                self.assertAlmostEqual(curve.getKeyValues(unit="rad")[1], .5)
                self.assertAlmostEqual(curve.evaluate(1, unit="rad"), .25)
                if suffix.endswith("A"):
                    # 角度出力の既定は度。
                    self.assertAlmostEqual(curve.getKeyValues()[1], math.degrees(.5))
                    self.assertAlmostEqual(curve.evaluate(1), math.degrees(.25))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
