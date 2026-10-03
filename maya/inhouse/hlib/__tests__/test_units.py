"""Preferencesとnative_units を検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds
import maya.api.OpenMaya as om2

import hlib
hlib.reload()
from hlib.environment import Preferences
from hlib.utils import units
from hlib.decorators import nativeUnits


class UnitsTest(unittest.TestCase):
    """現在のUI単位の取得・設定と nativeUnits の一時切り替えを検証する。"""

    def setUp(self):
        self.previous_linear = cmds.currentUnit(query=True, linear=True)
        self.previous_angle = cmds.currentUnit(query=True, angle=True)
        self.previous_time = cmds.currentUnit(query=True, time=True)

    def tearDown(self):
        cmds.currentUnit(linear=self.previous_linear, angle=self.previous_angle, time=self.previous_time)

    def test_linear_get_set_round_trip(self):
        self.assertEqual(Preferences.getLinearUnit(), self.previous_linear)
        Preferences.setLinearUnit("m")
        self.assertEqual(Preferences.getLinearUnit(), "m")
        self.assertEqual(cmds.currentUnit(query=True, linear=True), "m")

    def test_angle_get_set_round_trip(self):
        Preferences.setAngleUnit("rad")
        self.assertEqual(Preferences.getAngleUnit(), "rad")
        Preferences.setAngleUnit("deg")
        self.assertEqual(Preferences.getAngleUnit(), "deg")

    def test_time_get_set_round_trip(self):
        Preferences.setTimeUnit("ntsc")
        self.assertEqual(Preferences.getTimeUnit(), "ntsc")
        Preferences.setTimeUnit("film")
        self.assertEqual(Preferences.getTimeUnit(), "film")

    def test_set_linear_supports_undo(self):
        if not cmds.undoInfo(query=True, state=True):
            self.skipTest("Undo is disabled in this Maya session")
        Preferences.setLinearUnit("m")
        self.assertEqual(Preferences.getLinearUnit(), "m")
        cmds.undo()
        self.assertEqual(Preferences.getLinearUnit(), self.previous_linear)

    def test_native_units_forces_cm_and_radians_then_restores(self):
        Preferences.setLinearUnit("m")
        Preferences.setAngleUnit("deg")

        with nativeUnits():
            self.assertEqual(om2.MDistance.uiUnit(), om2.MDistance.kCentimeters)
            self.assertEqual(om2.MAngle.uiUnit(), om2.MAngle.kRadians)

        self.assertEqual(om2.MDistance.uiUnit(), om2.MDistance.kMeters)
        self.assertEqual(om2.MAngle.uiUnit(), om2.MAngle.kDegrees)
        self.assertEqual(Preferences.getLinearUnit(), "m")
        self.assertEqual(Preferences.getAngleUnit(), "deg")

    def test_native_units_restores_even_on_exception(self):
        Preferences.setLinearUnit("m")
        with self.assertRaises(ValueError):
            with nativeUnits():
                self.assertEqual(om2.MDistance.uiUnit(), om2.MDistance.kCentimeters)
                raise ValueError("boom")
        self.assertEqual(om2.MDistance.uiUnit(), om2.MDistance.kMeters)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
