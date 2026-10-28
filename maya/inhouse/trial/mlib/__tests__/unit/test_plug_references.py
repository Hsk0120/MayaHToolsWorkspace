"""参照取得を値・状態照会から分離し、型・単位・非評価を検証する。"""

import importlib
import math
import sys
import unittest
from unittest.mock import patch

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import mlib


class PlugReferencesTest(unittest.TestCase):
    """参照取得は入力型や表示単位によらず同じ役割を持つ。"""

    def setUp(self):
        """独立したシーンと既定の表示単位を用意する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        cmds.undoInfo(state=True)
        self.node = mlib.createNode("transform", name="referenceTarget")

    def tearDown(self):
        """表示単位を復元する。"""
        cmds.currentUnit(linear="cm", angle="deg", time="film")

    def test_reference_entry_keeps_types_and_identity(self):
        """文字列・MPlug・既存PlugをgetPlugだけで型付き参照へ解決する。"""
        entry = importlib.import_module("mlib.cmds.getPlug").getPlug
        self.assertIs(mlib.getPlug, entry)
        self.assertIs(mlib.cmds.getPlug, entry)
        self.assertFalse(hasattr(mlib, "getAttr"))
        self.assertFalse(hasattr(mlib.cmds, "getAttr"))
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("mlib.cmds.getAttr")
        samples = self.node.addAttr("samples", attributeType="double", multi=True)
        samples[3].set(4.0)
        label = self.node.addAttr("label", dataType="string").set("sample")
        cases = (
            (self.node.getPlug("translateX"), mlib.plugs.DoubleLinearPlug),
            (self.node.getPlug("rotateX"), mlib.plugs.DoubleAnglePlug),
            (self.node.getPlug("translate"), mlib.plugs.Double3Plug),
            (self.node.getPlug("worldMatrix[0]"), mlib.plugs.MatrixPlug),
            (samples, mlib.plugs.ArrayPlug), (label, mlib.plugs.StringPlug),
        )
        for plug, expected in cases:
            with self.subTest(type=expected.__name__):
                self.assertIs(entry(plug), plug)
                self.assertIsInstance(entry(plug.getFullName()), expected)
                self.assertIsInstance(entry(plug.mplug()), expected)
                self.assertEqual(entry(plug.mplug()), plug)
        self.assertEqual(entry(samples).get(), {3: 4.0})
        self.assertEqual(entry(label).get(), "sample")
        self.assertIsInstance(entry(self.node.getPlug("translate")).get(), mlib.maths.Vector)
        self.assertIsInstance(entry(self.node.getPlug("worldMatrix[0]")).get(), mlib.maths.Matrix)

    def test_reference_values_and_explicit_ui_units(self):
        """参照の取得では単位を選ばず、値のgetで明示的に選ぶ。"""
        angle = self.node.getPlug("rotateX").set(math.pi / 2)
        distance = self.node.getPlug("translateX").set(25)
        time = self.node.addAttr("sampleTime", attributeType="time").set(2)
        for linear, angular, frame in (("cm", "deg", "film"), ("m", "rad", "ntsc")):
            with self.subTest(linear=linear, angular=angular, frame=frame):
                cmds.currentUnit(linear=linear, angle=angular, time=frame)
                self.assertIs(mlib.getPlug(angle), angle)
                self.assertAlmostEqual(angle.get(), math.pi / 2)
                self.assertEqual(distance.get(), 25)
                self.assertEqual(time.get(), 2)
                self.assertAlmostEqual(angle.get(uiUnits=True), 90 if angular == "deg" else math.pi / 2)
                self.assertAlmostEqual(distance.get(uiUnits=True), 25 if linear == "cm" else 0.25)
                self.assertAlmostEqual(time.get(uiUnits=True), 48 if frame == "film" else 60)

    def test_sparse_reference_does_not_query_values_or_create_elements(self):
        """参照取得と列挙は欠番を実体化せず、Undo履歴を追加しない。"""
        numeric = self.node.addAttr("samples", attributeType="double", multi=True)
        message = self.node.addAttr("links", attributeType="message", multi=True)
        undo_name = cmds.undoInfo(query=True, undoName=True)
        with patch.object(cmds, "getAttr", side_effect=AssertionError("value query during resolution")):
            for array, index in ((numeric, 9), (message, 7)):
                element = mlib.getPlug(array.getFullName() + f"[{index}]")
                self.assertIs(mlib.getPlug(element), element)
                self.assertEqual(list(array.mplug().getExistingArrayAttributeIndices()), [])
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)

    def test_state_and_reference_are_separate_operations(self):
        """状態は専用照会で取得し、参照入口へ照会フラグを渡さない。"""
        angle = self.node.getPlug("rotateX")
        self.assertEqual(angle.getType(), "doubleAngle")
        self.assertTrue(angle.isSettable())
        angle.setLocked(True)
        self.assertTrue(angle.isLocked())
        self.assertFalse(angle.isSettable())
        with self.assertRaises(TypeError):
            mlib.getPlug(angle, lock=False)

    def test_input_rejection_and_invalid_reference_lifetime(self):
        """入力解決の拒否規則と、保持参照の削除後検査を維持する。"""
        for value in (None, True, 1, [], self.node):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(TypeError):
                    mlib.getPlug(value)
        for value in ("", om2.MPlug()):
            with self.assertRaises(ValueError):
                mlib.getPlug(value)
        with self.assertRaises(TypeError):
            mlib.getPlug(self.node.getFullName())
        with self.assertRaises(RuntimeError):
            mlib.getPlug(self.node.getFullName() + ".missingAttribute")
        plug = self.node.getPlug("translateX")
        cmds.delete(self.node.getFullName())
        self.assertIs(mlib.getPlug(plug), plug)
        self.assertFalse(plug.isValid())
        with self.assertRaises(RuntimeError):
            plug.get()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
