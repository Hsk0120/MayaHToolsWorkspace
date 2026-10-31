"""シーン操作の時間の既定を現在のUI時間単位のフレームにした約束(6.0.0)を固定する。

Plug.get/setの時間アトリビュート・Plug.setKeyのtime・AnimCurveのT型入力と時間出力・DrivenKey.setKey・
Node.addAttrの時間の範囲と既定値・Plug.setMin等は既定でフレーム、``timeUnit="sec"`` で秒。
film(24fps)以外の時間単位(ntsc 30fps)でも、フレームの数値がcmdsのUI単位と一致することを確かめる。
U型(無次元入力)のカーブの入力は換算しない。
"""

import math
import sys
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common.drivenKey import DrivenKey
from support.specCase import NamespaceCase

#: 確かめる時間単位と1秒あたりのフレーム数。
_FRAME_RATES = (("film", 24), ("ntsc", 30))


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、時間単位の復元。"""

    PREFIX = "mlibSpecTime_"

    def setUp(self):
        super().setUp()
        self.time_unit = cmds.currentUnit(query=True, time=True)
        self.current_time = cmds.currentTime(query=True)
        cmds.currentUnit(time="film")
        self.transform = mlib.getNode(self.make("transform", "node"))
        self.node_name = self.transform.getFullName()

    def tearDown(self):
        cmds.currentUnit(time=self.time_unit)
        cmds.currentTime(self.current_time)
        super().tearDown()


class PlugSetKeyTimeTest(_SpecCase):
    """Plug.setKeyのtimeは既定でフレーム、timeUnit="sec"で秒。"""

    def test_frames_and_seconds(self):
        """time=フレーム、timeUnit="sec"は秒をフレームへ換算してキーを打つ。"""
        for frame, fps in _FRAME_RATES:
            cmds.currentUnit(time=frame)
            with self.subTest(frame=frame):
                plug = mlib.getNode(self.make("transform", "key#")).getPlug("tx")
                plug.setKey(time=10, value=1)
                plug.setKey(t=2.0, v=2, timeUnit="sec")
                curve = plug.getSource().getNode()
                self.assertEqual(cmds.keyframe(curve.getFullName(), query=True, timeChange=True),
                                 [10.0, 2.0 * fps])
                self.assertEqual(curve.getKeyInputs(), [10.0, 2.0 * fps])

    def test_seconds_rejects_range_strings(self):
        """timeUnit="sec"では数値・数値の並びだけを受け付け、範囲の文字列はキーを作る前にTypeError。"""
        plug = self.transform.getPlug("ty")
        with self.assertRaises(TypeError):
            plug.setKey(time="1:10", timeUnit="sec")
        with self.assertRaises(ValueError):
            plug.setKey(time=1, timeUnit="minute")
        self.assertIsNone(plug.getSource(skipConversionNodes=True))
        plug.setKey(time=0.5, value=3, timeUnit="sec").setKey(time=1.0, value=4, timeUnit="sec")
        curve = plug.getSource().getNode()
        self.assertEqual(curve.getKeyInputs(timeUnit="sec"), [0.5, 1.0])


class AnimCurveTimeTest(_SpecCase):
    """AnimCurveのT型入力・時間出力は既定でフレーム。U型入力は無次元のまま。"""

    def test_time_input_frames_and_seconds(self):
        """animCurveTLのsetKey/getKeyInputs/evaluateは既定でフレーム、timeUnit="sec"で秒。cmdsと一致する。"""
        for frame, fps in _FRAME_RATES:
            cmds.currentUnit(time=frame)
            for fast in (False, True):
                with self.subTest(frame=frame, fast=fast):
                    curve = mlib.createNode("animCurveTL", name=self.name("curve#"))
                    curve.setKey(0, 0, "linear", "linear", fast=fast).setKey(fps, 10, "linear", "linear", fast=fast)
                    curve.setKey(3.0, 30, "linear", "linear", timeUnit="seconds", fast=fast)
                    name = curve.getFullName()
                    self.assertEqual(curve.getKeyInputs(), [0.0, float(fps), 3.0 * fps])
                    self.assertEqual(cmds.keyframe(name, query=True, timeChange=True), [0.0, float(fps), 3.0 * fps])
                    self.assertEqual(curve.getKeyInputs(timeUnit="sec"), [0.0, 1.0, 3.0])
                    self.assertAlmostEqual(curve.evaluate(fps / 2), 5.0)
                    self.assertAlmostEqual(curve.evaluate(0.5, timeUnit="sec"), 5.0)
                    self.assertAlmostEqual(cmds.getAttr(name + ".output", time=fps / 2), 5.0)

    def test_shift_scale_and_mirror_use_frames(self):
        """moveKeyの移動量、scaleKey/mirrorの基準値は既定でフレーム(cmdsのtimeChange・timePivotと同じ)。"""
        for frame, fps in _FRAME_RATES:
            cmds.currentUnit(time=frame)
            with self.subTest(frame=frame):
                curve = mlib.createNode("animCurveTU", name=self.name("shift#"))
                curve.setKey(0, 0).setKey(10, 1)
                curve.moveKey(timeOffset=5)
                self.assertSequenceAlmostEqual(curve.getKeyInputs(), [5, 15], places=4)
                curve.moveKey(timeOffset=1, timeUnit="sec")
                self.assertSequenceAlmostEqual(curve.getKeyInputs(), [5 + fps, 15 + fps], places=4)
                curve.scaleKey(2, 1, 5 + fps)
                self.assertSequenceAlmostEqual(curve.getKeyInputs(), [5 + fps, 25 + fps], places=4)
                curve.mirror(input=True, value=False, inputPivot=5 + fps)
                self.assertSequenceAlmostEqual(curve.getKeyInputs(), [-15 + fps, 5 + fps], places=4)
                curve.scaleKey(1, 1, 0, 0, timeUnit="sec")
                self.assertSequenceAlmostEqual(curve.getKeyInputs(timeUnit="sec"),
                                               [v / fps for v in curve.getKeyInputs()], places=6)

    def test_time_output_frames_and_seconds(self):
        """TT・UT型の時間出力の値も既定でフレーム、timeUnit="sec"で秒。"""
        cmds.currentUnit(time="ntsc")
        for fast in (False, True):
            with self.subTest(kind="TT", fast=fast):
                curve = mlib.createNode("animCurveTT", name=self.name("tt#"))
                curve.setKey(0, 0, fast=fast).setKey(30, 60, fast=fast)
                self.assertEqual(cmds.keyframe(curve.getFullName(), query=True, valueChange=True), [0.0, 60.0])
                self.assertSequenceAlmostEqual(curve.getKeyValues(), [0, 60])
                self.assertSequenceAlmostEqual(curve.getKeyValues(timeUnit="sec"), [0, 2])
                self.assertAlmostEqual(curve.evaluate(15), 30.0)
                self.assertAlmostEqual(curve.evaluate(0.5, timeUnit="sec"), 1.0)
                curve.moveKey(timeOffset=0, valueOffset=30)
                self.assertSequenceAlmostEqual(curve.getKeyValues(), [30, 90])
            with self.subTest(kind="UT", fast=fast):
                curve = mlib.createNode("animCurveUT", name=self.name("ut#"))
                curve.setKey(0, 0, fast=fast).setKey(1, 2.0, timeUnit="sec", fast=fast)
                # U型の入力は無次元のまま、時間出力だけ換算する。
                self.assertEqual(curve.getKeyInputs(), [0.0, 1.0])
                self.assertEqual(curve.getKeyInputs(timeUnit="sec"), [0.0, 1.0])
                self.assertSequenceAlmostEqual(curve.getKeyValues(), [0, 60])
                self.assertAlmostEqual(curve.evaluate(0.5), 30.0)

    def test_unitless_input_is_not_converted(self):
        """U型入力(ドリブンキー用)はtimeUnitに関係なく無次元。"""
        curve = mlib.createNode("animCurveUL", name=self.name("ul"))
        curve.setKey(2, 1, timeUnit="sec", fast=True).moveKey(timeOffset=3, timeUnit="sec")
        self.assertEqual(curve.getKeyInputs(), [5.0])
        self.assertAlmostEqual(curve.evaluate(5, timeUnit="sec"), 1.0)

    def test_invalid_time_unit(self):
        """timeUnitの型・名前の誤りは編集前に型付きの例外にする。"""
        curve = mlib.createNode("animCurveTL", name=self.name("bad"))
        with self.assertRaises(TypeError):
            curve.setKey(1, 1, timeUnit=1)
        with self.assertRaises(ValueError):
            curve.setKey(1, 1, timeUnit="minute")
        with self.assertRaisesRegex(ValueError, "unit for angle"):
            curve.getKeyInputs(timeUnit="rad")
        self.assertEqual(curve.getKeyCount(), 0)

    def test_set_key_undo_once(self):
        """setKeyは1回のUndoでキーの追加を戻す。fastはUndoに記録しない。"""
        curve = mlib.createNode("animCurveTL", name=self.name("undo"))
        cmds.flushUndo()
        curve.setKey(1.0, 5, timeUnit="sec")
        self.assertEqual(curve.getKeyInputs(), [24.0])
        cmds.undo()
        self.assertEqual(curve.getKeyCount(), 0)


class DrivenKeyTimeTest(_SpecCase):
    """DrivenKey.setKeyの時間のドライバー・駆動先は既定でフレーム。"""

    def test_time_driver_frames_and_seconds(self):
        """時間ドライバー(time1.outTimeと同じ型)の値はフレーム、timeUnit="sec"で秒。"""
        cmds.currentUnit(time="ntsc")
        driver = self.transform.addAttr("clock", attributeType="time")
        key = DrivenKey(driver, self.transform.getPlug("ty"))
        key.setKey(0, 0).setKey(30, 10).setKey(2.0, 20, timeUnit="sec")
        curve = key.getCurves()[0]
        self.assertEqual(cmds.keyframe(curve.getFullName(), query=True, floatChange=True), [0.0, 30.0, 60.0])
        driver.set(15)
        self.assertAlmostEqual(cmds.getAttr(self.node_name + ".ty"), 5.0)
        with self.assertRaises(ValueError):
            key.setKey(1, 1, timeUnit="minute")

    def test_time_driven(self):
        """時間の駆動先の値もフレーム。"""
        cmds.currentUnit(time="ntsc")
        driven = self.transform.addAttr("delay", attributeType="time")
        key = DrivenKey(self.transform.getPlug("tx"), driven)
        key.setKey(0, 0).setKey(1, 30)
        self.transform.getPlug("tx").set(1)
        self.assertAlmostEqual(cmds.getAttr(driven.getFullName()), 30.0)
        self.assertAlmostEqual(driven.get(timeUnit="sec"), 1.0)


class AddAttrTimeTest(_SpecCase):
    """Node.addAttrとPlug.setMin等の時間の範囲・既定値。"""

    def test_limits_in_frames_and_seconds(self):
        """timeのmin/max/softは既定でフレーム、timeUnit="sec"で秒。cmds.attributeQueryのUI単位と一致する。"""
        cmds.currentUnit(time="ntsc")
        for fast in (False, True):
            with self.subTest(fast=fast):
                plug = self.transform.addAttr("clip%d" % fast, attributeType="time", minValue=-30, maxValue=90,
                                              softMinValue=0, softMaxValue=60, fast=fast)
                name = plug.getLongName()
                self.assertAlmostEqual(cmds.attributeQuery(name, node=self.node_name, minimum=True)[0], -30.0)
                self.assertAlmostEqual(cmds.attributeQuery(name, node=self.node_name, maximum=True)[0], 90.0)
                self.assertAlmostEqual(cmds.attributeQuery(name, node=self.node_name, softMin=True)[0], 0.0)
                self.assertAlmostEqual(cmds.attributeQuery(name, node=self.node_name, softMax=True)[0], 60.0)
                self.assertIsInstance(plug.getMin(), om2.MTime)
                self.assertAlmostEqual(plug.getMin(timeUnit="frame"), -30.0)
                self.assertAlmostEqual(plug.getMax(timeUnit="sec"), 3.0)
                self.assertAlmostEqual(plug.getSoftMax(timeUnit="sec"), 2.0)
                self.assertAlmostEqual(plug.getMax(uiUnits=True), 90.0)
                with self.assertRaises(ValueError):
                    plug.getMax(timeUnit="sec", uiUnits=True)
        seconds = self.transform.addAttr("clipSec", attributeType="time", maxValue=2, timeUnit="sec")
        self.assertAlmostEqual(cmds.attributeQuery("clipSec", node=self.node_name, maximum=True)[0], 60.0)
        seconds.setMax(45)
        self.assertAlmostEqual(cmds.attributeQuery("clipSec", node=self.node_name, maximum=True)[0], 45.0)
        seconds.setMax(1.0, timeUnit="sec")
        self.assertAlmostEqual(cmds.attributeQuery("clipSec", node=self.node_name, maximum=True)[0], 30.0)
        seconds.setMin(om2.MTime(10, om2.MTime.uiUnit()), timeUnit="sec")
        self.assertAlmostEqual(cmds.attributeQuery("clipSec", node=self.node_name, minimum=True)[0], 10.0)
        with self.assertRaises(ValueError):
            self.transform.addAttr("badTime", attributeType="time", timeUnit="minute")
        self.assertFalse(self.transform.hasAttr("badTime"))

    def test_reset_keeps_seconds_internally(self):
        """resetは既定値をUI単位に依らず戻す(内部の秒で書き込む)。"""
        cmds.currentUnit(time="ntsc")
        plug = self.transform.addAttr("hold", attributeType="time")
        plug.set(45)
        plug.reset()
        self.assertAlmostEqual(plug.get(), 0.0)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
