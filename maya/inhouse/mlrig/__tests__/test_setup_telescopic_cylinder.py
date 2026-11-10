"""TelescopicCylinderの各段の伸び・位置・向き・範囲を、Pythonの式とOpenMayaで独立に求めた値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import TelescopicCylinder


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


def _expected(extension, strokes, sequence):
    """式を直接書いた各段の伸び(extensionsOfと独立に書く)。"""
    total = min(max(extension, 0.0), sum(strokes))
    ordered = []
    rest = total
    for stroke in strokes:
        ordered.append(min(rest, stroke))
        rest -= ordered[-1]
    uniform = [total * stroke / sum(strokes) for stroke in strokes]
    return [g + sequence * (o - g) for g, o in zip(uniform, ordered)]


class TelescopicCylinderTest(unittest.TestCase):
    """既定値・順番/均等/中間の分配・位置と向き・範囲・行程の変更・他の軸・単位・所有・Undo・引数を確認する。"""

    def setUp(self):
        """X軸の取り付けと、生成時にまっすぐ先(閉じた長さ10)にある先端、行程 4・3・2 の3段を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.base = cmds.createNode("transform", name="base")
        cmds.setAttr(self.base + ".translate", 1, 2, 3)
        self.tip = cmds.createNode("transform", name="tip")
        cmds.setAttr(self.tip + ".translate", 11, 2, 3)
        self.strokes = [4.0, 3.0, 2.0]
        self.setup = TelescopicCylinder.create(self.base, self.tip, name="telescope", stroke=self.strokes)
        self.owner = str(self.setup.container)

    def _get(self, attribute):
        """containerのアトリビュートの値を返す。"""
        return cmds.getAttr(self.owner + "." + attribute)

    def _stages(self):
        """各段の伸びを返す。"""
        return [self._get("stageExtension[{}]".format(index)) for index in range(len(self.strokes))]

    def test_defaults(self):
        """既定は閉じた長さ=生成時の距離・sequence=1・行程=0.9×閉じた長さ。生成時は全段が縮んでいる。"""
        cmds.file(new=True, force=True)
        base = cmds.createNode("transform", name="defaultBase")
        tip = cmds.createNode("transform", name="defaultTip")
        cmds.setAttr(tip + ".translate", 0, 0, 5)
        setup = TelescopicCylinder.create(base, tip, name="defaults", axis="z")
        owner = str(setup.container)
        self.assertAlmostEqual(cmds.getAttr(owner + ".closedLength"), 5.0, delta=1e-6)
        self.assertAlmostEqual(cmds.getAttr(owner + ".sequence"), 1.0, delta=1e-6)
        self.assertEqual(cmds.getAttr(owner + ".stageStroke", multiIndices=True), [0, 1, 2])
        for index in range(3):
            self.assertAlmostEqual(cmds.getAttr("{}.stageStroke[{}]".format(owner, index)), 4.5, delta=1e-6)
            self.assertAlmostEqual(cmds.getAttr("{}.stageExtension[{}]".format(owner, index)), 0.0, delta=1e-6)
        for index in range(4):
            matrix = _matrix("{}.matrix[{}]".format(owner, index))
            self.assertLess((_position(matrix) - om.MPoint(0, 0, 0)).length(), 1e-6)
            self.assertLess(_angle(_rotation(matrix), om.MQuaternion()), 1e-4)
        self.assertLess((_position(_matrix(owner + ".tipMatrix")) - om.MPoint(0, 0, 5)).length(), 1e-6)

    def test_distribution(self):
        """順番・均等・中間のどれでも、各段の伸びが式と一致し、合計が全体の伸びになる。"""
        for sequence in (1.0, 0.0, 0.35):
            cmds.setAttr(self.owner + ".sequence", sequence)
            for extension in (0.0, 1.5, 4.0, 5.5, 8.0, 9.0):
                cmds.setAttr(self.tip + ".translateX", 11 + extension)
                expected = _expected(extension, self.strokes, sequence)
                with self.subTest(sequence=sequence, extension=extension):
                    for actual, value in zip(self._stages(), expected):
                        self.assertAlmostEqual(actual, value, delta=1e-5)
                    self.assertAlmostEqual(sum(self._stages()), extension, delta=1e-5)
                    self.assertAlmostEqual(self._get("extension"), extension, delta=1e-5)
                    self.assertAlmostEqual(self._get("overExtension"), 0.0, delta=1e-5)
                    for actual, value in zip(TelescopicCylinder.extensionsOf(extension, self.strokes, sequence),
                                             expected):
                        self.assertAlmostEqual(actual, value, delta=1e-9)
        # 順番では外側から伸び切る: 5.5 なら 4・1.5・0。
        cmds.setAttr(self.owner + ".sequence", 1.0)
        cmds.setAttr(self.tip + ".translateX", 16.5)
        for actual, value in zip(self._stages(), (4.0, 1.5, 0.0)):
            self.assertAlmostEqual(actual, value, delta=1e-5)

    def test_positions_and_orientation(self):
        """曲げた位置でも、各段は先端への向きの線上に累積の伸びだけ進み、向きは最短の回転と一致する。"""
        cmds.setAttr(self.base + ".rotate", 10, -15, 25)
        cmds.setAttr(self.owner + ".sequence", 0.6)
        base_world = _matrix(self.base + ".worldMatrix[0]")
        origin = _position(base_world)
        u = _row(base_world, 0)
        for local in ((14.0, 1.0, 0.0), (12.0, -2.0, 3.0), (17.5, 2.0, -1.0)):
            point = origin + om.MVector(*local) * base_world
            cmds.setAttr(self.tip + ".translate", point.x, point.y, point.z)
            distance = (point - origin).length()
            aim = (point - origin).normal()
            expected = _expected(distance - 10.0, self.strokes, 0.6)
            turn = _rotation(base_world) * om.MQuaternion(u, aim)
            with self.subTest(local=local):
                self.assertAlmostEqual(self._get("length"), distance, delta=1e-5)
                self.assertAlmostEqual(self._get("bendAngle"), math.degrees(u.angle(aim)), delta=1e-3)
                travelled = 0.0
                for index in range(4):
                    matrix = _matrix("{}.matrix[{}]".format(self.owner, index))
                    self.assertLess((_position(matrix) - (origin + aim * travelled)).length(), 1e-4)
                    self.assertLess((_row(matrix, 0) - aim).length(), 1e-4)
                    self.assertLess(_angle(_rotation(matrix), turn), 1e-3)
                    if index < 3:
                        travelled += expected[index]
                tip = _matrix(self.owner + ".tipMatrix")
                self.assertLess((_position(tip) - point).length(), 1e-4)

    def test_limits(self):
        """行程の合計を超えると全段が伸び切り、縮みすぎでは全段0。超えた量は overExtension に出て、先端は届かない。"""
        cmds.setAttr(self.tip + ".translateX", 11 + 12.0)
        self.assertAlmostEqual(self._get("extension"), 9.0, delta=1e-5)
        self.assertAlmostEqual(self._get("overExtension"), 3.0, delta=1e-5)
        for actual, value in zip(self._stages(), self.strokes):
            self.assertAlmostEqual(actual, value, delta=1e-5)
        self.assertAlmostEqual(_position(_matrix(self.owner + ".tipMatrix")).x, 1 + 19.0, delta=1e-5)
        cmds.setAttr(self.tip + ".translateX", 11 - 2.5)
        self.assertAlmostEqual(self._get("extension"), 0.0, delta=1e-5)
        self.assertAlmostEqual(self._get("overExtension"), -2.5, delta=1e-5)
        self.assertAlmostEqual(_position(_matrix(self.owner + ".tipMatrix")).x, 11.0, delta=1e-5)
        for sequence in (0.0, 1.0):
            cmds.setAttr(self.owner + ".sequence", sequence)
            for actual in self._stages():
                self.assertAlmostEqual(actual, 0.0, delta=1e-5)

    def test_editable_attributes(self):
        """生成後に閉じた長さ・各段の行程を変えると、分配と範囲がそれに従う。"""
        cmds.setAttr(self.owner + ".stageStroke[0]", 1.0)
        cmds.setAttr(self.owner + ".closedLength", 8.0)
        cmds.setAttr(self.tip + ".translateX", 11 + 2.0)  # 全体の伸び 12 - 8 = 4
        for actual, value in zip(self._stages(), _expected(4.0, [1.0, 3.0, 2.0], 1.0)):
            self.assertAlmostEqual(actual, value, delta=1e-5)
        cmds.setAttr(self.tip + ".translateX", 11 + 6.0)  # 16 - 8 = 8 > 6
        self.assertAlmostEqual(self._get("overExtension"), 2.0, delta=1e-5)

    def test_other_axis_parent_and_scale(self):
        """axis=zと、取り付けの親の回転・scaleでも各段は線上にあり、出力のscaleは1。"""
        parent = cmds.createNode("transform", name="baseParent")
        cmds.setAttr(parent + ".rotate", 20, -35, 50)
        cmds.setAttr(parent + ".scale", 2, 2, 2)
        base = cmds.createNode("transform", name="zBase", parent=parent)
        cmds.setAttr(base + ".scale", 1, 1.5, 0.5)
        tip = cmds.createNode("transform", name="zTip")
        cmds.setAttr(tip + ".translate", 3, -2, 6)
        setup = TelescopicCylinder.create(base, tip, name="zCylinder", stages=2, axis="z", closedLength=4.0,
                                          stroke=2.0, sequence=0.0)
        owner = str(setup.container)
        origin = _position(_matrix(base + ".worldMatrix[0]"))
        point = om.MPoint(3, -2, 6)
        aim = (point - origin).normal()
        each = min((point - origin).length() - 4.0, 4.0) / 2.0
        for index, travelled in enumerate((0.0, each, 2 * each)):
            matrix = _matrix("{}.matrix[{}]".format(owner, index))
            self.assertLess((_position(matrix) - (origin + aim * travelled)).length(), 1e-4)
            self.assertLess((_row(matrix, 2) - aim).length(), 1e-4)
            for value in om.MTransformationMatrix(matrix).scale(om.MSpace.kWorld):
                self.assertAlmostEqual(value, 1.0, delta=1e-5)

    def test_linear_unit(self):
        """UIの長さ単位がmmでも、長さ・伸びはcmで計算・出力する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="mm")
        try:
            base = cmds.createNode("transform", name="mmBase")
            tip = cmds.createNode("transform", name="mmTip")
            cmds.setAttr(tip + ".translate", 100, 0, 0)  # 10cm
            setup = TelescopicCylinder.create(base, tip, name="mmCylinder", stages=2, stroke=3.0)
            owner = str(setup.container)
            self.assertAlmostEqual(cmds.getAttr(owner + ".closedLength"), 10.0, delta=1e-5)
            cmds.setAttr(tip + ".translate", 140, 0, 0)
            self.assertAlmostEqual(cmds.getAttr(owner + ".extension"), 4.0, delta=1e-5)
            self.assertAlmostEqual(cmds.getAttr(owner + ".stageExtension[1]"), 1.0, delta=1e-5)
            matrix = om.MMatrix(cmds.getAttr(owner + ".matrix[2]"))
            self.assertAlmostEqual(matrix[12], 4.0, delta=1e-5)
        finally:
            cmds.currentUnit(linear="cm")

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = []
        for plug in ("matrix[3]", "tipMatrix", "overExtension", "stageExtension[2]"):
            upstream += cmds.listHistory(self.owner + "." + plug, pruneDagObjects=True) or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        base = cmds.createNode("transform", name="undoBase")
        tip = cmds.createNode("transform", name="undoTip")
        cmds.setAttr(tip + ".translate", 5, 1, 0)
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        TelescopicCylinder.create(base, tip, name="undoCylinder")
        self.assertTrue(cmds.objExists("undoCylinder"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoCylinder"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoCylinder.tipMatrix"))

    def test_arguments(self):
        """軸・段数・長さ・行程・sequenceの不正、transform以外・同じノード・名前の重複を拒否する。"""
        for kwargs in ({"axis": "w"}, {"stages": 0}, {"stages": 17}, {"stages": 2.0}, {"stages": True},
                       {"closedLength": 0.0}, {"closedLength": float("nan")}, {"stroke": 0.0},
                       {"stroke": [1.0, 2.0]}, {"stroke": [1.0, float("inf"), 1.0]}, {"sequence": 1.5},
                       {"sequence": -0.1}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    TelescopicCylinder.create(self.base, self.tip, name="bad", **kwargs)
        node = cmds.createNode("multiplyDivide")
        with self.assertRaises(ValueError):
            TelescopicCylinder.create(node, self.tip, name="bad")
        with self.assertRaises(ValueError):
            TelescopicCylinder.create(self.base, self.base, name="bad")
        with self.assertRaises(ValueError):
            TelescopicCylinder.create(self.base, self.tip, name="telescope")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
