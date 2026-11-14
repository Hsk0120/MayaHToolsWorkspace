"""CapsuleCollisionの押し出しを、OpenMayaで独立に求めた線分への最近点・先細りの半径・柔らかい押し出しの式と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import CapsuleCollision

START_RADIUS = 2.5
END_RADIUS = 1.5
SOFTNESS = 1.0


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _position(matrix):
    """行列の平行移動をMPointで返す。"""
    return om.MPoint(matrix[12], matrix[13], matrix[14])


def _expected(target, start, end, startRadius, endRadius, softness):
    """OpenMayaで、期待する出力の行列・距離・押し出し量・押し込んだ深さ・軸上の位置を求める。"""
    a = _position(_matrix(start + ".worldMatrix[0]"))
    b = _position(_matrix(end + ".worldMatrix[0]"))
    source = _matrix(target + ".worldMatrix[0]")
    p = _position(source)
    axis = b - a
    lengthSquared = axis * axis
    t = 0.0 if lengthSquared <= 1e-12 else min(max(((p - a) * axis) / lengthSquared, 0.0), 1.0)
    closest = a + axis * t
    offset = p - closest
    length = offset.length()
    distance = length - (startRadius + (endRadius - startRadius) * t)
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
    return source * move, distance, push, max(-distance, 0.0), t


class CapsuleCollisionTest(unittest.TestCase):
    """作成時の姿勢・側面と両端の半球・先細り・硬い押し出し・軸の動き・長さ0・軸上・Python版・所有・Undo・引数を確認する。"""

    def setUp(self):
        """傾けた軸の両端(回転・拡大あり)と、回転した対象を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.start = cmds.createNode("transform", name="hip")
        cmds.setAttr(self.start + ".translate", 1, 10, -1)
        cmds.setAttr(self.start + ".rotate", 15, -30, 40)
        cmds.setAttr(self.start + ".scale", 2, 0.5, 3)
        self.end = cmds.createNode("transform", name="knee")
        cmds.setAttr(self.end + ".translate", 2, 2, 1)
        self.target = cmds.createNode("transform", name="skirtCtrl")
        cmds.setAttr(self.target + ".translate", 9, 6, 0)
        cmds.setAttr(self.target + ".rotate", 20, 40, -30)
        self.setup = CapsuleCollision.create(self.target, self.start, self.end, name="collide",
                                             startRadius=START_RADIUS, endRadius=END_RADIUS, softness=SOFTNESS)
        self.owner = str(self.setup.container)

    def _assertMatrix(self, actual, expected, tolerance=1e-4):
        for index, (a, b) in enumerate(zip(actual, expected)):
            self.assertAlmostEqual(a, b, delta=tolerance, msg="element {}".format(index))

    def _assertExpected(self, startRadius=START_RADIUS, endRadius=END_RADIUS, softness=SOFTNESS):
        matrix, distance, push, penetration, t = _expected(self.target, self.start, self.end, startRadius,
                                                           endRadius, softness)
        self._assertMatrix(_matrix(self.owner + ".matrix"), matrix)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".distance"), distance, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".push"), push, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".penetration"), penetration, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".parameter"), t, delta=1e-5)
        return distance, push, t

    def _ends(self):
        return (_position(_matrix(self.start + ".worldMatrix[0]")),
                _position(_matrix(self.end + ".worldMatrix[0]")))

    def _surfaceDistance(self, plug, startRadius=START_RADIUS, endRadius=END_RADIUS):
        """plugの行列の位置の、カプセルの表面からの符号付き距離。"""
        a, b = self._ends()
        p = _position(_matrix(plug))
        t = CapsuleCollision.closestParameter((p.x, p.y, p.z), (a.x, a.y, a.z), (b.x, b.y, b.z))
        closest = a + (b - a) * t
        return (p - closest).length() - (startRadius + (endRadius - startRadius) * t)

    def _place(self, parameter, direction, length):
        """対象を軸上の位置 parameter(範囲外なら軸の延長上)から、direction の軸に垂直な成分の向きへ length の距離に置く。"""
        a, b = self._ends()
        axis = b - a
        origin = a + axis * parameter
        vector = om.MVector(*direction)
        unit = axis.normal()
        perpendicular = vector - unit * (vector * unit)
        if perpendicular.length() < 1e-9:
            perpendicular = vector
        point = origin + perpendicular.normal() * length
        cmds.setAttr(self.target + ".translate", point.x, point.y, point.z)

    def test_rest(self):
        """作成直後は表面から十分離れているので押し出さず、出力が入力のワールド行列と一致する(跳ねない)。"""
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".push"), 0.0, delta=1e-6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".penetration"), 0.0, delta=1e-6)
        self._assertMatrix(_matrix(self.owner + ".matrix"), _matrix(self.target + ".worldMatrix[0]"), 1e-6)

    def test_side_and_tapered_radius(self):
        """側面のいろいろな位置・向きで帯の外・帯の中・中・軸の近くまで入れ、式と一致し、中へ入らない。"""
        for parameter in (0.0, 0.25, 0.5, 0.9, 1.0):
            for direction in ((1, 0, 0), (0, 0, -1), (-1, 2, 3)):
                for length in (6.0, 3.0, 2.2, 1.0, 0.05):
                    with self.subTest(parameter=parameter, direction=direction, length=length):
                        self._place(parameter, direction, length)
                        distance, push, t = self._assertExpected()
                        self.assertAlmostEqual(t, parameter, delta=1e-4)
                        self.assertGreater(self._surfaceDistance(self.owner + ".matrix"), -1e-4)
                        radius = START_RADIUS + (END_RADIUS - START_RADIUS) * parameter
                        if length >= radius + SOFTNESS:
                            self.assertAlmostEqual(push, 0.0, delta=1e-6)
                        else:
                            self.assertGreater(push, 0.0)

    def test_end_caps(self):
        """軸の端より先では t が 0・1 に張り付き、端の点を中心とする半球の式になる。"""
        for parameter, direction in ((-0.3, (0, 1, 0)), (1.4, (1, 0, 0)), (-0.05, (0, 0, 1)),
                                     (1.02, (-1, 1, 0))):
            for length in (0.0, 0.8, 2.0):
                with self.subTest(parameter=parameter, direction=direction, length=length):
                    self._place(parameter, direction, length)
                    _distance, _push, t = self._assertExpected()
                    self.assertEqual(t, 0.0 if parameter < 0 else 1.0)
                    self.assertGreater(self._surfaceDistance(self.owner + ".matrix"), -1e-4)

    def test_hard_and_attributes(self):
        """softness=0なら表面で硬く止まり、半径・softnessを変えると式と一致する。"""
        cmds.setAttr(self.owner + ".softness", 0.0)
        for parameter, length in ((0.3, 4.0), (0.5, 1.5), (0.8, 0.5)):
            with self.subTest(parameter=parameter, length=length):
                self._place(parameter, (1, 1, 0), length)
                self._assertExpected(softness=0.0)
                self.assertAlmostEqual(self._surfaceDistance(self.owner + ".matrix"), max(
                    cmds.getAttr(self.owner + ".distance"), 0.0), delta=1e-4)
        cmds.setAttr(self.owner + ".softness", 2.0)
        cmds.setAttr(self.owner + ".startRadius", 1.0)
        cmds.setAttr(self.owner + ".endRadius", 3.0)
        for parameter, length in ((0.1, 5.0), (0.6, 2.0), (0.95, 1.0)):
            with self.subTest(parameter=parameter, length=length, softness=2.0):
                self._place(parameter, (0, 0, 1), length)
                self._assertExpected(startRadius=1.0, endRadius=3.0, softness=2.0)

    def test_axis_moves_and_rotation_kept(self):
        """軸の端を動かすと押し出しが付いてきて、出力の回転とscaleは入力のまま、端の回転・scaleは影響しない。"""
        self._place(0.5, (1, 0, 0), 1.0)
        cmds.setAttr(self.end + ".translate", 6, 3, -2)
        cmds.setAttr(self.end + ".rotate", -25, 30, 40)
        cmds.setAttr(self.end + ".scale", 5, 5, 5)
        self._assertExpected()
        out = _matrix(self.owner + ".matrix")
        source = _matrix(self.target + ".worldMatrix[0]")
        for index in range(12):
            self.assertAlmostEqual(out[index], source[index], delta=1e-6)

    def test_degenerate(self):
        """両端が一致すると始点を中心とする球になり、対象が軸上にあると向きが決まらないので押し出さない。"""
        self._place(0.5, (1, 0, 0), 0.0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".push"), 0.0, delta=1e-9)
        self._assertMatrix(_matrix(self.owner + ".matrix"), _matrix(self.target + ".worldMatrix[0]"), 1e-5)
        cmds.setAttr(self.end + ".translate", *cmds.getAttr(self.start + ".translate")[0])
        for direction, length in (((1, 0, 0), 1.0), ((0, 1, 1), 4.0)):
            with self.subTest(direction=direction, length=length):
                a, _b = self._ends()
                point = a + om.MVector(*direction).normal() * length
                cmds.setAttr(self.target + ".translate", point.x, point.y, point.z)
                _distance, _push, t = self._assertExpected()
                self.assertEqual(t, 0.0)

    def test_python_matches(self):
        """Python版 pushedPosition・closestParameter が出力と一致する。"""
        a, b = self._ends()
        for parameter, direction, length in ((0.4, (1, 2, -1), 1.2), (1.3, (0, 1, 0), 1.0), (0.7, (1, 0, 0), 6.0)):
            with self.subTest(parameter=parameter, direction=direction, length=length):
                self._place(parameter, direction, length)
                p = _position(_matrix(self.target + ".worldMatrix[0]"))
                point, start, end = (p.x, p.y, p.z), (a.x, a.y, a.z), (b.x, b.y, b.z)
                result = CapsuleCollision.pushedPosition(point, start, end, START_RADIUS, END_RADIUS, SOFTNESS)
                out = _position(_matrix(self.owner + ".matrix"))
                for x, y in zip(result, (out.x, out.y, out.z)):
                    self.assertAlmostEqual(x, y, delta=1e-4)
                self.assertAlmostEqual(CapsuleCollision.closestParameter(point, start, end),
                                       cmds.getAttr(self.owner + ".parameter"), delta=1e-5)
        self.assertEqual(CapsuleCollision.closestParameter((5, 0, 0), (1, 1, 1), (1, 1, 1)), 0.0)
        self.assertEqual(CapsuleCollision.pushedPosition((0, 1, 0), (0, 0, 0), (0, 2, 0), 1, 1, 1), (0.0, 1.0, 0.0))

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = cmds.listHistory(self.owner + ".matrix", pruneDagObjects=True) or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        start = cmds.createNode("transform", name="undoHip")
        end = cmds.createNode("transform", name="undoKnee")
        target = cmds.createNode("transform", name="undoCtrl")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        CapsuleCollision.create(target, start, end, name="undoCollide")
        self.assertTrue(cmds.objExists("undoCollide"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoCollide"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoCollide.parameter"))

    def test_arguments(self):
        """負の値・有限でない値・transform以外・同じノード・名前の重複を拒否する。"""
        for kwargs in ({"softness": -1.0}, {"startRadius": -0.5}, {"endRadius": -0.1},
                       {"startRadius": float("nan")}, {"softness": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                CapsuleCollision.create(self.target, self.start, self.end, name="bad", **kwargs)
        node = cmds.createNode("multiplyDivide")
        with self.assertRaises(ValueError):
            CapsuleCollision.create(node, self.start, self.end, name="bad")
        for nodes in ((self.target, self.start, self.start), (self.target, self.target, self.end),
                      (self.end, self.start, self.end)):
            with self.subTest(nodes=nodes), self.assertRaises(ValueError):
                CapsuleCollision.create(*nodes, name="bad")
        with self.assertRaises(ValueError):
            CapsuleCollision.create(self.target, self.start, self.end, name="collide")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
