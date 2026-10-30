"""BoxCollisionの押し出しを、OpenMayaで独立に求めた箱の符号付き距離・法線・柔らかい押し出しの式と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import BoxCollision, SphereCollision

SIZE = (8.0, 4.0, 6.0)
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


def _boxDistance(local, size, rounding):
    """局所の位置での角を丸めた箱の符号付き距離と局所の法線を、Pythonのクラスとは別の書き方で求める。"""
    half = [max(value / 2.0 - rounding, 0.0) for value in size]
    closest = om.MVector(*[min(max(value, -limit), limit) for value, limit in zip(local, half)])
    outside = om.MVector(local) - closest
    if outside.length() > 1e-6:
        return outside.length() - rounding, outside.normal()
    depths = [abs(value) - limit for value, limit in zip(local, half)]
    axis = max(range(3), key=lambda index: (depths[index], -index))
    normal = om.MVector()
    normal[axis] = 1.0 if local[axis] >= 0.0 else -1.0
    return depths[axis] - rounding, normal


def _expected(target, box, size, rounding, softness):
    """OpenMayaで、期待する出力の行列・距離・押し出し量・押し込んだ深さ・ワールドの法線を求める。"""
    c = _position(_matrix(box + ".worldMatrix[0]"))
    source = _matrix(target + ".worldMatrix[0]")
    rotation = _rotation(box)
    local = (_position(source) - c).rotateBy(rotation.inverse())
    distance, normal = _boxDistance(local, size, rounding)
    if softness <= 1e-4:
        pushed = max(distance, 0.0)
    elif distance >= softness:
        pushed = distance
    else:
        pushed = softness * math.exp((distance - softness) / softness)
    push = pushed - distance
    world = normal.rotateBy(rotation)
    move = om.MMatrix()
    move[12], move[13], move[14] = world.x * push, world.y * push, world.z * push
    return source * move, distance, push, max(-distance, 0.0), world


class BoxCollisionTest(unittest.TestCase):
    """作成時の姿勢・面/辺/角・中・丸め・硬い押し出し・中心の動き・球との一致・Python版・所有・Undo・引数を確認する。"""

    def setUp(self):
        """回転・拡大した箱の中心と、回転した対象を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.box = cmds.createNode("transform", name="pelvis")
        cmds.setAttr(self.box + ".translate", 1, 10, -1)
        cmds.setAttr(self.box + ".rotate", 15, -30, 40)
        cmds.setAttr(self.box + ".scale", 2, 0.5, 3)
        self.target = cmds.createNode("transform", name="skirtCtrl")
        cmds.setAttr(self.target + ".translate", 14, 16, 9)
        cmds.setAttr(self.target + ".rotate", 20, 40, -30)
        self.setup = BoxCollision.create(self.target, self.box, name="collide", sizeX=SIZE[0], sizeY=SIZE[1],
                                         sizeZ=SIZE[2], softness=SOFTNESS)
        self.owner = str(self.setup.container)

    def _assertMatrix(self, actual, expected, tolerance=1e-4):
        for index, (a, b) in enumerate(zip(actual, expected)):
            self.assertAlmostEqual(a, b, delta=tolerance, msg="element {}".format(index))

    def _assertExpected(self, size=SIZE, rounding=0.0, softness=SOFTNESS):
        matrix, distance, push, penetration, normal = _expected(self.target, self.box, size, rounding, softness)
        self._assertMatrix(_matrix(self.owner + ".matrix"), matrix)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".distance"), distance, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".push"), push, delta=1e-4)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".penetration"), penetration, delta=1e-4)
        for a, b in zip(cmds.getAttr(self.owner + ".normal")[0], normal):
            self.assertAlmostEqual(a, b, delta=1e-4)
        return distance, push

    def _center(self):
        return _position(_matrix(self.box + ".worldMatrix[0]"))

    def _local(self, plug):
        """plugの行列の位置の、箱の局所の位置。"""
        offset = _position(_matrix(plug)) - self._center()
        return offset.rotateBy(_rotation(self.box).inverse())

    def _place(self, local):
        """対象を箱の局所の位置 local へ置く。"""
        point = self._center() + om.MVector(*local).rotateBy(_rotation(self.box))
        cmds.setAttr(self.target + ".translate", point.x, point.y, point.z)

    def test_rest(self):
        """作成直後は表面から十分離れているので押し出さず、出力が入力のワールド行列と一致する(跳ねない)。"""
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".push"), 0.0, delta=1e-6)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".penetration"), 0.0, delta=1e-6)
        self._assertMatrix(_matrix(self.owner + ".matrix"), _matrix(self.target + ".worldMatrix[0]"), 1e-6)

    def test_faces_edges_corners(self):
        """面・辺・角の外と帯の中、面の中を式と比べ、外の点は最近点の向きへ、どれも箱の外へ出る。"""
        points = ((6.0, 0.5, -1.0), (4.5, 0.0, 0.0), (0.0, -2.4, 1.0), (1.0, 1.0, 3.2), (4.3, 2.3, 0.0),
                  (-4.4, 0.0, -3.5), (4.2, -2.2, 3.3), (-5.0, 3.0, 4.0), (3.5, 0.0, 0.0), (0.5, -1.5, 0.2),
                  (-1.0, 0.3, -2.8), (3.9, 1.8, 2.95))
        for local in points:
            with self.subTest(local=local):
                self._place(local)
                distance, push = self._assertExpected()
                out = self._local(self.owner + ".matrix")
                outside = max(abs(value) - limit / 2.0 for value, limit in zip(out, SIZE))
                self.assertGreater(outside, -1e-5)
                if distance >= SOFTNESS:
                    self.assertAlmostEqual(push, 0.0, delta=1e-6)
                else:
                    self.assertGreater(push, 0.0)

    def test_rounding_and_attributes(self):
        """丸めると角が球の一部になり、softness=0なら表面で硬く止まり、辺の長さを変えると式と一致する。"""
        cmds.setAttr(self.owner + ".rounding", 1.5)
        for local in ((4.5, 2.5, 3.5), (3.6, 1.8, 2.4), (0.0, 0.0, 3.4), (-4.2, 1.9, 0.0), (1.0, 0.5, -0.5)):
            with self.subTest(local=local, rounding=1.5):
                self._place(local)
                self._assertExpected(rounding=1.5)
        cmds.setAttr(self.owner + ".softness", 0.0)
        for local in ((4.1, 1.9, 2.9), (0.2, -1.5, 0.3), (-3.0, 0.0, 2.9)):
            with self.subTest(local=local, softness=0.0):
                self._place(local)
                distance, _push = self._assertExpected(rounding=1.5, softness=0.0)
                if distance < 0.0:
                    self.assertAlmostEqual(cmds.getAttr(self.owner + ".distance") + cmds.getAttr(
                        self.owner + ".push"), 0.0, delta=1e-6)
                    out = self._local(self.owner + ".matrix")
                    self.assertAlmostEqual(BoxCollision.signedDistance(out, SIZE, 1.5)[0], 0.0, delta=1e-4)
        size = (3.0, 10.0, 2.0)
        cmds.setAttr(self.owner + ".softness", 2.0)
        cmds.setAttr(self.owner + ".rounding", 0.0)
        for item, value in zip("XYZ", size):
            cmds.setAttr(self.owner + ".size" + item, value)
        for local in ((0.0, 6.0, 0.0), (2.0, 4.0, 1.5), (0.5, -1.0, 0.2)):
            with self.subTest(local=local, size=size):
                self._place(local)
                self._assertExpected(size=size, softness=2.0)

    def test_center_moves_and_rotation_kept(self):
        """中心を移動・回転すると箱が付いてきて、出力の回転とscaleは入力のまま、中心のscaleは影響しない。"""
        self._place((4.2, 1.0, 2.0))
        cmds.setAttr(self.box + ".translate", 3, 11, 0)
        cmds.setAttr(self.box + ".rotate", -25, 70, 10)
        cmds.setAttr(self.box + ".scale", 5, 1, 0.2)
        self._assertExpected()
        out = _matrix(self.owner + ".matrix")
        source = _matrix(self.target + ".worldMatrix[0]")
        for index in range(12):
            self.assertAlmostEqual(out[index], source[index], delta=1e-6)
        parent = cmds.createNode("transform", name="parentScale")
        cmds.setAttr(parent + ".scale", 3, 1, 2)
        cmds.setAttr(parent + ".rotate", 10, 0, 35)
        cmds.parent(self.box, parent)
        self._place((-1.0, 2.2, 2.6))
        self._assertExpected()

    def test_full_rounding_matches_sphere(self):
        """丸めの半径が辺の長さの半分以上で立方体なら、中心以外では同じ半径のSphereCollisionと一致する。"""
        for item in "XYZ":
            cmds.setAttr(self.owner + ".size" + item, 6.0)
        cmds.setAttr(self.owner + ".rounding", 3.0)
        sphere = SphereCollision.create(self.target, self.box, name="sphereCollide", radius=3.0, softness=SOFTNESS)
        for local in ((1.0, 2.0, 3.0), (0.0, -3.4, 0.0), (1.0, 0.0, -1.0), (5.0, 0.0, 0.0)):
            with self.subTest(local=local):
                self._place(local)
                self._assertMatrix(_matrix(self.owner + ".matrix"), _matrix(str(sphere.container) + ".matrix"))

    def test_center(self):
        """中心では X、Y、Z の順に優先した最も浅い面(立方体なら+X)へ押し出し、Python版も同じ向きを返す。"""
        for item in "XYZ":
            cmds.setAttr(self.owner + ".size" + item, 4.0)
        self._place((0.0, 0.0, 0.0))
        self._assertExpected(size=(4.0, 4.0, 4.0))
        out = self._local(self.owner + ".matrix")
        self.assertGreater(out.x, 2.0 - 1e-5)
        self.assertEqual(BoxCollision.signedDistance((0, 0, 0), (4, 4, 4)), (-2.0, (1.0, 0.0, 0.0)))
        self.assertEqual(BoxCollision.signedDistance((0, 0, 0), (4, 2, 4))[1], (0.0, 1.0, 0.0))

    def test_python_matches(self):
        """Python版 pushedPosition・signedDistance が出力と一致する。"""
        cmds.setAttr(self.owner + ".rounding", 0.8)
        rotation = _rotation(self.box)
        axes = [tuple(om.MVector(*axis).rotateBy(rotation)) for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
        for local in ((4.2, 1.0, -2.0), (0.5, 2.6, 0.0), (5.0, 3.0, 3.5), (-1.0, -0.5, 2.5)):
            with self.subTest(local=local):
                self._place(local)
                p = _position(_matrix(self.target + ".worldMatrix[0]"))
                c = self._center()
                result = BoxCollision.pushedPosition((p.x, p.y, p.z), (c.x, c.y, c.z), SIZE, SOFTNESS,
                                                     rounding=0.8, axes=axes)
                out = _position(_matrix(self.owner + ".matrix"))
                for x, y in zip(result, (out.x, out.y, out.z)):
                    self.assertAlmostEqual(x, y, delta=1e-4)
                self.assertAlmostEqual(BoxCollision.signedDistance(local, SIZE, 0.8)[0],
                                       cmds.getAttr(self.owner + ".distance"), delta=1e-4)

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = cmds.listHistory(self.owner + ".matrix", pruneDagObjects=True) or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        box = cmds.createNode("transform", name="undoBox")
        target = cmds.createNode("transform", name="undoCtrl")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        BoxCollision.create(target, box, name="undoCollide")
        self.assertTrue(cmds.objExists("undoCollide"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoCollide"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoCollide.normal"))

    def test_arguments(self):
        """0以下の辺・負の丸めとsoftness・有限でない値・transform以外・同じノード・名前の重複を拒否する。"""
        for kwargs in ({"softness": -1.0}, {"rounding": -0.1}, {"sizeX": 0.0}, {"sizeY": -0.5},
                       {"sizeZ": 1e-6}, {"sizeX": float("nan")}, {"rounding": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                BoxCollision.create(self.target, self.box, name="bad", **kwargs)
        node = cmds.createNode("multiplyDivide")
        with self.assertRaises(ValueError):
            BoxCollision.create(node, self.box, name="bad")
        with self.assertRaises(ValueError):
            BoxCollision.create(self.target, self.target, name="bad")
        with self.assertRaises(ValueError):
            BoxCollision.create(self.target, self.box, name="collide")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
