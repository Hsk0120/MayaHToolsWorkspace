"""AckermannSteeringの左右の前輪の角度を、旋回中心(後輪の軸の延長上の1点)の幾何と独立計算で確かめる。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om2

from mlrig.setups import AckermannSteering

WHEEL_BASE = 26.0
TRACK = 15.0


def _exact(steer, wheelBase=WHEEL_BASE, track=TRACK):
    """旋回半径から求めた左右の角度(試験側の独立計算。R = L/tanδ、内輪 atan(L/(R-T/2))、外輪 atan(L/(R+T/2)))。"""
    if abs(steer) < 1e-12:
        return 0.0, 0.0
    radius = wheelBase / math.tan(math.radians(steer))
    left = math.degrees(math.atan2(wheelBase, radius - track * 0.5))
    right = math.degrees(math.atan2(wheelBase, radius + track * 0.5))
    if steer < 0:
        # 右へ曲がる場合、旋回中心は -X 側(R<0)。atan2 の第1引数を正にした分を負の角度へ戻す。
        left, right = left - 180.0, right - 180.0
    return left, right


def _world(node):
    return om2.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _row(matrix, index):
    return om2.MVector(matrix.getElement(index, 0), matrix.getElement(index, 1), matrix.getElement(index, 2))


class AckermannSteeringTest(unittest.TestCase):
    """作成時に跳ねない・独立計算・旋回中心の一致・割合・driver・UI単位・所有とUndo・引数を確認する。"""

    def setUp(self):
        """回転・移動した車体(前+Z、左+X、上+Y)の下に、初期の回転を持つ左右の前輪を作る。"""
        self._build((2.0, -1.5))

    def _build(self, rest):
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.car = cmds.createNode("transform", name="car")
        cmds.setAttr(self.car + ".translate", 4, 1, -3)
        cmds.setAttr(self.car + ".rotate", 0, 35, 0)
        self.left = cmds.createNode("transform", name="frontLeft", parent=self.car)
        self.right = cmds.createNode("transform", name="frontRight", parent=self.car)
        cmds.setAttr(self.left + ".translate", TRACK * 0.5, 0.3, WHEEL_BASE)
        cmds.setAttr(self.right + ".translate", -TRACK * 0.5, 0.3, WHEEL_BASE)
        cmds.setAttr(self.left + ".rotateY", rest[0])
        cmds.setAttr(self.right + ".rotateY", rest[1])
        self.rest = tuple(rest)
        self.setup = AckermannSteering.create(self.left, self.right, WHEEL_BASE, name="steering")
        self.owner = str(self.setup.container)

    def _offsets(self):
        return (cmds.getAttr(self.left + ".rotateY") - self.rest[0],
                cmds.getAttr(self.right + ".rotateY") - self.rest[1])

    def test_rest(self):
        """作成直後は車輪の回転が作成前のまま(跳ねない)で、輪距は車輪の距離から測る。"""
        for offset in self._offsets():
            self.assertAlmostEqual(offset, 0.0, delta=1e-9)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".trackWidth"), TRACK, delta=1e-9)

    def test_exact_angles(self):
        """左右の角度が旋回半径からの独立計算とPython版に一致し、内輪が外輪より大きく切れる。"""
        for steer in (5.0, 20.0, 37.5, 60.0, -12.0, -45.0, 0.0):
            with self.subTest(steer=steer):
                cmds.setAttr(self.owner + ".steer", steer)
                left, right = self._offsets()
                expected = _exact(steer)
                self.assertAlmostEqual(left, expected[0], delta=1e-4)
                self.assertAlmostEqual(right, expected[1], delta=1e-4)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".leftAngle"), left, delta=1e-9)
                python = AckermannSteering.angles(steer, WHEEL_BASE, TRACK)
                self.assertAlmostEqual(python[0], expected[0], delta=1e-9)
                self.assertAlmostEqual(python[1], expected[1], delta=1e-9)
                if steer > 0:
                    self.assertGreater(left, steer)
                    self.assertLess(right, steer)
                elif steer < 0:
                    self.assertLess(right, steer)
                    self.assertGreater(left, steer)

    def test_turn_center(self):
        """初期の回転0の車輪で、両輪の車軸の延長が後輪の軸の延長上の同じ点(旋回中心)で交わる。"""
        self._build((0.0, 0.0))
        owner = self.owner
        car = _world(self.car)
        rear_origin = om2.MPoint(car.getElement(3, 0), car.getElement(3, 1), car.getElement(3, 2))
        rear_axis = _row(car, 0)
        for steer in (8.0, 25.0, 50.0, -30.0):
            with self.subTest(steer=steer):
                cmds.setAttr(owner + ".steer", steer)
                hits = []
                for wheel in (self.left, self.right):
                    matrix = _world(wheel)
                    point = om2.MPoint(matrix.getElement(3, 0), matrix.getElement(3, 1), matrix.getElement(3, 2))
                    axle = _row(matrix, 0)
                    # 車輪の車軸の直線 point + t*axle と、後輪の軸の直線 rear_origin + u*rear_axis の(水平面での)交点。
                    forward = _row(car, 2)
                    t = -(om2.MVector(point - rear_origin) * forward) / (axle * forward)
                    hits.append(point + axle * t)
                self.assertLess((hits[0] - hits[1]).length(), 1e-3)
                # 交点は後輪の軸の上で、曲がる側にある(R = L/tanδ)。
                distance = om2.MVector(hits[0] - rear_origin) * rear_axis
                self.assertAlmostEqual(distance, WHEEL_BASE / math.tan(math.radians(steer)), delta=1e-3)

    def test_ackermann_ratio_and_attributes(self):
        """ackermann=0で両輪が中央の切れ角と同じ、途中は線形に混ざり、軸距・輪距の変更がすぐに反映される。"""
        cmds.setAttr(self.owner + ".steer", 30)
        exact = _exact(30.0)
        for ratio in (0.0, 0.25, 1.0):
            with self.subTest(ratio=ratio):
                cmds.setAttr(self.owner + ".ackermann", ratio)
                left, right = self._offsets()
                self.assertAlmostEqual(left, 30 + ratio * (exact[0] - 30), delta=1e-4)
                self.assertAlmostEqual(right, 30 + ratio * (exact[1] - 30), delta=1e-4)
        cmds.setAttr(self.owner + ".ackermann", 1)
        cmds.setAttr(self.owner + ".wheelBase", 40)
        cmds.setAttr(self.owner + ".trackWidth", 10)
        left, right = self._offsets()
        expected = _exact(30.0, 40.0, 10.0)
        self.assertAlmostEqual(left, expected[0], delta=1e-4)
        self.assertAlmostEqual(right, expected[1], delta=1e-4)

    def test_driver_axis_and_without_connect(self):
        """ハンドルの回転を比で切れ角へ変え、axis=zとconnect=Falseでは出力だけを持つ。"""
        cmds.file(new=True, force=True)
        wheel = cmds.createNode("transform", name="handle")
        cmds.setAttr(wheel + ".rotateZ", 10)
        left = cmds.createNode("transform", name="l")
        right = cmds.createNode("transform", name="r")
        cmds.setAttr(right + ".translateX", 3)
        setup = AckermannSteering.create(left, right, 6.0, name="wheel", axis="z", driver=wheel + ".rotateZ",
                                         driverRatio=0.25, connect=False)
        owner = str(setup.container)
        self.assertAlmostEqual(cmds.getAttr(owner + ".trackWidth"), 3.0, delta=1e-9)
        self.assertEqual(cmds.getAttr(owner + ".steer"), 0.0)
        cmds.setAttr(wheel + ".rotateZ", 10 + 120)
        self.assertAlmostEqual(cmds.getAttr(owner + ".steer"), 30.0, delta=1e-6)
        expected = _exact(30.0, 6.0, 3.0)
        self.assertAlmostEqual(cmds.getAttr(owner + ".leftAngle"), expected[0], delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(owner + ".rightAngle"), expected[1], delta=1e-4)
        self.assertEqual(cmds.getAttr(left + ".rotateZ"), 0.0)
        self.assertIsNone(cmds.listConnections(left + ".rotateZ", source=True, destination=False))

    def test_ui_units(self):
        """UI単位がラジアン・mmでも(距離の引数・測った輪距はcm)同じ角度になり、自動の単位変換が入らない(明示した係数1の変換のみ)。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="rad", linear="mm")
        left = cmds.createNode("transform", name="l")
        right = cmds.createNode("transform", name="r")
        cmds.setAttr(right + ".translateX", -150)
        setup = AckermannSteering.create(left, right, 26.0, name="units")  # 距離の引数はcm
        owner = str(setup.container)
        cmds.setAttr(owner + ".steer", math.radians(20))
        # 明示した係数1の変換(angleBetween の vector2 が長さの型の版の対策)以外の単位変換が入らない。
        conversions = cmds.ls(type="unitConversion")
        owned = cmds.container(owner, query=True, nodeList=True) or []
        self.assertEqual(sorted(set(conversions) - set(owned)), [])
        for node in conversions:
            self.assertAlmostEqual(cmds.getAttr(node + ".conversionFactor"), 1.0)
        cmds.currentUnit(angle="deg", linear="cm")
        expected = _exact(20.0, 26.0, 15.0)
        self.assertAlmostEqual(cmds.getAttr(left + ".rotateY"), expected[0], delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(right + ".rotateY"), expected[1], delta=1e-4)

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消えて接続も戻り、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = cmds.listHistory(self.left + ".rotateY") or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        left = cmds.createNode("transform", name="undoLeft")
        right = cmds.createNode("transform", name="undoRight")
        cmds.setAttr(right + ".translateX", 2)
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        AckermannSteering.create(left, right, 4.0, name="undoSteering")
        self.assertTrue(cmds.objExists("undoSteering"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoSteering"))
        self.assertEqual(set(cmds.ls()), before)
        self.assertIsNone(cmds.listConnections(left + ".rotateY", source=True, destination=False))
        cmds.redo()
        self.assertTrue(cmds.objExists("undoSteering.leftAngle"))

    def test_arguments(self):
        """軸・距離・割合・transform以外・同じ車輪・同じ位置・角度でないdriver・接続済み・名前の重複を拒否する。"""
        free = [cmds.createNode("transform", name="freeLeft"), cmds.createNode("transform", name="freeRight")]
        cmds.setAttr(free[1] + ".translateX", 2)
        cases = (
            ((free[0], free[1], 4.0), {"axis": "w"}),
            ((free[0], free[1], 0.0), {}),
            ((free[0], free[1], 4.0), {"trackWidth": -1.0}),
            ((free[0], free[1], float("nan")), {}),
            ((free[0], free[1], 4.0), {"ackermann": 1.5}),
            ((free[0], free[0], 4.0), {}),
            ((free[0], cmds.createNode("transform", name="samePlace"), 4.0), {}),
            ((cmds.createNode("multiplyDivide"), free[1], 4.0), {}),
            ((free[0], free[1], 4.0), {"driver": self.car + ".translateX"}),
            ((self.left, free[1], 4.0), {}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                AckermannSteering.create(*args, name="bad", **kwargs)
        with self.assertRaises(ValueError):
            AckermannSteering.create(free[0], free[1], 4.0, name="steering")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
