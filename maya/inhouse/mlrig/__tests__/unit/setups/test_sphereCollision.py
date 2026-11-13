"""SphereCollisionの押し出しを、OpenMayaで独立に求めた球の表面からの距離と柔らかい押し出しの式と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import SphereCollision

RADIUS = 3.0
SOFTNESS = 1.0


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _position(matrix):
    """行列の平行移動をMPointで返す。"""
    return om.MPoint(matrix[12], matrix[13], matrix[14])


def _expected(target, sphere, radius, softness):
    """OpenMayaで、期待する出力の行列・距離・押し出し量・押し込んだ深さを求める。"""
    center = _position(_matrix(sphere + ".worldMatrix[0]"))
    source = _matrix(target + ".worldMatrix[0]")
    offset = _position(source) - center
    length = offset.length()
    distance = length - radius
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
    return source * move, distance, push, max(-distance, 0.0)


class SphereCollisionTest(unittest.TestCase):
    """作成時の姿勢・向きと距離の行列・硬い押し出し・球の動き・回転の保持・中心・Python版・所有・Undo・引数を確認する。"""

    def setUp(self):
        """移動・回転・拡大した球と、回転した対象を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.sphere = cmds.createNode("transform", name="head")
        cmds.setAttr(self.sphere + ".translate", 1, 6, -2)
        cmds.setAttr(self.sphere + ".rotate", 15, -30, 40)
        cmds.setAttr(self.sphere + ".scale", 2, 0.5, 3)
        self.target = cmds.createNode("transform", name="ctrl")
        cmds.setAttr(self.target + ".translate", 9, 6, -2)
        cmds.setAttr(self.target + ".rotate", 20, 40, -30)
        self.setup = SphereCollision.create(self.target, self.sphere, name="collide", radius=RADIUS,
                                            softness=SOFTNESS)
        self.owner = str(self.setup.container)

    def _assertMatrix(self, actual, expected, tolerance=1e-4):
        for index, (a, b) in enumerate(zip(actual, expected)):
            self.assertAlmostEqual(a, b, delta=tolerance, msg="element {}".format(index))

    def _assertExpected(self, radius=RADIUS, softness=SOFTNESS):
        matrix, distance, push, penetration = _expected(self.target, self.sphere, radius, softness)
        self._assertMatrix(_matrix(self.owner + ".matrix"), matrix)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".distance"), distance, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".push"), push, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".penetration"), penetration, delta=1e-4)
        return distance, push

    def _outputRadius(self):
        """出力の位置の、球の中心からの距離。"""
        center = _position(_matrix(self.sphere + ".worldMatrix[0]"))
        return (_position(_matrix(self.owner + ".matrix")) - center).length()

    def _place(self, direction, length):
        """対象を球の中心から direction の向きへ length の距離に置く。"""
        center = _position(_matrix(self.sphere + ".worldMatrix[0]"))
        point = center + om.MVector(*direction).normal() * length
        cmds.setAttr(self.target + ".translate", point.x, point.y, point.z)

    def test_rest(self):
        """作成直後は表面から十分離れているので押し出さず、出力が入力のワールド行列と一致する(跳ねない)。"""
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".push"), 0.0, delta=1e-6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".penetration"), 0.0, delta=1e-6)
        self._assertMatrix(_matrix(self.owner + ".matrix"), _matrix(self.target + ".worldMatrix[0]"), 1e-6)

    def test_directions_and_lengths(self):
        """いろいろな向きで帯の外・帯の中・球の中・中心の近くまで入れ、独立に求めた式と一致し、球の中へ入らない。"""
        for direction in ((1, 0, 0), (0, -1, 0), (-1, 2, 3), (0.3, -0.4, -1)):
            for length in (8.0, 4.2, 4.0, 3.6, 3.0, 2.0, 0.5, 0.01):
                with self.subTest(direction=direction, length=length):
                    self._place(direction, length)
                    distance, push = self._assertExpected()
                    self.assertGreater(self._outputRadius(), RADIUS - 1e-5)
                    if length >= RADIUS + SOFTNESS:
                        self.assertAlmostEqual(push, 0.0, delta=1e-6)
                    else:
                        self.assertGreater(push, 0.0)
        # 中心の近くまで入れると、表面へ漸近する(d = -2.99 で d' = exp(-3.99) ≒ 0.0185cm)。
        self.assertAlmostEqual(self._outputRadius(), RADIUS + math.exp(-3.99), delta=1e-4)

    def test_hard_and_attributes(self):
        """softness=0なら表面で硬く止まり、radius・softnessを変えると式と一致する。"""
        cmds.setAttr(self.owner + ".softness", 0.0)
        for length in (5.0, 3.2, 2.5, 0.5):
            with self.subTest(length=length):
                self._place((1, 1, 0), length)
                self._assertExpected(softness=0.0)
        self.assertAlmostEqual(self._outputRadius(), RADIUS, delta=1e-5)
        cmds.setAttr(self.owner + ".softness", 2.5)
        cmds.setAttr(self.owner + ".radius", 1.5)
        for length in (6.0, 3.0, 1.0):
            with self.subTest(length=length, softness=2.5):
                self._place((0, 0, 1), length)
                self._assertExpected(radius=1.5, softness=2.5)

    def test_sphere_moves_and_rotation_kept(self):
        """球を動かすと押し出す向きが付いてきて、出力の回転とscaleは入力のまま、球の回転・scaleは影響しない。"""
        self._place((1, 0, 0), 2.0)
        cmds.setAttr(self.sphere + ".translate", 3, 4, 0)
        cmds.setAttr(self.sphere + ".rotate", -25, 30, 40)
        cmds.setAttr(self.sphere + ".scale", 5, 5, 5)
        self._assertExpected()
        out = _matrix(self.owner + ".matrix")
        source = _matrix(self.target + ".worldMatrix[0]")
        for index in range(12):
            self.assertAlmostEqual(out[index], source[index], delta=1e-6)

    def test_center(self):
        """中心と一致すると向きが決まらないので押し出さない(入力のまま)。"""
        self._place((1, 0, 0), 0.0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".penetration"), RADIUS, delta=1e-5)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".push"), 0.0, delta=1e-9)
        # 中心からわずかに離すと、その向きへ押し出し始める。
        self._place((0, 0, -1), 0.001)
        self._assertExpected()
        self.assertGreater(self._outputRadius(), RADIUS - 1e-5)
        self._place((1, 0, 0), 0.0)
        self._assertMatrix(_matrix(self.owner + ".matrix"), _matrix(self.target + ".worldMatrix[0]"), 1e-5)

    def test_python_matches(self):
        """Python版 pushedPosition が出力の位置と一致する。"""
        center = _position(_matrix(self.sphere + ".worldMatrix[0]"))
        for direction, length in (((1, 2, -1), 2.2), ((0, 1, 0), 3.5), ((1, 0, 0), 6.0)):
            with self.subTest(direction=direction, length=length):
                self._place(direction, length)
                point = _position(_matrix(self.target + ".worldMatrix[0]"))
                result = SphereCollision.pushedPosition(point, center, RADIUS, SOFTNESS)
                out = _position(_matrix(self.owner + ".matrix"))
                for a, b in zip(result, (out.x, out.y, out.z)):
                    self.assertAlmostEqual(a, b, delta=1e-4)
        self.assertEqual(SphereCollision.pushedPosition((1, 2, 3), (1, 2, 3), 1.0, 1.0), (1.0, 2.0, 3.0))

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = cmds.listHistory(self.owner + ".matrix", pruneDagObjects=True) or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        sphere = cmds.createNode("transform", name="undoHead")
        target = cmds.createNode("transform", name="undoCtrl")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        SphereCollision.create(target, sphere, name="undoCollide")
        self.assertTrue(cmds.objExists("undoCollide"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoCollide"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoCollide.penetration"))

    def test_arguments(self):
        """負の値・有限でない値・transform以外・同じノード・名前の重複を拒否する。"""
        for kwargs in ({"softness": -1.0}, {"radius": -0.5}, {"radius": float("nan")},
                       {"softness": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                SphereCollision.create(self.target, self.sphere, name="bad", **kwargs)
        node = cmds.createNode("multiplyDivide")
        with self.assertRaises(ValueError):
            SphereCollision.create(node, self.sphere, name="bad")
        with self.assertRaises(ValueError):
            SphereCollision.create(self.target, self.target, name="bad")
        with self.assertRaises(ValueError):
            SphereCollision.create(self.target, self.sphere, name="collide")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
