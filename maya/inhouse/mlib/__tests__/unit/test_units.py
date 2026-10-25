"""単位変換とnativeUnits を検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds
import maya.api.OpenMaya as om2

import mlib
mlib.reload()
from mlib.common import units
from mlib.decorator import nativeUnits


class UnitsTest(unittest.TestCase):
    """現在のUI単位の取得・設定と nativeUnits の一時切り替えを検証する。"""

    def setUp(self):
        self.previous_linear = cmds.currentUnit(query=True, linear=True)
        self.previous_angle = cmds.currentUnit(query=True, angle=True)
        self.previous_time = cmds.currentUnit(query=True, time=True)

    def tearDown(self):
        cmds.currentUnit(linear=self.previous_linear, angle=self.previous_angle, time=self.previous_time)





    def test_native_units_forces_cm_and_radians_then_restores(self):
        cmds.currentUnit(linear="m")
        cmds.currentUnit(angle="deg")

        with nativeUnits():
            self.assertEqual(om2.MDistance.uiUnit(), om2.MDistance.kCentimeters)
            self.assertEqual(om2.MAngle.uiUnit(), om2.MAngle.kRadians)

        self.assertEqual(om2.MDistance.uiUnit(), om2.MDistance.kMeters)
        self.assertEqual(om2.MAngle.uiUnit(), om2.MAngle.kDegrees)
        self.assertEqual(cmds.currentUnit(query=True, linear=True), "m")
        self.assertEqual(cmds.currentUnit(query=True, angle=True), "deg")

    def test_native_units_restores_even_on_exception(self):
        cmds.currentUnit(linear="m")
        with self.assertRaises(ValueError):
            with nativeUnits():
                self.assertEqual(om2.MDistance.uiUnit(), om2.MDistance.kCentimeters)
                raise ValueError("boom")
        self.assertEqual(om2.MDistance.uiUnit(), om2.MDistance.kMeters)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
