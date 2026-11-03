"""CoilSpringのらせんの各点を、OpenMayaで独立に組んだばねの座標系・ピッチ・密着長の式と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import CoilSpring

COUNT = 9
TURNS = 3.0
RADIUS = 1.5
WIRE = 0.4


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _position(matrix):
    """行列の平行移動をMPointで返す。"""
    return om.MPoint(matrix[12], matrix[13], matrix[14])


def _row(matrix, index):
    """行列の行ベクトル(長さ1)を返す。"""
    return om.MVector(matrix[index * 4], matrix[index * 4 + 1], matrix[index * 4 + 2]).normal()


def _springFrame(base, tip):
    """baseのX軸をtipへ向け、baseのY軸へ上方向を揃えた座標系の原点・軸・上・横を返す。"""
    base_world = _matrix(base + ".worldMatrix[0]")
    origin = _position(base_world)
    aim = (_position(_matrix(tip + ".worldMatrix[0]")) - origin).normal()
    reference = _row(base_world, 1)
    up = (reference - aim * (reference * aim)).normal()
    side = aim ^ up
    return origin, aim, up, side


def _expected(base, tip, count, turns, radius, wire):
    """OpenMayaで、各点の位置・半径方向・軸方向と、長さの出力を求める。"""
    origin, aim, up, side = _springFrame(base, tip)
    length = (_position(_matrix(tip + ".worldMatrix[0]")) - origin).length()
    solid = turns * wire
    effective = max(length, solid)
    points = []
    for index in range(count):
        ratio = index / (count - 1)
        angle = math.radians(360.0 * turns * ratio)
        radial = up * math.cos(angle) + side * math.sin(angle)
        points.append((origin + aim * (effective * ratio) + radial * radius, radial, aim))
    values = {"length": length, "solidLength": solid, "effectiveLength": effective,
              "pitch": effective / turns, "gap": effective / turns - wire, "coilBind": effective - length}
    return points, values


class CoilSpringTest(unittest.TestCase):
    """各点の位置と向き・伸縮・密着・baseの回転・アトリビュートの変更・Python版・所有・Undo・引数を確認する。"""

    def setUp(self):
        """回転したbaseと、斜めに離れたtipを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.base = cmds.createNode("transform", name="springBase")
        cmds.setAttr(self.base + ".translate", 1, 2, -3)
        cmds.setAttr(self.base + ".rotate", 10, 30, 20)
        self.tip = cmds.createNode("transform", name="springTip")
        cmds.setAttr(self.tip + ".translate", 4, 9, -1)
        self.setup = CoilSpring.create(self.base, self.tip, name="spring", count=COUNT, turns=TURNS,
                                       radius=RADIUS, wireDiameter=WIRE)
        self.owner = str(self.setup.container)

    def _assertExpected(self, turns=TURNS, radius=RADIUS, wire=WIRE, tolerance=1e-4):
        points, values = _expected(self.base, self.tip, COUNT, turns, radius, wire)
        for index, (position, radial, aim) in enumerate(points):
            matrix = _matrix("{}.matrix{}".format(self.owner, index))
            with self.subTest(point=index):
                self.assertLess((_position(matrix) - position).length(), tolerance)
                self.assertLess((_row(matrix, 1) - radial).length(), tolerance)
                self.assertLess((_row(matrix, 0) - aim).length(), tolerance)
        for attr, value in values.items():
            self.assertAlmostEqual(cmds.getAttr(self.owner + "." + attr), value, delta=tolerance, msg=attr)
        return values

    def test_rest(self):
        """生成時の配置が式と一致し、最初と最後の点は軸の両端から半径だけ離れる。"""
        values = self._assertExpected()
        self.assertEqual(values["coilBind"], 0.0)
        first = _position(_matrix(self.owner + ".matrix0"))
        last = _position(_matrix("{}.matrix{}".format(self.owner, COUNT - 1)))
        origin = _position(_matrix(self.base + ".worldMatrix[0]"))
        tip = _position(_matrix(self.tip + ".worldMatrix[0]"))
        self.assertAlmostEqual((first - origin).length(), RADIUS, delta=1e-4)
        self.assertAlmostEqual((last - tip).length(), RADIUS, delta=1e-4)

    def test_stretch_keeps_radius(self):
        """伸ばすとピッチだけが増え、半径は変わらない。"""
        cmds.setAttr(self.tip + ".translate", 8, 16, 2)
        values = self._assertExpected()
        self.assertGreater(values["pitch"], WIRE)
        origin, aim, _up, _side = _springFrame(self.base, self.tip)
        for index in range(COUNT):
            offset = _position(_matrix("{}.matrix{}".format(self.owner, index))) - origin
            radial = offset - aim * (offset * aim)
            self.assertAlmostEqual(radial.length(), RADIUS, delta=1e-4)

    def test_coil_bind(self):
        """密着長より縮めると、ばねは密着長で止まり、足りない分がcoilBindになる。"""
        origin = _position(_matrix(self.base + ".worldMatrix[0]"))
        direction = (_position(_matrix(self.tip + ".worldMatrix[0]")) - origin).normal()
        for length in (TURNS * WIRE + 0.3, TURNS * WIRE, 0.5, 0.05):
            point = origin + direction * length
            cmds.setAttr(self.tip + ".translate", point.x, point.y, point.z)
            with self.subTest(length=length):
                values = self._assertExpected()
                self.assertAlmostEqual(values["coilBind"], max(TURNS * WIRE - length, 0.0), delta=1e-4)
                self.assertGreaterEqual(cmds.getAttr(self.owner + ".gap"), -1e-6)
        # 安全な長さへ戻すと密着は解ける。
        cmds.setAttr(self.tip + ".translate", 4, 9, -1)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".coilBind"), 0.0, delta=1e-6)

    def test_base_rotation_twists(self):
        """baseを軸まわりに回すと巻き始めの向きが回り、tipへ向かう軸は変わらない。"""
        cmds.setAttr(self.base + ".rotate", 80, -20, 45)
        self._assertExpected()

    def test_attributes(self):
        """turns・radius・wireDiameterをcontainerで変えると配置が更新される。"""
        cmds.setAttr(self.owner + ".turns", 5.5)
        cmds.setAttr(self.owner + ".radius", 0.75)
        cmds.setAttr(self.owner + ".wireDiameter", 1.5)
        values = self._assertExpected(turns=5.5, radius=0.75, wire=1.5)
        self.assertGreater(values["coilBind"], 0.0)

    def test_python_matches(self):
        """coilLayoutの値がDGの出力と一致する。"""
        length = cmds.getAttr(self.owner + ".length")
        layout = CoilSpring.coilLayout(COUNT, length, TURNS, RADIUS, WIRE)
        for attr in ("solidLength", "effectiveLength", "pitch", "gap", "coilBind"):
            self.assertAlmostEqual(layout[attr], cmds.getAttr(self.owner + "." + attr), delta=1e-4, msg=attr)
        origin, aim, _up, _side = _springFrame(self.base, self.tip)
        for index, (axial, _angle, radius) in enumerate(layout["points"]):
            offset = _position(_matrix("{}.matrix{}".format(self.owner, index))) - origin
            self.assertAlmostEqual(offset * aim, axial, delta=1e-4)
            self.assertAlmostEqual((offset - aim * axial).length(), radius, delta=1e-4)

    def test_other_axes(self):
        """aimAxis=z・upAxis=xでも、指定した軸が軸方向・半径方向になる。"""
        setup = CoilSpring.create(self.base, self.tip, name="springZ", count=4, aimAxis="z", upAxis="x")
        owner = str(setup.container)
        origin = _position(_matrix(self.base + ".worldMatrix[0]"))
        aim = (_position(_matrix(self.tip + ".worldMatrix[0]")) - origin).normal()
        for index in range(4):
            matrix = _matrix("{}.matrix{}".format(owner, index))
            self.assertLess((_row(matrix, 2) - aim).length(), 1e-4)
            offset = _position(matrix) - origin
            radial = (offset - aim * (offset * aim)).normal()
            self.assertLess((_row(matrix, 0) - radial).length(), 1e-4)

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = cmds.listHistory(self.owner + ".matrix0", pruneDagObjects=True) or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        base = cmds.createNode("transform", name="undoBase")
        tip = cmds.createNode("transform", name="undoTip")
        cmds.setAttr(tip + ".translateX", 5)
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        CoilSpring.create(base, tip, name="undoSpring")
        self.assertTrue(cmds.objExists("undoSpring"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoSpring"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoSpring.coilBind"))

    def test_arguments(self):
        """軸・数・値の不正、transform以外・同じノード・同じ位置・名前の重複を拒否する。"""
        for kwargs in ({"count": 1}, {"turns": 0.2}, {"radius": 0.0}, {"wireDiameter": -0.1},
                       {"turns": float("nan")}, {"aimAxis": "y"}, {"upAxis": "w"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                CoilSpring.create(self.base, self.tip, name="bad", **kwargs)
        with self.assertRaises(TypeError):
            CoilSpring.create(self.base, self.tip, name="bad", count=3.0)
        node = cmds.createNode("multiplyDivide")
        with self.assertRaises(ValueError):
            CoilSpring.create(node, self.tip, name="bad")
        with self.assertRaises(ValueError):
            CoilSpring.create(self.base, self.base, name="bad")
        same = cmds.createNode("transform", name="sameSpot")
        cmds.matchTransform(same, self.base)
        with self.assertRaises(ValueError):
            CoilSpring.create(self.base, same, name="bad")
        with self.assertRaises(ValueError):
            CoilSpring.create(self.base, self.tip, name="spring")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
