"""ConstantVelocityJointの出力軸・ケージの向きと等速性を、OpenMayaで独立に求めた最短の回転と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import ConstantVelocityJoint, UniversalJoint


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


class ConstantVelocityJointTest(unittest.TestCase):
    """まっすぐ・最短の回転・等速・ケージの二等分・atTarget・他の軸・scale・所有・Undo・引数を確認する。"""

    def setUp(self):
        """X軸の入力軸と、XY平面で上へ曲げた出力軸の先の点を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.shaft = cmds.createNode("transform", name="inputShaft")
        cmds.setAttr(self.shaft + ".translate", 1, 2, 3)
        self.target = cmds.createNode("transform", name="outputTarget")
        self._bend(30.0)
        self.setup = ConstantVelocityJoint.create(self.shaft, self.target, name="cv")
        self.owner = str(self.setup.container)

    def _bend(self, degrees, length=5.0, tilt=0.0):
        """出力軸の先の点を、中心から degrees だけ上へ、tilt だけ奥へ曲げた位置へ置く。"""
        radians = math.radians(degrees)
        side = math.radians(tilt)
        cmds.setAttr(self.target + ".translate", 1 + length * math.cos(radians) * math.cos(side),
                     2 + length * math.sin(radians), 3 + length * math.cos(radians) * math.sin(side))

    def _expected(self, toward):
        """入力の回転に、入力軸を toward へ回す最短の回転をOpenMayaで掛けたクォータニオン。"""
        world = _matrix(self.shaft + ".worldMatrix[0]")
        arc = om.MQuaternion(_row(world, 0), toward)
        return _rotation(world) * arc

    def test_straight_matches_input(self):
        """まっすぐなら出力・ケージは入力軸と同じ向きで、曲げ角0。"""
        self._bend(0.0)
        for spin in (0.0, 35.0, 170.0, -100.0):
            cmds.setAttr(self.shaft + ".rotateX", spin)
            with self.subTest(spin=spin):
                expected = _matrix(self.shaft + ".worldMatrix[0]")
                for plug in ("matrix", "cageMatrix"):
                    output = _matrix(self.owner + "." + plug)
                    self.assertLess(_angle(_rotation(output), _rotation(expected)), 1e-3)
                    self.assertLess((_position(output) - _position(expected)).length(), 1e-4)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".bendAngle"), 0.0, delta=1e-3)

    def test_shortest_arc(self):
        """出力軸は先の点を向き、向きは入力の回転に最短の回転を掛けたものと一致する。"""
        for spin, bend, tilt in ((0.0, 30.0, 0.0), (40.0, 30.0, 20.0), (123.0, 55.0, -35.0), (-70.0, 10.0, 80.0)):
            self._bend(bend, tilt=tilt)
            cmds.setAttr(self.shaft + ".rotateX", spin)
            with self.subTest(spin=spin, bend=bend, tilt=tilt):
                matrix = _matrix(self.owner + ".matrix")
                world = _matrix(self.shaft + ".worldMatrix[0]")
                center = _position(world)
                aim = (_position(_matrix(self.target + ".worldMatrix[0]")) - center).normal()
                self.assertLess((_row(matrix, 0) - aim).length(), 1e-4)
                self.assertLess(_angle(_rotation(matrix), self._expected(aim)), 1e-3)
                self.assertLess((_position(matrix) - center).length(), 1e-4)
                expectedBend = math.degrees(math.acos(max(-1.0, min(1.0, _row(world, 0) * aim))))
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".bendAngle"), expectedBend, delta=1e-3)

    def test_constant_velocity(self):
        """入力軸を θ 回すと出力軸も出力軸まわりに θ 回る(UniversalJointは揺れる)。"""
        bend = 40.0
        self._bend(bend)
        universal = UniversalJoint.create(self.shaft, self.target, name="uj")
        cmds.setAttr(self.shaft + ".rotateX", 0.0)
        rest = _rotation(_matrix(self.owner + ".matrix"))
        restUniversal = _rotation(_matrix(str(universal.container) + ".matrix"))
        aim = _row(_matrix(self.owner + ".matrix"), 0)
        largest = 0.0
        for spin in range(15, 360, 15):
            cmds.setAttr(self.shaft + ".rotateX", spin)
            turn = rest.inverse() * _rotation(_matrix(self.owner + ".matrix"))
            expected = om.MQuaternion(math.radians(spin), aim)
            with self.subTest(spin=spin):
                self.assertLess(_angle(turn, expected), 1e-3)
            turnUniversal = restUniversal.inverse() * _rotation(_matrix(str(universal.container) + ".matrix"))
            largest = max(largest, _angle(turnUniversal, expected))
        # 同じ曲げ角の十字軸継手は、出力の角度が入力から数度ずれる区間がある。
        self.assertGreater(largest, 3.0)

    def test_cage_bisects(self):
        """ケージの軸は二等分の向き h を向き、等速面は両軸と同じ角度をなす。ケージは最短の回転の半分。"""
        for spin, bend, tilt in ((0.0, 30.0, 0.0), (75.0, 50.0, 30.0), (-140.0, 20.0, -60.0)):
            self._bend(bend, tilt=tilt)
            cmds.setAttr(self.shaft + ".rotateX", spin)
            with self.subTest(spin=spin, bend=bend, tilt=tilt):
                cage = _matrix(self.owner + ".cageMatrix")
                world = _matrix(self.shaft + ".worldMatrix[0]")
                inputAxis = _row(world, 0)
                outputAxis = _row(_matrix(self.owner + ".matrix"), 0)
                half = (inputAxis + outputAxis).normal()
                self.assertLess((_row(cage, 0) - half).length(), 1e-4)
                self.assertAlmostEqual(_row(cage, 0) * inputAxis, _row(cage, 0) * outputAxis, delta=1e-5)
                self.assertLess(_angle(_rotation(cage), self._expected(half)), 1e-3)
                self.assertLess((_position(cage) - _position(world)).length(), 1e-4)
                # ケージから見て、入力と出力の向きは等速面に対して鏡像(半分ずつの回転)。
                middle = _rotation(cage)
                self.assertAlmostEqual(_angle(middle, _rotation(world)),
                                       _angle(_rotation(_matrix(self.owner + ".matrix")), middle), delta=1e-3)

    def test_at_target(self):
        """atTargetでは位置が先の点になり、向きは中心に置いた場合と同じ。ケージは中心のまま。"""
        setup = ConstantVelocityJoint.create(self.shaft, self.target, name="atTip", atTarget=True)
        owner = str(setup.container)
        for spin in (0.0, 70.0, -140.0):
            cmds.setAttr(self.shaft + ".rotateX", spin)
            with self.subTest(spin=spin):
                atTip = _matrix(owner + ".matrix")
                self.assertLess(_angle(_rotation(atTip), _rotation(_matrix(self.owner + ".matrix"))), 1e-3)
                target = _position(_matrix(self.target + ".worldMatrix[0]"))
                self.assertLess((_position(atTip) - target).length(), 1e-4)
                center = _position(_matrix(self.shaft + ".worldMatrix[0]"))
                self.assertLess((_position(_matrix(owner + ".cageMatrix")) - center).length(), 1e-4)

    def test_other_axis_parent_rotation_and_scale(self):
        """axis=zと、入力軸の親の回転・scaleでも向きが最短の回転と一致し、出力のscaleは1。"""
        parent = cmds.createNode("transform", name="shaftParent")
        cmds.setAttr(parent + ".rotate", 20, -35, 50)
        cmds.setAttr(parent + ".scale", 2, 2, 2)
        shaft = cmds.createNode("transform", name="zShaft", parent=parent)
        cmds.setAttr(shaft + ".rotateZ", 33.0)
        cmds.setAttr(shaft + ".scale", 1, 1.5, 0.5)
        target = cmds.createNode("transform", name="zTarget")
        cmds.setAttr(target + ".translate", 3, -2, 6)
        setup = ConstantVelocityJoint.create(shaft, target, name="zJoint", axis="z")
        matrix = _matrix(str(setup.container) + ".matrix")
        world = _matrix(shaft + ".worldMatrix[0]")
        aim = (_position(_matrix(target + ".worldMatrix[0]")) - _position(world)).normal()
        self.assertLess((_row(matrix, 2) - aim).length(), 1e-4)
        expected = _rotation(world) * om.MQuaternion(_row(world, 2), aim)
        self.assertLess(_angle(_rotation(matrix), expected), 1e-3)
        scale = om.MTransformationMatrix(matrix).scale(om.MSpace.kWorld)
        for value in scale:
            self.assertAlmostEqual(value, 1.0, delta=1e-5)

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = cmds.listHistory(self.owner + ".matrix", pruneDagObjects=True) or []
        upstream += cmds.listHistory(self.owner + ".cageMatrix", pruneDagObjects=True) or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        shaft = cmds.createNode("transform", name="undoShaft")
        target = cmds.createNode("transform", name="undoTarget")
        cmds.setAttr(target + ".translate", 5, 1, 0)
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        ConstantVelocityJoint.create(shaft, target, name="undoJoint")
        self.assertTrue(cmds.objExists("undoJoint"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoJoint"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoJoint.cageMatrix"))

    def test_arguments(self):
        """軸の不正、transform以外・同じノード・名前の重複を拒否する。"""
        with self.assertRaises(ValueError):
            ConstantVelocityJoint.create(self.shaft, self.target, name="bad", axis="w")
        node = cmds.createNode("multiplyDivide")
        with self.assertRaises(ValueError):
            ConstantVelocityJoint.create(node, self.target, name="bad")
        with self.assertRaises(ValueError):
            ConstantVelocityJoint.create(self.shaft, self.shaft, name="bad")
        with self.assertRaises(ValueError):
            ConstantVelocityJoint.create(self.shaft, self.target, name="cv")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
