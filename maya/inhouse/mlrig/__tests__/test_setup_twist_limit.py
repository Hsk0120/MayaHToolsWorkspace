"""非対称なTwist制限を、Quaternionで求めた期待値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import TwistLimit


def _rotation(matrix):
    """行列の回転をQuaternionで返す。"""
    return om.MTransformationMatrix(om.MMatrix(matrix)).rotation(asQuaternion=True)


def _expected(rest, current, axis, minimum, maximum, softness):
    """生成時の姿勢restと現在の姿勢currentから期待値を計算する。

    Returns:
        tuple: (期待する親空間の行列, Twist角, 制限後のTwist角)。
    """
    rest_rotation = _rotation(rest)
    delta = _rotation(current) * rest_rotation.inverse()
    index = "xyz".index(axis)
    components = [delta.x, delta.y, delta.z]
    twist = om.MQuaternion(*[v if i == index else 0 for i, v in enumerate(components)], delta.w)
    length = math.sqrt(components[index] ** 2 + delta.w ** 2)
    twist = twist.normalizeIt() if length > 1e-9 else om.MQuaternion()
    swing = twist.inverse() * delta
    angle = math.degrees(2 * math.atan2(components[index], delta.w))
    angle = (angle + 180) % 360 - 180
    limited = TwistLimit.softTwist(angle, minimum, maximum, softness)
    unit = om.MVector(*[float(i == index) for i in range(3)])
    result = om.MQuaternion(math.radians(limited), unit) * swing * rest_rotation
    matrix = om.MTransformationMatrix(result.asMatrix())
    matrix.setTranslation(
        om.MTransformationMatrix(om.MMatrix(current)).translation(om.MSpace.kTransform), om.MSpace.kTransform
    )
    return matrix.asMatrix(), angle, limited


class TwistLimitTest(unittest.TestCase):
    """標準ノードの数値評価・境界・Swing保持・引数検査を確認する。"""

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

    def check(self, owner, rest, axis, minimum, maximum, softness):
        """現在の姿勢でグラフの出力と期待値を比較する。"""
        expected, angle, limited = _expected(rest, self.local(), axis, minimum, maximum, softness)
        self.assertAlmostEqual(owner.getPlug("twist").get(), angle, places=2)
        self.assertAlmostEqual(owner.getPlug("limitedTwist").get(), limited, places=2)
        self.assertAlmostEqual(owner.getPlug("excessTwist").get(), angle - limited, places=2)
        self.assertMatrix(owner.getPlug("matrix").get(), expected)
        return limited

    def test_hard_asymmetric(self):
        """softness=0で、+側と-側がそれぞれの限界角で止まる。"""
        owner = TwistLimit.create(self.joint, minimum=-30, maximum=60, softness=0).container
        rest = self.local()
        for twist, expected in ((20, 20), (59, 59), (90, 60), (170, 60), (-10, -10), (-50, -30), (-170, -30)):
            cmds.setAttr(self.joint + ".rotate", twist, 0, 0)
            limited = self.check(owner, rest, "x", -30, 60, 0)
            self.assertAlmostEqual(limited, expected, places=2)

    def test_soft_monotonic(self):
        """柔らかい区間で連続・単調・非超過、内側の値は入力のまま。"""
        owner = TwistLimit.create(self.joint, minimum=-40, maximum=80, softness=0.5).container
        rest = self.local()
        previous = -1000.0
        for twist in range(-175, 176, 5):
            cmds.setAttr(self.joint + ".rotate", twist, 0, 0)
            limited = self.check(owner, rest, "x", -40, 80, 0.5)
            self.assertGreaterEqual(limited, previous - 1e-4)
            self.assertLessEqual(limited, 80 + 1e-4)
            self.assertGreaterEqual(limited, -40 - 1e-4)
            previous = limited
        # w=0.5*120/2=30、上側の開始角50度、下側の開始角-10度。0度は入力のまま。
        cmds.setAttr(self.joint + ".rotate", 0, 0, 0)
        self.assertAlmostEqual(owner.getPlug("limitedTwist").get(), 0, places=4)
        self.assertAlmostEqual(owner.getPlug("excessTwist").get(), 0, places=4)

    def test_swing_kept_and_rest_pose(self):
        """Swingを保持し、jointOrient/OPM/移動を含む基準姿勢から測る。"""
        cmds.setAttr(self.joint + ".jointOrient", 10, 20, 30)
        cmds.setAttr(self.joint + ".translate", 5, 2, -1)
        opm = om.MEulerRotation(0.1, -0.2, 0.3).asMatrix()
        cmds.setAttr(self.joint + ".offsetParentMatrix", *opm, type="matrix")
        owner = TwistLimit.create(self.joint, minimum=-20, maximum=35, softness=0.25).container
        rest = self.local()
        self.assertMatrix(owner.getPlug("matrix").get(), rest)
        self.assertMatrix(owner.getPlug("restMatrix").get(), rest)
        for rotation in ((95, 30, -20), (-70, 10, 65), (20, -80, 5)):
            cmds.setAttr(self.joint + ".rotate", *rotation)
            self.check(owner, rest, "x", -20, 35, 0.25)
        # 純粋なSwingはTwistが0なので制限しない。
        cmds.setAttr(self.joint + ".rotate", 0, 0, 0)
        cmds.setAttr(self.joint + ".rz", 70)
        self.assertAlmostEqual(owner.getPlug("twist").get(), 0, places=3)
        self.assertMatrix(owner.getPlug("matrix").get(), self.local())

    def test_other_axes_and_live_attributes(self):
        """y/z軸と、生成後のminimum・maximum・softnessの変更に追従する。"""
        for axis, rotation in (("y", (20, 100, 15)), ("z", (-25, 10, -120))):
            cmds.setAttr(self.joint + ".rotate", 0, 0, 0)
            owner = TwistLimit.create(self.joint, name="limit" + axis, axis=axis).container
            rest = self.local()
            cmds.setAttr(self.joint + ".rotate", *rotation)
            self.check(owner, rest, axis, -45, 45, 0.2)
            owner.getPlug("minimum").set(-90)
            owner.getPlug("maximum").set(10)
            owner.getPlug("softness").set(0.7)
            self.check(owner, rest, axis, -90, 10, 0.7)
            cmds.delete(owner.getFullName())

    def test_invalid_and_undo(self):
        """範囲外の引数を拒否し、生成を1回のUndoで戻せる。"""
        for kwargs in ({"axis": "w"}, {"minimum": 10, "maximum": 10}, {"minimum": 20, "maximum": 10},
                       {"minimum": -180}, {"maximum": 180}, {"maximum": float("nan")},
                       {"softness": -0.1}, {"softness": 1.5}):
            with self.assertRaises(ValueError):
                TwistLimit.create(self.joint, **kwargs)
        self.assertFalse(cmds.objExists("twistLimit"))
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        TwistLimit.create(self.joint)
        self.assertTrue(cmds.objExists("twistLimit"))
        cmds.undo()
        self.assertFalse(cmds.objExists("twistLimit"))
        cmds.redo()
        self.assertTrue(cmds.objExists("twistLimit"))

    def test_python_helpers(self):
        """補助関数の端の値を確認する。"""
        self.assertAlmostEqual(TwistLimit.softWidth(-30, 60, 0.2), 9)
        self.assertAlmostEqual(TwistLimit.softWidth(-30, 60, 0), TwistLimit.MINIMUM_SOFT_WIDTH)
        self.assertAlmostEqual(TwistLimit.softTwist(500, -30, 60, 0.2), 60, places=6)
        self.assertAlmostEqual(TwistLimit.softTwist(-500, -30, 60, 0.2), -30, places=6)
        self.assertAlmostEqual(TwistLimit.softTwist(80, -30, 60, 0), 60, places=6)
        self.assertAlmostEqual(TwistLimit.softTwist(10, -30, 60, 0.2), 10)


if __name__ == "__main__":
    unittest.main()
