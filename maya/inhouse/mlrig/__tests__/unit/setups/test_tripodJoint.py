"""TripodJointのスパイダーの位置・プランジ・範囲・シャフトの向きを、OpenMayaで独立に求めた値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import TripodJoint


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _position(matrix):
    """行列の平行移動をMPointで返す。"""
    return om.MPoint(matrix[12], matrix[13], matrix[14])


def _row(matrix, index):
    """行列の行ベクトル(長さ1)を返す。"""
    return om.MVector(matrix[index * 4], matrix[index * 4 + 1], matrix[index * 4 + 2]).normal()


def _rotation(matrix):
    """行列の回転(scaleを除く)をMQuaternionで返す。"""
    return om.MTransformationMatrix(matrix).rotation(asQuaternion=True)


def _angle(first, second):
    """2つのクォータニオンの差の回転角(度、0〜180)。"""
    turn = math.degrees((first * second.inverse()).asAxisAngle()[1]) % 360.0
    return min(turn, 360.0 - turn)


class TripodJointTest(unittest.TestCase):
    """まっすぐ・直線と球の交点・範囲・届かない場合・等速・tipMatrix・他の軸・単位・所有・Undo・引数を確認する。"""

    def setUp(self):
        """X軸のハウジングと、生成時にまっすぐ先(長さ10)にある外側の継手を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.housing = cmds.createNode("transform", name="housing")
        cmds.setAttr(self.housing + ".translate", 1, 2, 3)
        self.outer = cmds.createNode("transform", name="outerJoint")
        cmds.setAttr(self.outer + ".translate", 11, 2, 3)
        self.setup = TripodJoint.create(self.housing, self.outer, name="tripod")
        self.owner = str(self.setup.container)

    def _get(self, attribute):
        """containerのアトリビュートの値を返す。"""
        return cmds.getAttr(self.owner + "." + attribute)

    def _expected(self, housing, outer, length, minimum, maximum, axis=0):
        """OpenMayaで直線と球の交点を解き、(制限前のプランジ, スパイダーの中心, ハウジングの軸)を返す。"""
        world = _matrix(housing + ".worldMatrix[0]")
        origin = _position(world)
        u = _row(world, axis)
        d = _position(_matrix(outer + ".worldMatrix[0]")) - origin
        a = d * u
        b = (d - u * a).length()
        raw = a - math.sqrt(max(length * length - b * b, 0.0))
        return raw, origin + u * min(max(raw, minimum), maximum), u

    def test_defaults_and_straight(self):
        """既定は長さ=生成時の距離・範囲±10%。まっすぐ軸に沿って動かすとプランジがそのまま移動量になる。"""
        self.assertAlmostEqual(self._get("length"), 10.0, delta=1e-6)
        self.assertAlmostEqual(self._get("minPlunge"), -1.0, delta=1e-6)
        self.assertAlmostEqual(self._get("maxPlunge"), 1.0, delta=1e-6)
        for move in (0.0, 0.6, -0.8):
            cmds.setAttr(self.outer + ".translateX", 11 + move)
            with self.subTest(move=move):
                self.assertAlmostEqual(self._get("plunge"), move, delta=1e-5)
                self.assertAlmostEqual(self._get("overPlunge"), 0.0, delta=1e-5)
                self.assertAlmostEqual(self._get("shaftLength"), 10.0, delta=1e-5)
                self.assertAlmostEqual(self._get("stretch"), 0.0, delta=1e-5)
                self.assertAlmostEqual(self._get("bendAngle"), 0.0, delta=1e-3)
                matrix = _matrix(self.owner + ".matrix")
                housing = _matrix(self.housing + ".worldMatrix[0]")
                self.assertLess(_angle(_rotation(matrix), _rotation(housing)), 1e-3)
                self.assertLess((_position(matrix) - om.MPoint(1 + move, 2, 3)).length(), 1e-5)

    def test_line_sphere_intersection(self):
        """曲げた位置でも、スパイダーは軸上でシャフトの長さを保ち、シャフトの向きは最短の回転と一致する。"""
        cmds.setAttr(self.housing + ".rotate", 10, -15, 25)
        for offset in ((9.8, 1.5, 0.0), (9.9, 0.0, -1.2), (9.6, -2.0, 1.0), (10.3, 1.0, 1.0)):
            local = om.MVector(*offset) * _matrix(self.housing + ".worldMatrix[0]")
            point = _position(_matrix(self.housing + ".worldMatrix[0]")) + local
            cmds.setAttr(self.outer + ".translate", point.x, point.y, point.z)
            raw, center, u = self._expected(self.housing, self.outer, 10.0, -1.0, 1.0)
            with self.subTest(offset=offset):
                self.assertTrue(-1.0 < raw < 1.0)
                self.assertAlmostEqual(self._get("plunge"), raw, delta=1e-5)
                matrix = _matrix(self.owner + ".matrix")
                self.assertLess((_position(matrix) - center).length(), 1e-4)
                self.assertAlmostEqual((point - _position(matrix)).length(), 10.0, delta=1e-4)
                self.assertAlmostEqual(self._get("stretch"), 0.0, delta=1e-4)
                aim = (point - center).normal()
                self.assertLess((_row(matrix, 0) - aim).length(), 1e-4)
                expected = _rotation(_matrix(self.housing + ".worldMatrix[0]")) * om.MQuaternion(u, aim)
                self.assertLess(_angle(_rotation(matrix), expected), 1e-3)
                self.assertAlmostEqual(self._get("bendAngle"), math.degrees(u.angle(aim)), delta=1e-3)
                self.assertAlmostEqual(TripodJoint.plungeOf(offset[0], math.hypot(offset[1], offset[2]), 10.0), raw,
                                       delta=1e-9)

    def test_limits(self):
        """範囲を超えるとプランジが止まり、超えた量が overPlunge、シャフトの伸び縮みが stretch に出る。"""
        for move, plunge in ((2.5, 1.0), (-3.0, -1.0)):
            cmds.setAttr(self.outer + ".translate", 11 + move, 4, 3)
            raw, center, _ = self._expected(self.housing, self.outer, 10.0, -1.0, 1.0)
            with self.subTest(move=move):
                self.assertAlmostEqual(self._get("plunge"), plunge, delta=1e-5)
                self.assertAlmostEqual(self._get("overPlunge"), raw - plunge, delta=1e-5)
                self.assertGreater(abs(self._get("overPlunge")), 0.1)
                shaft = (_position(_matrix(self.outer + ".worldMatrix[0]")) - center).length()
                self.assertAlmostEqual(self._get("shaftLength"), shaft, delta=1e-5)
                self.assertAlmostEqual(self._get("stretch"), shaft - 10.0, delta=1e-5)
                self.assertEqual(self._get("stretch") > 0, move > 0)
        # 範囲を広げると同じ位置で長さが保たれる。
        cmds.setAttr(self.owner + ".maxPlunge", 5.0)
        cmds.setAttr(self.outer + ".translate", 13.5, 4, 3)
        self.assertAlmostEqual(self._get("overPlunge"), 0.0, delta=1e-5)
        self.assertAlmostEqual(self._get("shaftLength"), 10.0, delta=1e-5)

    def test_unreachable(self):
        """軸から長さより遠いと、制限前のプランジは軸に最も近い点 a になる。"""
        cmds.setAttr(self.owner + ".maxPlunge", 20.0)
        cmds.setAttr(self.outer + ".translate", 5, 14, 3)
        self.assertAlmostEqual(self._get("plunge"), 4.0, delta=1e-5)
        self.assertAlmostEqual(self._get("shaftLength"), 12.0, delta=1e-5)
        self.assertAlmostEqual(self._get("stretch"), 2.0, delta=1e-5)
        self.assertAlmostEqual(self._get("bendAngle"), 90.0, delta=1e-3)
        self.assertAlmostEqual(TripodJoint.plungeOf(4.0, 12.0, 10.0), 4.0, delta=1e-9)

    def test_constant_velocity_and_tip(self):
        """ハウジングを θ 回すとシャフトもシャフトの軸まわりに θ 回る。tipMatrixは同じ向きで外側の継手の位置。"""
        cmds.setAttr(self.outer + ".translate", 10.5, 4.5, 3)
        rest = _rotation(_matrix(self.owner + ".matrix"))
        aim = _row(_matrix(self.owner + ".matrix"), 0)
        for spin in range(30, 360, 30):
            cmds.setAttr(self.housing + ".rotateX", spin)
            with self.subTest(spin=spin):
                matrix = _matrix(self.owner + ".matrix")
                turn = rest.inverse() * _rotation(matrix)
                self.assertLess(_angle(turn, om.MQuaternion(math.radians(spin), aim)), 1e-3)
                tip = _matrix(self.owner + ".tipMatrix")
                self.assertLess(_angle(_rotation(tip), _rotation(matrix)), 1e-4)
                self.assertLess((_position(tip) - om.MPoint(10.5, 4.5, 3)).length(), 1e-5)

    def test_other_axis_parent_and_scale(self):
        """axis=zと、ハウジングの親の回転・scale、範囲の指定でも交点と一致し、出力のscaleは1。"""
        parent = cmds.createNode("transform", name="housingParent")
        cmds.setAttr(parent + ".rotate", 20, -35, 50)
        cmds.setAttr(parent + ".scale", 2, 2, 2)
        housing = cmds.createNode("transform", name="zHousing", parent=parent)
        cmds.setAttr(housing + ".rotateZ", 33.0)
        cmds.setAttr(housing + ".scale", 1, 1.5, 0.5)
        outer = cmds.createNode("transform", name="zOuter")
        cmds.setAttr(outer + ".translate", 3, -2, 6)
        setup = TripodJoint.create(housing, outer, name="zJoint", axis="z", length=6.0, minPlunge=-3, maxPlunge=3)
        owner = str(setup.container)
        raw, center, u = self._expected(housing, outer, 6.0, -3.0, 3.0, axis=2)
        self.assertAlmostEqual(cmds.getAttr(owner + ".plunge"), min(max(raw, -3.0), 3.0), delta=1e-5)
        matrix = _matrix(owner + ".matrix")
        self.assertLess((_position(matrix) - center).length(), 1e-4)
        aim = (om.MPoint(3, -2, 6) - center).normal()
        self.assertLess((_row(matrix, 2) - aim).length(), 1e-4)
        for value in om.MTransformationMatrix(matrix).scale(om.MSpace.kWorld):
            self.assertAlmostEqual(value, 1.0, delta=1e-5)

    def test_linear_unit(self):
        """UIの長さ単位がmmでも、長さ・プランジはcmで計算・出力する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="mm")
        try:
            housing = cmds.createNode("transform", name="mmHousing")
            outer = cmds.createNode("transform", name="mmOuter")
            cmds.setAttr(outer + ".translate", 100, 0, 0)  # 10cm
            setup = TripodJoint.create(housing, outer, name="mmJoint")
            owner = str(setup.container)
            self.assertAlmostEqual(cmds.getAttr(owner + ".length"), 10.0, delta=1e-5)
            cmds.setAttr(outer + ".translate", 105, 0, 0)
            self.assertAlmostEqual(cmds.getAttr(owner + ".plunge"), 0.5, delta=1e-5)
            self.assertAlmostEqual(cmds.getAttr(owner + ".shaftLength"), 10.0, delta=1e-5)
            matrix = om.MMatrix(cmds.getAttr(owner + ".matrix"))
            self.assertAlmostEqual(matrix[12], 0.5, delta=1e-5)
        finally:
            cmds.currentUnit(linear="cm")

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = []
        for plug in ("matrix", "tipMatrix", "plunge", "stretch"):
            upstream += cmds.listHistory(self.owner + "." + plug, pruneDagObjects=True) or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        housing = cmds.createNode("transform", name="undoHousing")
        outer = cmds.createNode("transform", name="undoOuter")
        cmds.setAttr(outer + ".translate", 5, 1, 0)
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        TripodJoint.create(housing, outer, name="undoJoint")
        self.assertTrue(cmds.objExists("undoJoint"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoJoint"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoJoint.tipMatrix"))

    def test_arguments(self):
        """軸・長さ・範囲の不正、transform以外・同じノード・名前の重複を拒否する。"""
        for kwargs in ({"axis": "w"}, {"length": 0.0}, {"length": float("nan")},
                       {"minPlunge": 2.0, "maxPlunge": 1.0}, {"maxPlunge": float("inf")}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    TripodJoint.create(self.housing, self.outer, name="bad", **kwargs)
        node = cmds.createNode("multiplyDivide")
        with self.assertRaises(ValueError):
            TripodJoint.create(node, self.outer, name="bad")
        with self.assertRaises(ValueError):
            TripodJoint.create(self.housing, self.housing, name="bad")
        with self.assertRaises(ValueError):
            TripodJoint.create(self.housing, self.outer, name="tripod")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
