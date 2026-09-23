"""hlib.units の Units/native_units を検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds
import maya.api.OpenMaya as om2

import hlib
hlib.reload()
from hlib.units import Units, native_units


class UnitsTest(unittest.TestCase):
    """現在のUI単位の取得・設定と native_units の一時切り替えを検証する。"""

    def setUp(self):
        self.previous_linear = cmds.currentUnit(query=True, linear=True)
        self.previous_angle = cmds.currentUnit(query=True, angle=True)
        self.previous_time = cmds.currentUnit(query=True, time=True)

    def tearDown(self):
        cmds.currentUnit(linear=self.previous_linear, angle=self.previous_angle, time=self.previous_time)

    def test_linear_get_set_round_trip(self):
        self.assertEqual(Units.linear(), self.previous_linear)
        Units.set_linear("m")
        self.assertEqual(Units.linear(), "m")
        self.assertEqual(cmds.currentUnit(query=True, linear=True), "m")

    def test_angle_get_set_round_trip(self):
        Units.set_angle("rad")
        self.assertEqual(Units.angle(), "rad")
        Units.set_angle("deg")
        self.assertEqual(Units.angle(), "deg")

    def test_time_get_set_round_trip(self):
        Units.set_time("ntsc")
        self.assertEqual(Units.time(), "ntsc")
        Units.set_time("film")
        self.assertEqual(Units.time(), "film")

    def test_set_linear_supports_undo(self):
        if not cmds.undoInfo(query=True, state=True):
            self.skipTest("Undo is disabled in this Maya session")
        Units.set_linear("m")
        self.assertEqual(Units.linear(), "m")
        cmds.undo()
        self.assertEqual(Units.linear(), self.previous_linear)

    def test_native_units_forces_cm_and_radians_then_restores(self):
        Units.set_linear("m")
        Units.set_angle("deg")

        with native_units():
            self.assertEqual(om2.MDistance.uiUnit(), om2.MDistance.kCentimeters)
            self.assertEqual(om2.MAngle.uiUnit(), om2.MAngle.kRadians)

        self.assertEqual(om2.MDistance.uiUnit(), om2.MDistance.kMeters)
        self.assertEqual(om2.MAngle.uiUnit(), om2.MAngle.kDegrees)
        self.assertEqual(Units.linear(), "m")
        self.assertEqual(Units.angle(), "deg")

    def test_native_units_restores_even_on_exception(self):
        Units.set_linear("m")
        with self.assertRaises(ValueError):
            with native_units():
                self.assertEqual(om2.MDistance.uiUnit(), om2.MDistance.kCentimeters)
                raise ValueError("boom")
        self.assertEqual(om2.MDistance.uiUnit(), om2.MDistance.kMeters)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
