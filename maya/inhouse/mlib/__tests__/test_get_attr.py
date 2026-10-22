"""getAttrのPlug取得と、明示フラグによる既存Maya照会を検証する。"""

import importlib
import math
import sys
import unittest
from unittest.mock import patch

import mlib
import maya.api.OpenMaya as om2
import maya.cmds as cmds


class GetAttrTest(unittest.TestCase):
    """省略時の参照取得とフラグ指定時の値・状態取得を分けて確認する。"""

    def setUp(self):
        """独立した空シーンと既定の表示単位を用意する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        cmds.undoInfo(state=True)
        self.node = mlib.createNode("transform", name="getAttrTarget")

    def tearDown(self):
        """変更した表示単位を既定値へ戻す。"""
        cmds.currentUnit(linear="cm", angle="deg", time="film")

    def test_public_entries_return_typed_plugs_and_preserve_existing_identity(self):
        """文字列・MPlug・既存Plugは同じ公開入口で型付き参照へ解決する。"""
        entry = importlib.import_module("mlib.cmds.getAttr").getAttr
        self.assertIs(mlib.getAttr, entry)
        self.assertIs(mlib.cmds.getAttr, entry)
        values = self.node.addAttr("samples", attributeType="double", multi=True)
        values[3].set(4.0)
        label = self.node.addAttr("label", dataType="string")
        label.set("sample")
        cases = (
            (self.node.getPlug("translateX"), mlib.plugs.DoubleLinearPlug),
            (self.node.getPlug("rotateX"), mlib.plugs.DoubleAnglePlug),
            (self.node.getPlug("translate"), mlib.plugs.Double3Plug),
            (self.node.getPlug("worldMatrix[0]"), mlib.plugs.MatrixPlug),
            (values, mlib.plugs.ArrayPlug),
            (label, mlib.plugs.StringPlug),
        )
        for plug, expected in cases:
            with self.subTest(type=expected.__name__):
                self.assertIs(entry(plug), plug)
                self.assertIsInstance(entry(str(plug)), expected)
                self.assertIsInstance(entry(plug.mplug()), expected)
                self.assertEqual(entry(plug.mplug()), plug)
        self.assertEqual(mlib.getAttr(values).get(), {3: 4.0})
        self.assertEqual(mlib.getAttr(label).get(), "sample")
        self.assertIsInstance(mlib.getAttr(self.node.getPlug("translate")).get(), mlib.maths.Vector)
        self.assertIsInstance(mlib.getAttr(self.node.getPlug("worldMatrix[0]")).get(), mlib.maths.Matrix)

    def test_reference_values_keep_fixed_units_and_getu_tracks_ui_units(self):
        """返したPlugのgetはrad/cm/秒、getuは度/m/フレームへ追従する。"""
        angle = self.node.getPlug("rotateX")
        distance = self.node.getPlug("translateX")
        time = self.node.addAttr("sampleTime", attributeType="time")
        angle.set(math.pi / 2)
        distance.set(25)
        time.set(2)
        for linear, angular, frame in (("cm", "deg", "film"), ("m", "rad", "ntsc")):
            with self.subTest(linear=linear, angular=angular, frame=frame):
                cmds.currentUnit(linear=linear, angle=angular, time=frame)
                self.assertIs(mlib.getAttr(angle), angle)
                self.assertAlmostEqual(mlib.getAttr(angle).get(), math.pi / 2)
                self.assertEqual(mlib.getAttr(distance).get(), 25)
                self.assertEqual(mlib.getAttr(time).get(), 2)
                self.assertAlmostEqual(mlib.getAttr(angle).get(uiUnits=True), 90 if angular == 'deg' else math.pi / 2)
                self.assertAlmostEqual(mlib.getAttr(distance).get(uiUnits=True), 25 if linear == 'cm' else 0.25)
                self.assertAlmostEqual(mlib.getAttr(time).get(uiUnits=True), 48 if frame == 'film' else 60)
                self.assertAlmostEqual(mlib.getAttr(angle, time=3), cmds.getAttr(str(angle), time=3))

    def test_missing_sparse_references_do_not_evaluate_or_materialize_elements(self):
        """省略時の取得は値照会とUndo登録をせず、未作成の要素を実体化しない。"""
        numeric = self.node.addAttr("samples", attributeType="double", multi=True)
        message = self.node.addAttr("links", attributeType="message", multi=True)
        before = [list(array.mplug().getExistingArrayAttributeIndices()) for array in (numeric, message)]
        undo_name = cmds.undoInfo(query=True, undoName=True)
        with patch.object(cmds, "getAttr", side_effect=AssertionError("value query during reference resolution")):
            numeric_element = mlib.getAttr(str(numeric) + "[9]")
            message_element = mlib.getAttr(str(message) + "[7]")
            self.assertIsInstance(numeric_element, mlib.plugs.DoublePlug)
            self.assertIsInstance(message_element, mlib.plugs.MessagePlug)
            self.assertIs(mlib.getAttr(numeric_element), numeric_element)
            self.assertIsInstance(mlib.getAttr(numeric_element.mplug()), mlib.plugs.DoublePlug)
        after = [list(array.mplug().getExistingArrayAttributeIndices()) for array in (numeric, message)]
        self.assertEqual(after, before)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)

    def test_explicit_flags_keep_value_state_aliases_and_mathematical_wrapping(self):
        """フラグの存在で従来照会へ入り、False値・time・silentも値を返す。"""
        angle = self.node.getPlug("rotateX")
        angle.set(math.pi / 2)
        self.assertEqual(mlib.getAttr(angle, typ=True), "doubleAngle")
        for flag in ("lock", "keyable", "channelBox", "settable"):
            self.assertEqual(mlib.getAttr(angle, **{flag: True}), cmds.getAttr(str(angle), **{flag: True}))
        angle.setLocked(True)
        self.assertTrue(mlib.getAttr(angle, l=True))
        self.assertFalse(mlib.getAttr(angle, settable=True))
        angle.setLocked(False)
        for flags in ({"lock": False}, {"type": False}, {"silent": True}, {"silent": False}):
            self.assertEqual(mlib.getAttr(angle, **flags), cmds.getAttr(str(angle), **flags))
        enum = self.node.addAttr("mode", attributeType="enum", enumName="first:second", defaultValue=1)
        self.assertEqual(mlib.getAttr(enum, asString=True), "second")
        numeric = self.node.addAttr("samples", attributeType="double", multi=True)
        numeric[3].set(4.0)
        numeric[9].set(10.0)
        self.assertEqual(mlib.getAttr(numeric, mi=True), [3, 9])
        translate = self.node.getPlug("translate")
        self.assertIs(type(mlib.getAttr(translate, silent=True)), mlib.maths.Vector)
        matrix = self.node.getPlug("worldMatrix[0]")
        self.assertIsInstance(mlib.getAttr(matrix, type=False), mlib.maths.Matrix)
        animated = self.node.addAttr("animated", attributeType="double")
        animated.setKey(t=1, v=2)
        animated.setKey(t=8, v=9)
        self.assertEqual(mlib.getAttr(animated, time=1), 2)
        self.assertEqual(mlib.getAttr(animated, t=8), 9)
        with patch.object(cmds, "getAttr", side_effect=AssertionError("duplicate flags reached Maya")):
            for flags in ({"type": True, "typ": True}, {"time": 1, "t": 1}, {"lock": True, "l": True}):
                with self.subTest(flags=flags):
                    with self.assertRaises(TypeError):
                        mlib.getAttr(angle, **flags)

    def test_shared_input_rejection_and_invalid_existing_plug_identity(self):
        """getPlugと同じ入力拒否を使い、保持済み参照の値読取まで検証を遅らせる。"""
        for value in (None, True, 1, [], self.node):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(TypeError):
                    mlib.getAttr(value)
        for value in ("", om2.MPlug()):
            with self.assertRaises(ValueError):
                mlib.getAttr(value)
        with self.assertRaises(TypeError):
            mlib.getAttr(str(self.node))
        with self.assertRaises(RuntimeError):
            mlib.getAttr(str(self.node) + ".missingAttribute")
        plug = self.node.getPlug("translateX")
        cmds.delete(str(self.node))
        self.assertIs(mlib.getAttr(plug), plug)
        self.assertFalse(plug.isValid())
        with self.assertRaises(RuntimeError):
            mlib.getAttr(plug).get()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
