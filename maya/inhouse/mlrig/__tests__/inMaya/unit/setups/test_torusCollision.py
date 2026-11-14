"""TorusCollisionの押し出しを、OpenMayaで独立に求めた芯の円上の最近点・管の半径・柔らかい押し出しの式と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import TorusCollision

MAJOR_RADIUS = 4.0
MINOR_RADIUS = 1.2
SOFTNESS = 1.0


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _position(matrix):
    """行列の平行移動をMPointで返す。"""
    return om.MPoint(matrix[12], matrix[13], matrix[14])


def _frame(torus):
    """輪の中心・局所X・局所Y(軸)・局所Zのワールドの向き(長さ1)を返す。"""
    matrix = _matrix(torus + ".worldMatrix[0]")
    x = om.MVector(matrix[0], matrix[1], matrix[2]).normal()
    n = om.MVector(matrix[4], matrix[5], matrix[6]).normal()
    z = om.MVector(matrix[8], matrix[9], matrix[10]).normal()
    return _position(matrix), x, n, z


def _expected(target, torus, majorRadius, minorRadius, softness):
    """OpenMayaで、期待する出力の行列・距離・押し出し量・押し込んだ深さ・高さ・軸からの距離を求める。"""
    c, x, n, _z = _frame(torus)
    source = _matrix(target + ".worldMatrix[0]")
    p = _position(source)
    v = p - c
    height = v * n
    planar = v - n * height
    axisDistance = planar.length()
    ring = planar.normal() if axisDistance > 1e-6 else x
    closest = c + ring * majorRadius
    offset = p - closest
    length = offset.length()
    distance = length - minorRadius
    if softness <= 1e-4:
        pushed = max(distance, 0.0)
    elif distance >= softness:
        pushed = distance
    else:
        pushed = softness * math.exp((distance - softness) / softness)
    push = pushed - distance if length > 1e-6 else 0.0
    direction = offset / length if length > 1e-6 else om.MVector()
    move = om.MMatrix()
    move[12], move[13], move[14] = direction.x * push, direction.y * push, direction.z * push
    return source * move, distance, push, max(-distance, 0.0), height, axisDistance


class TorusCollisionTest(unittest.TestCase):
    """作成時の姿勢・管の周り・穴と軸上・硬い押し出し・輪の動き・半径0・Python版・所有・Undo・引数を確認する。"""

    def setUp(self):
        """傾けた輪(回転・不均一なscaleあり)と、回転した対象を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.torus = cmds.createNode("transform", name="ring")
        cmds.setAttr(self.torus + ".translate", 1, 8, -2)
        cmds.setAttr(self.torus + ".rotate", 25, -35, 50)
        cmds.setAttr(self.torus + ".scale", 2, 0.5, 3)
        self.target = cmds.createNode("transform", name="handCtrl")
        cmds.setAttr(self.target + ".translate", 12, 3, 4)
        cmds.setAttr(self.target + ".rotate", 20, 40, -30)
        self.setup = TorusCollision.create(self.target, self.torus, name="collide", majorRadius=MAJOR_RADIUS,
                                           minorRadius=MINOR_RADIUS, softness=SOFTNESS)
        self.owner = str(self.setup.container)

    def _assertMatrix(self, actual, expected, tolerance=1e-4):
        for index, (a, b) in enumerate(zip(actual, expected)):
            self.assertAlmostEqual(a, b, delta=tolerance, msg="element {}".format(index))

    def _assertExpected(self, majorRadius=MAJOR_RADIUS, minorRadius=MINOR_RADIUS, softness=SOFTNESS):
        matrix, distance, push, penetration, height, axisDistance = _expected(
            self.target, self.torus, majorRadius, minorRadius, softness)
        self._assertMatrix(_matrix(self.owner + ".matrix"), matrix)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".distance"), distance, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".push"), push, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".penetration"), penetration, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".height"), height, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".axisDistance"), axisDistance, delta=1e-4)
        return distance, push

    def _surfaceDistance(self, plug, majorRadius=MAJOR_RADIUS, minorRadius=MINOR_RADIUS):
        """plugの行列の位置の、トーラスの表面からの符号付き距離(軸上でも厳密な式)。"""
        c, _x, n, _z = _frame(self.torus)
        v = _position(_matrix(plug)) - c
        height = v * n
        planar = (v - n * height).length()
        return math.hypot(planar - majorRadius, height) - minorRadius

    def _place(self, angle, axisDistance, height):
        """対象を輪の局所の円柱座標(局所Xから局所Zへの角度・軸からの距離・輪の平面からの高さ)へ置く。"""
        c, x, n, z = _frame(self.torus)
        radians = math.radians(angle)
        point = c + (x * math.cos(radians) + z * math.sin(radians)) * axisDistance + n * height
        cmds.setAttr(self.target + ".translate", point.x, point.y, point.z)

    def test_rest(self):
        """作成直後は表面から十分離れているので押し出さず、出力が入力のワールド行列と一致する(跳ねない)。"""
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".push"), 0.0, delta=1e-6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".penetration"), 0.0, delta=1e-6)
        self._assertMatrix(_matrix(self.owner + ".matrix"), _matrix(self.target + ".worldMatrix[0]"), 1e-6)

    def test_around_the_tube(self):
        """管の周りのいろいろな位置で帯の外・帯の中・管の中・芯の近くまで入れ、式と一致し、管の中へ入らない。"""
        for angle in (0.0, 70.0, 180.0, 290.0):
            for tubeAngle in (0.0, 60.0, 135.0, 180.0, 250.0):
                for tubeDistance in (4.0, 2.0, 1.0, 0.3, 0.02):
                    with self.subTest(angle=angle, tubeAngle=tubeAngle, tubeDistance=tubeDistance):
                        radians = math.radians(tubeAngle)
                        self._place(angle, MAJOR_RADIUS + tubeDistance * math.cos(radians),
                                    tubeDistance * math.sin(radians))
                        distance, push = self._assertExpected()
                        self.assertAlmostEqual(distance, tubeDistance - MINOR_RADIUS, delta=1e-4)
                        self.assertGreater(self._surfaceDistance(self.owner + ".matrix"), -1e-4)
                        if tubeDistance >= MINOR_RADIUS + SOFTNESS:
                            self.assertAlmostEqual(push, 0.0, delta=1e-6)
                        else:
                            self.assertGreater(push, 0.0)

    def test_hole_and_axis(self):
        """穴の中・軸上でも距離は芯の円からの厳密な値で連続し、軸上では局所Xの向きの点から押し出す。"""
        cmds.setAttr(self.owner + ".majorRadius", 1.5)
        for axisDistance in (0.0, 1e-8, 0.4):
            for height in (0.0, 0.5, -1.0, 3.0):
                with self.subTest(axisDistance=axisDistance, height=height):
                    self._place(30.0, axisDistance, height)
                    distance, _push = self._assertExpected(majorRadius=1.5)
                    self.assertAlmostEqual(distance, math.hypot(axisDistance - 1.5, height) - MINOR_RADIUS,
                                           delta=1e-4)
                    self.assertGreater(self._surfaceDistance(self.owner + ".matrix", majorRadius=1.5), -1e-4)
        self._place(0.0, 0.0, 0.0)
        c, x, _n, _z = _frame(self.torus)
        out = _position(_matrix(self.owner + ".matrix"))
        self.assertLess((out - c) * x, -1e-3)

    def test_hard_and_attributes(self):
        """softness=0なら表面で硬く止まり、半径・softnessを変えると式と一致する。"""
        cmds.setAttr(self.owner + ".softness", 0.0)
        for angle, tubeDistance in ((40.0, 3.0), (100.0, 0.8), (220.0, 0.1)):
            with self.subTest(angle=angle, tubeDistance=tubeDistance):
                self._place(angle, MAJOR_RADIUS - tubeDistance, 0.0)
                distance, _push = self._assertExpected(softness=0.0)
                self.assertAlmostEqual(self._surfaceDistance(self.owner + ".matrix"), max(distance, 0.0),
                                       delta=1e-4)
        cmds.setAttr(self.owner + ".softness", 2.0)
        cmds.setAttr(self.owner + ".majorRadius", 6.0)
        cmds.setAttr(self.owner + ".minorRadius", 2.0)
        for angle, axisDistance, height in ((10.0, 9.0, 0.0), (150.0, 6.0, 1.5), (300.0, 4.5, -0.5)):
            with self.subTest(angle=angle, axisDistance=axisDistance, height=height, softness=2.0):
                self._place(angle, axisDistance, height)
                self._assertExpected(majorRadius=6.0, minorRadius=2.0, softness=2.0)

    def test_torus_moves_and_rotation_kept(self):
        """輪を動かす・回すと押し出しが付いてきて、出力の回転とscaleは入力のまま、輪のscaleは半径に影響しない。"""
        self._place(45.0, MAJOR_RADIUS + 0.5, 0.3)
        cmds.setAttr(self.torus + ".translate", -3, 2, 5)
        cmds.setAttr(self.torus + ".rotate", -60, 15, 80)
        cmds.setAttr(self.torus + ".scale", 4, 4, 0.2)
        distance, _push = self._assertExpected()
        self.assertGreater(self._surfaceDistance(self.owner + ".matrix"), -1e-4)
        self._place(200.0, MAJOR_RADIUS, 0.6)
        distance, push = self._assertExpected()
        self.assertAlmostEqual(distance, 0.6 - MINOR_RADIUS, delta=1e-4)
        self.assertGreater(push, 0.0)
        out = _matrix(self.owner + ".matrix")
        source = _matrix(self.target + ".worldMatrix[0]")
        for index in range(12):
            self.assertAlmostEqual(out[index], source[index], delta=1e-6)

    def test_zero_major_radius(self):
        """芯の円の半径が0なら、輪の中心を中心とする球と同じ押し出しになる。"""
        cmds.setAttr(self.owner + ".majorRadius", 0.0)
        c, _x, _n, _z = _frame(self.torus)
        for direction, length in (((1, 0, 0), 0.5), ((0, 1, 1), 1.5), ((-1, 2, 3), 5.0)):
            with self.subTest(direction=direction, length=length):
                point = c + om.MVector(*direction).normal() * length
                cmds.setAttr(self.target + ".translate", point.x, point.y, point.z)
                distance, _push = self._assertExpected(majorRadius=0.0)
                self.assertAlmostEqual(distance, length - MINOR_RADIUS, delta=1e-4)

    def test_python_matches(self):
        """Python版 pushedPosition・closestRingPoint が出力と一致する(軸上は局所Xを fallback に渡す)。"""
        c, x, n, _z = _frame(self.torus)
        center, axis, fallback = (c.x, c.y, c.z), (n.x * 3, n.y * 3, n.z * 3), (x.x, x.y, x.z)
        for angle, axisDistance, height in ((20.0, 4.3, 0.4), (250.0, 0.0, 0.7), (130.0, 9.0, 0.0),
                                            (90.0, 3.5, -0.9)):
            with self.subTest(angle=angle, axisDistance=axisDistance, height=height):
                self._place(angle, axisDistance, height)
                p = _position(_matrix(self.target + ".worldMatrix[0]"))
                point = (p.x, p.y, p.z)
                result = TorusCollision.pushedPosition(point, center, axis, MAJOR_RADIUS, MINOR_RADIUS, SOFTNESS,
                                                       fallback)
                out = _position(_matrix(self.owner + ".matrix"))
                for a, b in zip(result, (out.x, out.y, out.z)):
                    self.assertAlmostEqual(a, b, delta=1e-4)
                ring = TorusCollision.closestRingPoint(point, center, axis, MAJOR_RADIUS, fallback)
                self.assertAlmostEqual(math.sqrt(sum((a - b) ** 2 for a, b in zip(ring, center))), MAJOR_RADIUS,
                                       delta=1e-6)
        self.assertEqual(TorusCollision.pushedPosition((4, 0, 0), (0, 0, 0), (0, 1, 0), 4, 1, 1), (4.0, 0.0, 0.0))
        self.assertEqual(TorusCollision.closestRingPoint((0, 5, 0), (0, 0, 0), (0, 2, 0), 3), (3.0, 0.0, 0.0))
        self.assertEqual(TorusCollision.closestRingPoint((0, 0, 0), (0, 0, 0), (1, 0, 0), 2), (0.0, 0.0, 2.0))
        with self.assertRaises(ValueError):
            TorusCollision.closestRingPoint((1, 0, 0), (0, 0, 0), (0, 0, 0), 2)
        with self.assertRaises(ValueError):
            TorusCollision.closestRingPoint((0, 1, 0), (0, 0, 0), (0, 1, 0), 2, fallback=(0, 2, 0))

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = cmds.listHistory(self.owner + ".matrix", pruneDagObjects=True) or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        torus = cmds.createNode("transform", name="undoRing")
        target = cmds.createNode("transform", name="undoCtrl")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        TorusCollision.create(target, torus, name="undoCollide")
        self.assertTrue(cmds.objExists("undoCollide"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoCollide"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoCollide.axisDistance"))

    def test_arguments(self):
        """負の値・有限でない値・transform以外・同じノード・名前の重複を拒否する。"""
        for kwargs in ({"softness": -1.0}, {"majorRadius": -0.5}, {"minorRadius": -0.1},
                       {"majorRadius": float("nan")}, {"softness": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                TorusCollision.create(self.target, self.torus, name="bad", **kwargs)
        node = cmds.createNode("multiplyDivide")
        with self.assertRaises(ValueError):
            TorusCollision.create(node, self.torus, name="bad")
        with self.assertRaises(ValueError):
            TorusCollision.create(self.torus, self.torus, name="bad")
        with self.assertRaises(ValueError):
            TorusCollision.create(self.target, self.torus, name="collide")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
