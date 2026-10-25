"""PlaneCollisionの押し出しを、OpenMayaで独立に求めた平面からの距離と柔らかい押し出しの式と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import PlaneCollision

SOFTNESS = 1.0
RADIUS = 0.5


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _expected(target, plane, softness, radius, axis=(0, 1, 0)):
    """OpenMayaで、期待する出力の行列・距離・押し出し量を求める。"""
    world = _matrix(plane + ".worldMatrix[0]")
    normal = (om.MVector(*axis) * world).normal()
    origin = om.MPoint(world[12], world[13], world[14])
    source = _matrix(target + ".worldMatrix[0]")
    point = om.MPoint(source[12], source[13], source[14])
    distance = (point - origin) * normal - radius
    if softness <= 1e-4:
        pushed = max(distance, 0.0)
    elif distance >= softness:
        pushed = distance
    else:
        pushed = softness * math.exp((distance - softness) / softness)
    push = pushed - distance
    move = om.MMatrix()
    move[12], move[13], move[14] = normal.x * push, normal.y * push, normal.z * push
    return source * move, distance, push


class PlaneCollisionTest(unittest.TestCase):
    """作成時の姿勢・帯の外/中/下・式の連続性・硬い押し出し・面の動き・回転の保持・軸・所有・Undo・引数を確認する。"""

    def setUp(self):
        """傾けて移動・拡大した面と、回転した対象を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.plane = cmds.createNode("transform", name="floor")
        cmds.setAttr(self.plane + ".translate", 1, 2, -1)
        cmds.setAttr(self.plane + ".rotate", 10, 0, 15)
        cmds.setAttr(self.plane + ".scale", 3, 0.5, 2)
        self.target = cmds.createNode("transform", name="ctrl")
        cmds.setAttr(self.target + ".translate", 1, 8, -1)
        cmds.setAttr(self.target + ".rotate", 20, 40, -30)
        self.setup = PlaneCollision.create(self.target, self.plane, name="collide", softness=SOFTNESS,
                                           radius=RADIUS)
        self.owner = str(self.setup.container)

    def _assertMatrix(self, actual, expected, tolerance=1e-4):
        for index, (a, b) in enumerate(zip(actual, expected)):
            self.assertAlmostEqual(a, b, delta=tolerance, msg="element {}".format(index))

    def _assertExpected(self, softness=SOFTNESS, radius=RADIUS):
        matrix, distance, push = _expected(self.target, self.plane, softness, radius)
        self._assertMatrix(_matrix(self.owner + ".matrix"), matrix)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".distance"), distance, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".push"), push, delta=1e-4)
        return distance, push

    def _height(self):
        """出力の位置の、面からの距離(radiusを含まない)。"""
        world = _matrix(self.plane + ".worldMatrix[0]")
        normal = (om.MVector(0, 1, 0) * world).normal()
        out = _matrix(self.owner + ".matrix")
        return (om.MPoint(out[12], out[13], out[14]) - om.MPoint(world[12], world[13], world[14])) * normal

    def _place(self, height):
        """対象を面の原点の真上(法線の向き)へ、面からheightの距離に置く。"""
        world = _matrix(self.plane + ".worldMatrix[0]")
        normal = (om.MVector(0, 1, 0) * world).normal()
        point = om.MPoint(world[12], world[13], world[14]) + normal * height
        cmds.setAttr(self.target + ".translate", point.x, point.y, point.z)

    def test_rest(self):
        """作成直後は面から十分離れているので押し出さず、出力が入力のワールド行列と一致する(跳ねない)。"""
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".push"), 0.0, delta=1e-6)
        self._assertMatrix(_matrix(self.owner + ".matrix"), _matrix(self.target + ".worldMatrix[0]"), 1e-6)

    def test_heights(self):
        """帯の外・帯の中・面の下・深く沈めた場合で、独立に求めた式と一致し、面より下へ沈まない。"""
        for height in (5.0, 1.6, 1.5, 1.2, 0.8, 0.5, 0.0, -2.0, -20.0):
            with self.subTest(height=height):
                self._place(height)
                distance, push = self._assertExpected()
                # plusMinusAverage等は単精度なので、20cm沈めた場合の丸め(約2e-6cm)を許す。
                self.assertGreater(self._height(), RADIUS - 1e-5)
                if height >= RADIUS + SOFTNESS:
                    self.assertAlmostEqual(push, 0.0, delta=1e-6)
                else:
                    self.assertGreater(push, 0.0)
        # 深く沈めると、面から radius の高さへ漸近する。
        self.assertAlmostEqual(self._height(), RADIUS, delta=1e-4)

    def test_response_is_smooth(self):
        """押し出した後の距離は単調で、帯の境界で値と傾きが連続する。"""
        values = [PlaneCollision.response(-3.0 + 0.01 * index, 1.0) for index in range(500)]
        self.assertTrue(all(b > a for a, b in zip(values, values[1:])))
        self.assertTrue(all(value > 0.0 for value in values))
        epsilon = 1e-6
        below = (PlaneCollision.response(1.0, 1.0) - PlaneCollision.response(1.0 - epsilon, 1.0)) / epsilon
        self.assertAlmostEqual(below, 1.0, delta=1e-4)
        self.assertEqual(PlaneCollision.response(-1.0, 0.0), 0.0)
        self.assertEqual(PlaneCollision.response(2.0, 0.0), 2.0)

    def test_hard_and_attributes(self):
        """softness=0なら面で硬く止まり、radius・softnessを変えると式と一致する。"""
        cmds.setAttr(self.owner + ".softness", 0.0)
        for height in (2.0, 0.6, 0.2, -1.0):
            with self.subTest(height=height):
                self._place(height)
                self._assertExpected(softness=0.0)
        self.assertAlmostEqual(self._height(), RADIUS, delta=1e-5)
        cmds.setAttr(self.owner + ".softness", 2.5)
        cmds.setAttr(self.owner + ".radius", -0.3)
        for height in (3.0, 1.0, -1.5):
            with self.subTest(height=height, softness=2.5):
                self._place(height)
                self._assertExpected(softness=2.5, radius=-0.3)

    def test_plane_moves_and_rotation_kept(self):
        """面を動かす・回すと押し出す向きが付いてきて、出力の回転とscaleは入力のまま。"""
        self._place(-1.0)
        cmds.setAttr(self.plane + ".rotate", -25, 30, 40)
        cmds.setAttr(self.plane + ".translate", -2, 3, 1)
        self._assertExpected()
        out = _matrix(self.owner + ".matrix")
        source = _matrix(self.target + ".worldMatrix[0]")
        for index in range(12):
            self.assertAlmostEqual(out[index], source[index], delta=1e-6)

    def test_axis(self):
        """axis=zでは面のローカルZを法線として押し出す。"""
        cmds.file(new=True, force=True)
        plane = cmds.createNode("transform", name="wall")
        cmds.setAttr(plane + ".rotate", 0, 30, 0)
        target = cmds.createNode("transform", name="hand")
        setup = PlaneCollision.create(target, plane, name="wallCollide", axis="z", softness=0.0)
        owner = str(setup.container)
        normal = om.MVector(0, 0, 1) * _matrix(plane + ".worldMatrix[0]")
        point = normal * -2.0
        cmds.setAttr(target + ".translate", point.x, point.y, point.z)
        matrix, _, push = _expected(target, plane, 0.0, 0.0, axis=(0, 0, 1))
        self.assertAlmostEqual(push, 2.0, delta=1e-6)
        self.assertAlmostEqual(cmds.getAttr(owner + ".push"), 2.0, delta=1e-5)
        self._assertMatrix(_matrix(owner + ".matrix"), matrix, 1e-5)

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = cmds.listHistory(self.owner + ".matrix", pruneDagObjects=True) or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        plane = cmds.createNode("transform", name="undoFloor")
        target = cmds.createNode("transform", name="undoCtrl")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        PlaneCollision.create(target, plane, name="undoCollide")
        self.assertTrue(cmds.objExists("undoCollide"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoCollide"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoCollide.matrix"))

    def test_arguments(self):
        """軸・負のsoftness・有限でない値・transform以外・同じノード・名前の重複を拒否する。"""
        for kwargs in ({"axis": "w"}, {"softness": -1.0}, {"radius": float("nan")},
                       {"softness": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                PlaneCollision.create(self.target, self.plane, name="bad", **kwargs)
        node = cmds.createNode("multiplyDivide")
        with self.assertRaises(ValueError):
            PlaneCollision.create(node, self.plane, name="bad")
        with self.assertRaises(ValueError):
            PlaneCollision.create(self.target, self.target, name="bad")
        with self.assertRaises(ValueError):
            PlaneCollision.create(self.target, self.plane, name="collide")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
