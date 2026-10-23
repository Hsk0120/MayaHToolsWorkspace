"""楕円コーンのSwing制限を、Quaternionで求めた期待値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import SwingLimit


def _rotation(matrix):
    """行列の回転をQuaternionで返す。"""
    return om.MTransformationMatrix(om.MMatrix(matrix)).rotation(asQuaternion=True)


def _expected(rest, current, axis, limit1, limit2, softness):
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
    limit = SwingLimit.limitAngle(limit1, limit2, tip["xyz".index(first)], tip["xyz".index(second)])
    limited = SwingLimit.softAngle(angle, limit, softness)
    ratio = limited / angle if angle > 1e-4 else 1.0
    result = twist * om.MQuaternion.slerp(om.MQuaternion(), swing, ratio) * rest_rotation
    matrix = om.MTransformationMatrix(result.asMatrix())
    matrix.setTranslation(
        om.MTransformationMatrix(om.MMatrix(current)).translation(om.MSpace.kTransform), om.MSpace.kTransform
    )
    return matrix.asMatrix(), angle, limit, limited


class SwingLimitTest(unittest.TestCase):
    """標準ノードの数値評価・境界・Twist保持・引数検査を確認する。"""

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

    def check(self, owner, rest, axis, limit1, limit2, softness):
        """現在の姿勢でグラフの出力と期待値を比較する。"""
        expected, angle, limit, limited = _expected(rest, self.local(), axis, limit1, limit2, softness)
        self.assertAlmostEqual(owner.getPlug("swingAngle").get(), angle, places=2)
        if angle > 0.5:
            self.assertAlmostEqual(owner.getPlug("limitAngle").get(), limit, places=2)
        self.assertAlmostEqual(owner.getPlug("limitedAngle").get(), limited, places=2)
        self.assertMatrix(owner.getPlug("matrix").get(), expected)
        return limited

    def test_hard_limit_axes(self):
        """softness=0で、各直交軸の側にそれぞれの限界角で止まる。"""
        owner = SwingLimit.create(self.joint, limit1=60, limit2=30, softness=0).container
        rest = self.local()
        # Z回転で+X先端は+Y側へ、Y回転の負で+Z側へ曲がる。
        for rotation, expected in (((0, 0, 50), 50), ((0, 0, 80), 60), ((0, 0, -120), 60),
                                   ((0, -20, 0), 20), ((0, -70, 0), 30), ((0, 100, 0), 30)):
            cmds.setAttr(self.joint + ".rotate", *rotation)
            limited = self.check(owner, rest, "x", 60, 30, 0)
            self.assertAlmostEqual(limited, expected, places=2)

    def test_ellipse_and_soft(self):
        """斜め方向の楕円の限界角と、柔らかい区間の連続・単調・非超過を確認する。"""
        owner = SwingLimit.create(self.joint, limit1=70, limit2=25, softness=0.3).container
        rest = self.local()
        previous = -1.0
        # 曲げる向きを固定するため、YZ平面内の一定の軸まわりに回す。
        bend_axis = om.MVector(0, -0.6, 0.8)
        for bend in range(0, 171, 10):
            euler = om.MQuaternion(math.radians(bend), bend_axis).asEulerRotation()
            cmds.setAttr(self.joint + ".rotate", *[math.degrees(v) for v in euler])
            limited = self.check(owner, rest, "x", 70, 25, 0.3)
            self.assertGreaterEqual(limited, previous - 1e-4)
            self.assertLessEqual(limited, owner.getPlug("limitAngle").get() + 1e-4)
            previous = limited
        cmds.setAttr(self.joint + ".rotate", 0, 0, 30)
        # softness=0.3, L=70 なら start=49度。30度は入力のまま。
        self.assertAlmostEqual(owner.getPlug("ratio").get(), 1, places=4)

    def test_twist_kept_and_rest_pose(self):
        """Twistを保持し、jointOrient/OPM/移動を含む基準姿勢から測る。"""
        cmds.setAttr(self.joint + ".jointOrient", 10, 20, 30)
        cmds.setAttr(self.joint + ".translate", 5, 2, -1)
        opm = om.MEulerRotation(0.1, -0.2, 0.3).asMatrix()
        cmds.setAttr(self.joint + ".offsetParentMatrix", *opm, type="matrix")
        owner = SwingLimit.create(self.joint, limit1=40, limit2=20, softness=0.25).container
        rest = self.local()
        self.assertMatrix(owner.getPlug("matrix").get(), rest)
        self.assertMatrix(owner.getPlug("restMatrix").get(), rest)
        for rotation in ((45, 30, -20), (-70, 10, 65), (20, -80, 5)):
            cmds.setAttr(self.joint + ".rotate", *rotation)
            self.check(owner, rest, "x", 40, 20, 0.25)
        cmds.setAttr(self.joint + ".rotate", 0, 0, 0)
        cmds.setAttr(self.joint + ".rx", 75)
        # 純粋なTwistは制限しない。
        self.assertAlmostEqual(owner.getPlug("swingAngle").get(), 0, places=3)
        self.assertMatrix(owner.getPlug("matrix").get(), self.local())

    def test_other_axes_and_live_attributes(self):
        """y/z軸と、生成後のlimit・softnessの変更に追従する。"""
        for axis, rotation in (("y", (40, 0, 50)), ("z", (-35, 60, 0))):
            cmds.setAttr(self.joint + ".rotate", 0, 0, 0)
            owner = SwingLimit.create(self.joint, name="limit" + axis, axis=axis).container
            rest = self.local()
            cmds.setAttr(self.joint + ".rotate", *rotation)
            self.check(owner, rest, axis, 60, 30, 0.2)
            owner.getPlug("limit1").set(25)
            owner.getPlug("limit2").set(45)
            owner.getPlug("softness").set(0.6)
            self.check(owner, rest, axis, 25, 45, 0.6)
            cmds.delete(owner.getFullName())

    def test_invalid_and_undo(self):
        """範囲外の引数を拒否し、生成を1回のUndoで戻せる。"""
        for kwargs in ({"axis": "w"}, {"limit1": 0}, {"limit2": 180}, {"limit1": float("nan")},
                       {"softness": -0.1}, {"softness": 1.5}):
            with self.assertRaises(ValueError):
                SwingLimit.create(self.joint, **kwargs)
        self.assertFalse(cmds.objExists("swingLimit"))
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        SwingLimit.create(self.joint)
        self.assertTrue(cmds.objExists("swingLimit"))
        cmds.undo()
        self.assertFalse(cmds.objExists("swingLimit"))
        cmds.redo()
        self.assertTrue(cmds.objExists("swingLimit"))

    def test_python_helpers(self):
        """補助関数の端の値を確認する。"""
        self.assertEqual(SwingLimit.perpendicularAxes("x"), ("y", "z"))
        self.assertEqual(SwingLimit.perpendicularAxes("y"), ("z", "x"))
        self.assertEqual(SwingLimit.perpendicularAxes("z"), ("x", "y"))
        self.assertAlmostEqual(SwingLimit.limitAngle(60, 30, 1, 0), 60)
        self.assertAlmostEqual(SwingLimit.limitAngle(60, 30, 0, -1), 30)
        self.assertAlmostEqual(SwingLimit.limitAngle(60, 30, 0, 0), 30)
        self.assertAlmostEqual(SwingLimit.softAngle(500, 60, 0.2), 60, places=6)
        self.assertAlmostEqual(SwingLimit.softAngle(80, 60, 0), 60, places=6)
        self.assertAlmostEqual(SwingLimit.softAngle(10, 60, 0.2), 10)


if __name__ == "__main__":
    unittest.main()
