"""象限ごとに限界角が違う楕円コーンのSwing制限を、Quaternionで求めた期待値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import AsymmetricSwingLimit, SwingLimit


def _rotation(matrix):
    """行列の回転をQuaternionで返す。"""
    return om.MTransformationMatrix(om.MMatrix(matrix)).rotation(asQuaternion=True)


def _expected(rest, current, axis, limits, softness):
    """生成時の姿勢restと現在の姿勢currentから期待値を計算する。

    Returns:
        tuple: (期待する親空間の行列, θ, 限界角, 制限後の角度)。
    """
    rest_rotation = _rotation(rest)
    delta = _rotation(current) * rest_rotation.inverse()
    index = "xyz".index(axis)
    components = [delta.x, delta.y, delta.z]
    twist = om.MQuaternion(*[v if i == index else 0 for i, v in enumerate(components)], delta.w)
    length = math.sqrt(components[index] ** 2 + delta.w ** 2)
    twist = twist.normalizeIt() if length > 1e-9 else om.MQuaternion()
    swing = twist.inverse() * delta
    unit = om.MVector(*[float(i == index) for i in range(3)])
    tip = unit.rotateBy(swing)
    angle = math.degrees(unit.angle(tip))
    first, second = SwingLimit.perpendicularAxes(axis)
    limit = AsymmetricSwingLimit.asymmetricLimitAngle(
        *limits, tip["xyz".index(first)], tip["xyz".index(second)]
    )
    limited = SwingLimit.softAngle(angle, limit, softness)
    ratio = limited / angle if angle > 1e-4 else 1.0
    result = twist * om.MQuaternion.slerp(om.MQuaternion(), swing, ratio) * rest_rotation
    matrix = om.MTransformationMatrix(result.asMatrix())
    matrix.setTranslation(
        om.MTransformationMatrix(om.MMatrix(current)).translation(om.MSpace.kTransform), om.MSpace.kTransform
    )
    return matrix.asMatrix(), angle, limit, limited


class AsymmetricSwingLimitTest(unittest.TestCase):
    """標準ノードの数値評価・象限ごとの限界・連続性・引数検査を確認する。"""

    LIMITS = (80, 30, 60, 20)

    def setUp(self):
        """親付き入力jointを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.parent = cmds.createNode("transform")
        self.joint = cmds.createNode("joint", parent=self.parent)

    def local(self):
        """入力jointの matrix * offsetParentMatrix。"""
        return om.MMatrix(cmds.getAttr(self.joint + ".matrix")) * om.MMatrix(
            cmds.getAttr(self.joint + ".offsetParentMatrix")
        )

    def assertMatrix(self, actual, expected, places=3):
        """行列を誤差付きで比較する。"""
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, places=places)

    def bend(self, degrees, direction):
        """YZ平面内の向きdirection(度、+Y=0・+Z=90)へdegreesだけ曲げる。"""
        heading = math.radians(direction)
        tip = om.MVector(0, math.cos(heading), math.sin(heading))
        bend_axis = om.MVector(1, 0, 0) ^ tip
        euler = om.MQuaternion(math.radians(degrees), bend_axis).asEulerRotation()
        cmds.setAttr(self.joint + ".rotate", *[math.degrees(v) for v in euler])

    def check(self, owner, rest, axis, limits, softness):
        """現在の姿勢でグラフの出力と期待値を比較する。"""
        expected, angle, limit, limited = _expected(rest, self.local(), axis, limits, softness)
        self.assertAlmostEqual(owner.getPlug("swingAngle").get(), angle, places=2)
        if angle > 0.5:
            self.assertAlmostEqual(owner.getPlug("limitAngle").get(), limit, places=2)
        self.assertAlmostEqual(owner.getPlug("limitedAngle").get(), limited, places=2)
        self.assertAlmostEqual(owner.getPlug("excessAngle").get(), angle - limited, places=2)
        self.assertMatrix(owner.getPlug("matrix").get(), expected)
        return limited

    def test_hard_limit_each_side(self):
        """softness=0で、+Y・-Y・+Z・-Zの各側にそれぞれの限界角で止まる。"""
        owner = AsymmetricSwingLimit.create(self.joint, softness=0).container
        rest = self.local()
        for direction, expected in ((0, 80), (180, 30), (90, 60), (270, 20)):
            for degrees in (10, 100):
                self.bend(degrees, direction)
                limited = self.check(owner, rest, "x", self.LIMITS, 0)
                self.assertAlmostEqual(limited, min(degrees, expected), places=2)

    def test_quadrant_continuity_and_soft(self):
        """向きを一周回しても限界角が連続し、柔らかい区間は単調で限界を超えない。"""
        owner = AsymmetricSwingLimit.create(self.joint, softness=0.3).container
        rest = self.local()
        previous_limit = None
        for direction in range(0, 361, 5):
            self.bend(150, direction)
            self.check(owner, rest, "x", self.LIMITS, 0.3)
            limit = owner.getPlug("limitAngle").get()
            self.assertGreaterEqual(limit, min(self.LIMITS) - 1e-3)
            self.assertLessEqual(limit, max(self.LIMITS) + 1e-3)
            if previous_limit is not None:
                # 5度ごとの変化が、最大と最小の差の1/4を超えて跳ばない。
                self.assertLess(abs(limit - previous_limit), (max(self.LIMITS) - min(self.LIMITS)) / 4)
            previous_limit = limit
        previous = -1.0
        for degrees in range(0, 171, 10):
            self.bend(degrees, 135)
            limited = self.check(owner, rest, "x", self.LIMITS, 0.3)
            self.assertGreaterEqual(limited, previous - 1e-4)
            self.assertLessEqual(limited, owner.getPlug("limitAngle").get() + 1e-4)
            previous = limited

    def test_symmetric_matches_swing_limit(self):
        """+側と-側が同じなら、SwingLimitと同じ行列になる。"""
        sym = SwingLimit.create(self.joint, name="sym", limit1=50, limit2=25, softness=0.25).container
        asym = AsymmetricSwingLimit.create(self.joint, name="asym", limit1Positive=50, limit1Negative=50,
                                           limit2Positive=25, limit2Negative=25, softness=0.25).container
        for rotation in ((10, 40, -70), (-30, -80, 20), (0, 0, 120)):
            cmds.setAttr(self.joint + ".rotate", *rotation)
            self.assertMatrix(asym.getPlug("matrix").get(), sym.getPlug("matrix").get())
            self.assertAlmostEqual(asym.getPlug("excessAngle").get(), sym.getPlug("excessAngle").get(), places=3)

    def test_twist_rest_pose_axes_and_live_attributes(self):
        """jointOrient/OPM付きの基準姿勢、Twist保持、y/z軸、生成後の値の変更に追従する。"""
        cmds.setAttr(self.joint + ".jointOrient", 10, 20, 30)
        cmds.setAttr(self.joint + ".translate", 5, 2, -1)
        opm = om.MEulerRotation(0.1, -0.2, 0.3).asMatrix()
        cmds.setAttr(self.joint + ".offsetParentMatrix", *opm, type="matrix")
        owner = AsymmetricSwingLimit.create(self.joint).container
        rest = self.local()
        self.assertMatrix(owner.getPlug("matrix").get(), rest)
        for rotation in ((45, 30, -20), (-70, 10, 65), (20, -80, 5)):
            cmds.setAttr(self.joint + ".rotate", *rotation)
            self.check(owner, rest, "x", self.LIMITS, 0.2)
        cmds.setAttr(self.joint + ".rotate", 75, 0, 0)
        self.assertAlmostEqual(owner.getPlug("swingAngle").get(), 0, places=3)
        self.assertMatrix(owner.getPlug("matrix").get(), self.local())
        cmds.delete(owner.getFullName())
        for axis, rotation in (("y", (40, 0, 50)), ("z", (-35, 60, 0))):
            cmds.setAttr(self.joint + ".rotate", 0, 0, 0)
            owner = AsymmetricSwingLimit.create(self.joint, name="limit" + axis, axis=axis).container
            rest = self.local()
            cmds.setAttr(self.joint + ".rotate", *rotation)
            self.check(owner, rest, axis, self.LIMITS, 0.2)
            changed = (25, 45, 15, 35)
            for attr, value in zip(AsymmetricSwingLimit.LIMIT_ATTRIBUTES, changed):
                owner.getPlug(attr).set(value)
            owner.getPlug("softness").set(0.6)
            self.check(owner, rest, axis, changed, 0.6)
            cmds.delete(owner.getFullName())

    def test_invalid_and_undo(self):
        """範囲外の引数を拒否し、生成を1回のUndoで戻せる。"""
        for kwargs in ({"axis": "w"}, {"limit1Positive": 0}, {"limit1Negative": 180},
                       {"limit2Positive": float("nan")}, {"limit2Negative": -5},
                       {"softness": -0.1}, {"softness": 1.5}):
            with self.assertRaises(ValueError):
                AsymmetricSwingLimit.create(self.joint, **kwargs)
        self.assertFalse(cmds.objExists("asymmetricSwingLimit"))
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        AsymmetricSwingLimit.create(self.joint)
        self.assertTrue(cmds.objExists("asymmetricSwingLimit"))
        cmds.undo()
        self.assertFalse(cmds.objExists("asymmetricSwingLimit"))
        cmds.redo()
        self.assertTrue(cmds.objExists("asymmetricSwingLimit"))

    def test_python_helpers(self):
        """補助関数の象限選択と端の値を確認する。"""
        limits = self.LIMITS
        self.assertEqual(AsymmetricSwingLimit.quadrantLimits(*limits, 1, 1), (80, 60))
        self.assertEqual(AsymmetricSwingLimit.quadrantLimits(*limits, -1, -1), (30, 20))
        self.assertAlmostEqual(AsymmetricSwingLimit.asymmetricLimitAngle(*limits, 1, 0), 80)
        self.assertAlmostEqual(AsymmetricSwingLimit.asymmetricLimitAngle(*limits, -1, 0), 30)
        self.assertAlmostEqual(AsymmetricSwingLimit.asymmetricLimitAngle(*limits, 0, 1), 60)
        self.assertAlmostEqual(AsymmetricSwingLimit.asymmetricLimitAngle(*limits, 0, -1), 20)
        self.assertAlmostEqual(AsymmetricSwingLimit.asymmetricLimitAngle(*limits, 0, 0), 20)
        # 軸のごく近くでは隣の象限と同じ値に近づく(連続)。
        near = AsymmetricSwingLimit.asymmetricLimitAngle(*limits, 1e-6, 1)
        self.assertAlmostEqual(near, AsymmetricSwingLimit.asymmetricLimitAngle(*limits, -1e-6, 1), places=4)


if __name__ == "__main__":
    unittest.main()
