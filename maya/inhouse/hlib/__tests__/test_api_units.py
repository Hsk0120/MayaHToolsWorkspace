"""公開層間の単位境界とfast/Undoの同値性をMayaで検証する。"""
from maya.api.OpenMaya import MSpace
import math
import sys
import unittest
import maya.cmds as cmds
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import hlib


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
        """単位型のスカラー・複合値はrad/cm/秒で往復する。"""
        node = hlib.createNode("transform")
        time = node.addAttr("sampleTime", attributeType="time")
        for linear, angle, frame in (("cm", "deg", "film"), ("m", "rad", "ntsc")):
            cmds.currentUnit(linear=linear, angle=angle, time=frame)
            for fast in (False, True):
                node.plug("rx").set(math.pi / 2, fast=fast)
                node.plug("translate").set((25, 50, 75), fast=fast)
                time.set(2, fast=fast)
                self.assertAlmostEqual(node.plug("rx").get(), math.pi / 2)
                self.assertEqual(tuple(node.plug("translate").get()), (25, 50, 75))
                self.assertEqual(time.get(), 2)
                self.assertEqual(time.mplug().asMTime().asUnits(om2.MTime.kSeconds), 2)
                self.assertAlmostEqual(hlib.getAttr(node.plug("rx")), 90 if angle == "deg" else math.pi / 2)
                self.assertAlmostEqual(hlib.getAttr(node.plug("tx")), 25 if linear == "cm" else .25)
                self.assertAlmostEqual(hlib.getAttr(time), 48 if frame == "film" else 60)
            node.plug("rx").set(.1)
            cmds.undo()
            self.assertAlmostEqual(node.plug("rx").get(), math.pi / 2)
            cmds.redo()
            self.assertAlmostEqual(node.plug("rx").get(), .1)

    def test_creation_limits_and_reset(self):
        """生成と範囲は内部単位。addAttr固有のcmds仕様も維持する。"""
        cmds.currentUnit(linear="m", angle="deg")
        node = hlib.createNode("network")
        angle = node.addAttr("angle", attributeType="doubleAngle", defaultValue=.5, minValue=0, maxValue=1)
        command = hlib.addAttr(node, longName="commandAngle", attributeType="doubleAngle", defaultValue=90)
        self.assertAlmostEqual(angle.get(), .5)
        self.assertAlmostEqual(command.get(), 90)
        for fast in (False, True):
            angle.set(.75, fast=fast)
            with self.assertRaises(RuntimeError):
                angle.set(1.1, fast=fast)
            angle.reset(fast=fast)
            self.assertAlmostEqual(angle.get(), .5)

    def test_geometry_and_transform_units(self):
        """頂点・CV・行列の位置は表示単位によらずcmで一致する。"""
        for shape_name in (cmds.polyCube(ch=False)[0], cmds.curve(d=1, p=[(0, 0, 0), (1, 2, 3)])):
            node = hlib.getNode(shape_name)
            shape = node.shape()
            item = shape.vertex(0) if shape.type() == "mesh" else shape.cv(0)
            cmds.currentUnit(linear="m")
            for fast in (False, True):
                node.setTranslation((25, 50, 75), fast=fast, at=4)
                self.assertEqual(tuple(node.getTranslation(at=4)), (25, 50, 75))
                self.assertEqual(tuple(node.plug("translate").get()), (25, 50, 75))
                item.setPosition((1, 2, 3), fast=fast)
                self.assertEqual(item.getPosition(), (1, 2, 3))
                self.assertEqual(item.getPosition(ws=True), (26, 52, 78))
            item.setPosition((4, 5, 6))
            cmds.undo()
            self.assertEqual(item.getPosition(), (1, 2, 3))
            cmds.currentUnit(linear="cm")

    def test_periodic_cv_index_and_undo(self):
        """API末尾の重複CVを正しい独立CVへ対応付けてUndoする。"""
        shape = hlib.getNode(cmds.circle(ch=False)[0]).shape()
        fn = shape.curveFn()
        index = fn.numCVs - fn.degree
        cv = shape.cv(index)
        before = cv.getPosition()
        self.assertEqual(cv.getPosition(), shape.cv(0).getPosition())
        self.assertEqual(cv.fullName(), shape.cv(0).fullName())
        cv.setPosition((1, 2, 3))
        self.assertEqual(cv.getPosition(), (1, 2, 3))
        cmds.undo()
        for a, b in zip(cv.getPosition(), before):
            self.assertAlmostEqual(a, b)
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
                curve = hlib.createNode("animCurve" + suffix)
                curve.setKey(0, 0).setKey(2, .5)
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
                        curve.plug("input").set(2)
                    evaluated = curve.plug("output").mplug().asMTime()
                    self.assertAlmostEqual(evaluated.asUnits(om2.MTime.kSeconds), .5)
                else:
                    self.assertAlmostEqual(fn.value(1), .5)
                self.assertAlmostEqual(curve.keyValues()[1], .5)
                self.assertAlmostEqual(curve.evaluate(1), .25)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
