"""EllipsoidCollisionの押し出しを、OpenMayaで独立に求めた楕円体の放射方向の半径・柔らかい押し出しの式と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import EllipsoidCollision, SphereCollision

RADII = (4.0, 6.0, 2.0)
SOFTNESS = 1.0


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _position(matrix):
    """行列の平行移動をMPointで返す。"""
    return om.MPoint(matrix[12], matrix[13], matrix[14])


def _rotation(node):
    """ノードのワールド回転(scaleを除く)をMQuaternionで返す。"""
    return om.MTransformationMatrix(_matrix(node + ".worldMatrix[0]")).rotation(asQuaternion=True)


def _radius(direction, rotation, radii):
    """ワールドの向き direction での楕円体の中心から表面までの距離を、OpenMayaの回転で局所へ戻して求める。"""
    local = om.MVector(direction).normal().rotateBy(rotation.inverse())
    return 1.0 / math.sqrt(sum((value / radius) ** 2 for value, radius in zip(local, radii)))


def _expected(target, ellipsoid, radii, softness):
    """OpenMayaで、期待する出力の行列・距離・押し出し量・押し込んだ深さ・向きの半径を求める。"""
    c = _position(_matrix(ellipsoid + ".worldMatrix[0]"))
    source = _matrix(target + ".worldMatrix[0]")
    p = _position(source)
    offset = p - c
    length = offset.length()
    if length > 1e-6:
        radius = _radius(offset, _rotation(ellipsoid), radii)
        direction = offset / length
    else:
        radius = _radius(om.MVector(1, 0, 0), _rotation(ellipsoid), radii)
        direction = om.MVector()
    distance = length - radius
    if softness <= 1e-4:
        pushed = max(distance, 0.0)
    elif distance >= softness:
        pushed = distance
    else:
        pushed = softness * math.exp((distance - softness) / softness)
    push = pushed - distance if length > 1e-6 else 0.0
    move = om.MMatrix()
    move[12], move[13], move[14] = direction.x * push, direction.y * push, direction.z * push
    return source * move, distance, push, max(-distance, 0.0), radius


class EllipsoidCollisionTest(unittest.TestCase):
    """作成時の姿勢・軸と斜めの向き・硬い押し出し・中心の動き・球との一致・中心・Python版・所有・Undo・引数を確認する。"""

    def setUp(self):
        """回転・拡大した楕円体の中心と、回転した対象を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.ellipsoid = cmds.createNode("transform", name="chest")
        cmds.setAttr(self.ellipsoid + ".translate", 1, 10, -1)
        cmds.setAttr(self.ellipsoid + ".rotate", 15, -30, 40)
        cmds.setAttr(self.ellipsoid + ".scale", 2, 0.5, 3)
        self.target = cmds.createNode("transform", name="handCtrl")
        cmds.setAttr(self.target + ".translate", 12, 14, 9)
        cmds.setAttr(self.target + ".rotate", 20, 40, -30)
        self.setup = EllipsoidCollision.create(self.target, self.ellipsoid, name="collide", radiusX=RADII[0],
                                               radiusY=RADII[1], radiusZ=RADII[2], softness=SOFTNESS)
        self.owner = str(self.setup.container)

    def _assertMatrix(self, actual, expected, tolerance=1e-4):
        for index, (a, b) in enumerate(zip(actual, expected)):
            self.assertAlmostEqual(a, b, delta=tolerance, msg="element {}".format(index))

    def _assertExpected(self, radii=RADII, softness=SOFTNESS):
        matrix, distance, push, penetration, radius = _expected(self.target, self.ellipsoid, radii, softness)
        self._assertMatrix(_matrix(self.owner + ".matrix"), matrix)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".distance"), distance, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".push"), push, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".penetration"), penetration, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".directionRadius"), radius, delta=1e-4)
        return distance, push, radius

    def _center(self):
        return _position(_matrix(self.ellipsoid + ".worldMatrix[0]"))

    def _normalizedRadius(self, plug, radii=RADII):
        """plugの行列の位置を楕円体の局所で各軸の半径で割った長さ。1以上なら表面の外。"""
        offset = _position(_matrix(plug)) - self._center()
        local = offset.rotateBy(_rotation(self.ellipsoid).inverse())
        return math.sqrt(sum((value / radius) ** 2 for value, radius in zip(local, radii)))

    def _place(self, localDirection, length):
        """対象を中心から、楕円体の局所の向き localDirection へ length の距離に置く。"""
        direction = om.MVector(*localDirection).normal().rotateBy(_rotation(self.ellipsoid))
        point = self._center() + direction * length
        cmds.setAttr(self.target + ".translate", point.x, point.y, point.z)

    def test_rest(self):
        """作成直後は表面から十分離れているので押し出さず、出力が入力のワールド行列と一致する(跳ねない)。"""
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".push"), 0.0, delta=1e-6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".penetration"), 0.0, delta=1e-6)
        self._assertMatrix(_matrix(self.owner + ".matrix"), _matrix(self.target + ".worldMatrix[0]"), 1e-6)

    def test_axes_and_diagonals(self):
        """軸と斜めの向きで帯の外・帯の中・中・中心の近くまで入れ、式と一致し、中へ入らず、同じ半直線上に出る。"""
        directions = ((1, 0, 0), (0, -1, 0), (0, 0, 1), (1, 1, 0), (-1, 2, 3), (2, -1, -1))
        for direction in directions:
            radius = EllipsoidCollision.directionRadius(direction, RADII)
            for length in (radius + 3.0, radius + 0.5, radius, radius * 0.5, 0.05):
                with self.subTest(direction=direction, length=length):
                    self._place(direction, length)
                    distance, push, actualRadius = self._assertExpected()
                    self.assertAlmostEqual(actualRadius, radius, delta=1e-4)
                    self.assertGreater(self._normalizedRadius(self.owner + ".matrix"), 1.0 - 1e-5)
                    source = _position(_matrix(self.target + ".worldMatrix[0]")) - self._center()
                    out = _position(_matrix(self.owner + ".matrix")) - self._center()
                    self.assertLess((source.normal() ^ out.normal()).length(), 1e-4)
                    if length >= radius + SOFTNESS:
                        self.assertAlmostEqual(push, 0.0, delta=1e-6)
                    else:
                        self.assertGreater(push, 0.0)
        for index, direction in enumerate(((1, 0, 0), (0, 1, 0), (0, 0, 1))):
            with self.subTest(axis=index):
                self.assertAlmostEqual(EllipsoidCollision.directionRadius(direction, RADII), RADII[index])

    def test_hard_and_attributes(self):
        """softness=0なら表面で硬く止まり、半径・softnessを変えると式と一致する。"""
        cmds.setAttr(self.owner + ".softness", 0.0)
        for direction, length in (((1, 0, 0), 6.0), ((0, 1, 1), 1.5), ((1, -1, 1), 0.5)):
            with self.subTest(direction=direction, length=length):
                self._place(direction, length)
                distance, _push, _radius = self._assertExpected(softness=0.0)
                if distance < 0.0:
                    self.assertAlmostEqual(self._normalizedRadius(self.owner + ".matrix"), 1.0, delta=1e-4)
        radii = (2.0, 3.0, 5.0)
        cmds.setAttr(self.owner + ".softness", 2.0)
        for item, value in zip("XYZ", radii):
            cmds.setAttr(self.owner + ".radius" + item, value)
        for direction, length in (((0, 0, 1), 6.0), ((1, 1, 0), 2.0), ((0, 1, 0), 1.0)):
            with self.subTest(direction=direction, length=length, softness=2.0):
                self._place(direction, length)
                self._assertExpected(radii=radii, softness=2.0)
                self.assertGreater(self._normalizedRadius(self.owner + ".matrix", radii), 1.0 - 1e-5)

    def test_center_moves_and_rotation_kept(self):
        """中心を移動・回転すると楕円体が付いてきて、出力の回転とscaleは入力のまま、中心のscaleは影響しない。"""
        self._place((1, 1, 0), 2.0)
        cmds.setAttr(self.ellipsoid + ".translate", 3, 11, 0)
        cmds.setAttr(self.ellipsoid + ".rotate", -25, 70, 10)
        cmds.setAttr(self.ellipsoid + ".scale", 5, 1, 0.2)
        self._assertExpected()
        out = _matrix(self.owner + ".matrix")
        source = _matrix(self.target + ".worldMatrix[0]")
        for index in range(12):
            self.assertAlmostEqual(out[index], source[index], delta=1e-6)
        parent = cmds.createNode("transform", name="parentScale")
        cmds.setAttr(parent + ".scale", 3, 1, 2)
        cmds.setAttr(parent + ".rotate", 10, 0, 35)
        cmds.parent(self.ellipsoid, parent)
        self._place((0, 1, 1), 1.0)
        self._assertExpected()

    def test_equal_radii_match_sphere(self):
        """3つの半径が同じなら、同じ対象と中心のSphereCollisionと一致する。"""
        for item in "XYZ":
            cmds.setAttr(self.owner + ".radius" + item, 3.0)
        sphere = SphereCollision.create(self.target, self.ellipsoid, name="sphereCollide", radius=3.0,
                                        softness=SOFTNESS)
        for direction, length in (((1, 2, 3), 5.0), ((0, -1, 0), 3.4), ((1, 0, -1), 1.0)):
            with self.subTest(direction=direction, length=length):
                self._place(direction, length)
                self._assertMatrix(_matrix(self.owner + ".matrix"), _matrix(str(sphere.container) + ".matrix"))
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".directionRadius"), 3.0, delta=1e-4)

    def test_degenerate(self):
        """対象が中心と一致すると向きが決まらないので押し出さない。"""
        self._place((1, 0, 0), 0.0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".push"), 0.0, delta=1e-9)
        self._assertMatrix(_matrix(self.owner + ".matrix"), _matrix(self.target + ".worldMatrix[0]"), 1e-5)
        self.assertAlmostEqual(EllipsoidCollision.directionRadius((0, 0, 0), RADII), RADII[0])
        self.assertEqual(EllipsoidCollision.pushedPosition((1, 2, 3), (1, 2, 3), RADII, 1.0), (1.0, 2.0, 3.0))

    def test_python_matches(self):
        """Python版 pushedPosition・directionRadius が出力と一致する。"""
        rotation = _rotation(self.ellipsoid)
        axes = [tuple(om.MVector(*axis).rotateBy(rotation)) for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
        for direction, length in (((1, 2, -1), 1.2), ((0, 1, 0), 5.5), ((1, 0, 0), 9.0), ((3, -1, 2), 2.5)):
            with self.subTest(direction=direction, length=length):
                self._place(direction, length)
                p = _position(_matrix(self.target + ".worldMatrix[0]"))
                c = self._center()
                result = EllipsoidCollision.pushedPosition((p.x, p.y, p.z), (c.x, c.y, c.z), RADII, SOFTNESS,
                                                           axes=axes)
                out = _position(_matrix(self.owner + ".matrix"))
                for x, y in zip(result, (out.x, out.y, out.z)):
                    self.assertAlmostEqual(x, y, delta=1e-4)
                self.assertAlmostEqual(EllipsoidCollision.directionRadius(direction, RADII),
                                       cmds.getAttr(self.owner + ".directionRadius"), delta=1e-4)

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = cmds.listHistory(self.owner + ".matrix", pruneDagObjects=True) or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        ellipsoid = cmds.createNode("transform", name="undoChest")
        target = cmds.createNode("transform", name="undoCtrl")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        EllipsoidCollision.create(target, ellipsoid, name="undoCollide")
        self.assertTrue(cmds.objExists("undoCollide"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoCollide"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoCollide.directionRadius"))

    def test_arguments(self):
        """0以下の半径・負のsoftness・有限でない値・transform以外・同じノード・名前の重複を拒否する。"""
        for kwargs in ({"softness": -1.0}, {"radiusX": 0.0}, {"radiusY": -0.5}, {"radiusZ": 1e-6},
                       {"radiusX": float("nan")}, {"softness": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                EllipsoidCollision.create(self.target, self.ellipsoid, name="bad", **kwargs)
        node = cmds.createNode("multiplyDivide")
        with self.assertRaises(ValueError):
            EllipsoidCollision.create(node, self.ellipsoid, name="bad")
        with self.assertRaises(ValueError):
            EllipsoidCollision.create(self.target, self.target, name="bad")
        with self.assertRaises(ValueError):
            EllipsoidCollision.create(self.target, self.ellipsoid, name="collide")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
