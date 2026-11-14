"""UniversalJointの出力軸の向き・曲げ角・角速度比を、OpenMayaで独立に求めた十字軸の幾何と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import UniversalJoint


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
    """2つのクォータニオンの差の回転角(度)。"""
    return math.degrees((first * second.inverse()).asAxisAngle()[1]) % 360.0


class UniversalJointTest(unittest.TestCase):
    """まっすぐ・十字軸の拘束・角度の式・角速度比・二重継手・atTarget・Python版・所有・Undo・引数を確認する。"""

    def setUp(self):
        """X軸の入力軸(ピンはY)と、XY平面で上へ曲げた出力軸の先の点を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.shaft = cmds.createNode("transform", name="inputShaft")
        cmds.setAttr(self.shaft + ".translate", 1, 2, 3)
        self.target = cmds.createNode("transform", name="outputTarget")
        self._bend(30.0)
        self.setup = UniversalJoint.create(self.shaft, self.target, name="uj")
        self.owner = str(self.setup.container)

    def _bend(self, degrees, length=5.0):
        """出力軸の先の点を、中心からXY平面で degrees だけ上へ曲げた位置へ置く。"""
        radians = math.radians(degrees)
        cmds.setAttr(self.target + ".translate", 1 + length * math.cos(radians), 2 + length * math.sin(radians), 3)

    def _outputGamma(self, beta):
        """出力のピン(Y)の角度を、出力軸に垂直な曲げ平面内の向きから測る(度)。"""
        matrix = _matrix(self.owner + ".matrix")
        pin = _row(matrix, 1)
        radians = math.radians(beta)
        inPlane = om.MVector(-math.sin(radians), math.cos(radians), 0)
        return math.degrees(math.atan2(pin * om.MVector(0, 0, 1), pin * inPlane))

    def test_straight_matches_input(self):
        """まっすぐなら出力の向きは入力軸と同じで、曲げ角0・角速度比1。"""
        self._bend(0.0)
        for spin in (0.0, 35.0, 170.0, -100.0):
            cmds.setAttr(self.shaft + ".rotateX", spin)
            with self.subTest(spin=spin):
                output = _matrix(self.owner + ".matrix")
                expected = _matrix(self.shaft + ".worldMatrix[0]")
                turn = _angle(_rotation(output), _rotation(expected))
                self.assertLess(min(turn, 360.0 - turn), 1e-3)
                self.assertLess((_position(output) - _position(expected)).length(), 1e-4)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".bendAngle"), 0.0, delta=1e-3)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".speedRatio"), 1.0, delta=1e-6)

    def test_cross_constraint(self):
        """出力軸は先の点を向き、出力ヨークのピンは入力ヨークのピンと出力軸の両方に垂直。"""
        for spin, bend in ((0.0, 30.0), (40.0, 30.0), (123.0, 55.0), (-70.0, 10.0)):
            self._bend(bend)
            cmds.setAttr(self.shaft + ".rotateX", spin)
            with self.subTest(spin=spin, bend=bend):
                matrix = _matrix(self.owner + ".matrix")
                center = _position(_matrix(self.shaft + ".worldMatrix[0]"))
                aim = (_position(_matrix(self.target + ".worldMatrix[0]")) - center).normal()
                inputPin = _row(_matrix(self.shaft + ".worldMatrix[0]"), 1)
                self.assertLess((_row(matrix, 0) - aim).length(), 1e-4)
                self.assertLess(abs(_row(matrix, 2) * inputPin), 1e-4)
                self.assertLess(abs(_row(matrix, 2) * aim), 1e-4)
                self.assertLess((_position(matrix) - center).length(), 1e-4)
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".bendAngle"), bend, delta=1e-3)

    def test_output_angle_formula(self):
        """出力ヨークの角度が tan γ2 = tan γ1 / cos β を満たす。"""
        for bend in (15.0, 30.0, 60.0):
            self._bend(bend)
            for spin in (0.0, 20.0, 45.0, 89.0, 135.0, -60.0, 179.0):
                cmds.setAttr(self.shaft + ".rotateX", spin)
                with self.subTest(bend=bend, spin=spin):
                    expected = UniversalJoint.outputAngle(spin, bend)
                    difference = (self._outputGamma(bend) - expected + 180.0) % 360.0 - 180.0
                    self.assertLess(abs(difference), 1e-3)
                    pinTwist = math.sin(math.radians(bend)) * math.sin(math.radians(spin))
                    self.assertAlmostEqual(cmds.getAttr(self.owner + ".pinTwist"), pinTwist, delta=1e-5)

    def test_speed_ratio(self):
        """speedRatioが出力角の差分の比・Python版と一致し、cos β から 1/cos β の範囲で揺れる。"""
        bend = 40.0
        self._bend(bend)
        cosine = math.cos(math.radians(bend))
        ratios = []
        for spin in range(0, 360, 15):
            cmds.setAttr(self.shaft + ".rotateX", spin)
            ratio = cmds.getAttr(self.owner + ".speedRatio")
            before = self._outputGamma(bend)
            cmds.setAttr(self.shaft + ".rotateX", spin + 0.01)
            after = self._outputGamma(bend)
            numeric = ((after - before + 180.0) % 360.0 - 180.0) / 0.01
            with self.subTest(spin=spin):
                self.assertAlmostEqual(ratio, UniversalJoint.speedRatio(spin, bend), delta=1e-5)
                self.assertAlmostEqual(ratio, numeric, delta=2e-3)
            ratios.append(ratio)
        self.assertAlmostEqual(min(ratios), cosine, delta=1e-5)
        self.assertAlmostEqual(max(ratios), 1.0 / cosine, delta=1e-5)

    def test_double_cardan_constant_velocity(self):
        """位相を揃えた2つの継手(Z配置、等しい曲げ角)では、出力が入力と同じ角度だけ回る。"""
        self._bend(30.0)
        first = UniversalJoint.create(self.shaft, self.target, name="first", atTarget=True)
        middle = cmds.createNode("transform", name="middleShaftEnd")
        cmds.connectAttr(str(first.container) + ".matrix", middle + ".offsetParentMatrix")
        end = cmds.createNode("transform", name="outputEnd")
        tip = om.MPoint(*cmds.getAttr(self.target + ".translate")[0])
        cmds.setAttr(end + ".translate", tip.x + 5.0, tip.y, tip.z)
        second = UniversalJoint.create(middle, end, name="second", pinAxis="z")
        owner = str(second.container)
        cmds.setAttr(self.shaft + ".rotateX", 0.0)
        restOutput = _rotation(_matrix(owner + ".matrix"))
        restInput = _rotation(_matrix(self.shaft + ".worldMatrix[0]"))
        for spin in (17.0, 45.0, 90.0, 133.0, -75.0):
            cmds.setAttr(self.shaft + ".rotateX", spin)
            outputTurn = _rotation(_matrix(owner + ".matrix")) * restOutput.inverse()
            inputTurn = _rotation(_matrix(self.shaft + ".worldMatrix[0]")) * restInput.inverse()
            with self.subTest(spin=spin):
                self.assertLess(min(_angle(outputTurn, inputTurn), 360.0 - _angle(outputTurn, inputTurn)), 1e-3)
                # 1つ目の継手だけでは揺れる(中間軸は入力と違う角度だけ回る。0・90度ごとの点では一致する)。
                if spin % 90.0:
                    single = self._outputGamma(30.0)
                    self.assertGreater(abs(((single - spin) + 180.0) % 360.0 - 180.0), 0.1)

    def test_at_target(self):
        """atTargetでは位置が先の点になり、向きは中心に置いた場合と同じ。"""
        setup = UniversalJoint.create(self.shaft, self.target, name="atTip", atTarget=True)
        for spin in (0.0, 70.0, -140.0):
            cmds.setAttr(self.shaft + ".rotateX", spin)
            with self.subTest(spin=spin):
                atTip = _matrix(str(setup.container) + ".matrix")
                atCenter = _matrix(self.owner + ".matrix")
                for index in range(3):
                    self.assertLess((_row(atTip, index) - _row(atCenter, index)).length(), 1e-4)
                target = _position(_matrix(self.target + ".worldMatrix[0]"))
                self.assertLess((_position(atTip) - target).length(), 1e-4)

    def test_other_axes_and_input_rotation(self):
        """axis=z・pinAxis=xと、入力軸の親の回転でも十字軸の拘束が成り立つ。"""
        parent = cmds.createNode("transform", name="shaftParent")
        cmds.setAttr(parent + ".rotate", 20, -35, 50)
        shaft = cmds.createNode("transform", name="zShaft", parent=parent)
        cmds.setAttr(shaft + ".rotateZ", 33.0)
        target = cmds.createNode("transform", name="zTarget")
        cmds.setAttr(target + ".translate", 3, -2, 6)
        setup = UniversalJoint.create(shaft, target, name="zJoint", axis="z", pinAxis="x")
        matrix = _matrix(str(setup.container) + ".matrix")
        world = _matrix(shaft + ".worldMatrix[0]")
        aim = (_position(_matrix(target + ".worldMatrix[0]")) - _position(world)).normal()
        self.assertLess((_row(matrix, 2) - aim).length(), 1e-4)
        self.assertLess(abs(_row(matrix, 1) * _row(world, 0)), 1e-4)
        bend = math.degrees(math.acos(max(-1.0, min(1.0, _row(world, 2) * aim))))
        self.assertAlmostEqual(cmds.getAttr(str(setup.container) + ".bendAngle"), bend, delta=1e-3)

    def test_python_helpers(self):
        """Python版の角度と比の端の値。"""
        self.assertAlmostEqual(UniversalJoint.outputAngle(0.0, 40.0), 0.0)
        self.assertAlmostEqual(UniversalJoint.outputAngle(90.0, 40.0), 90.0)
        self.assertAlmostEqual(UniversalJoint.outputAngle(-90.0, 40.0), -90.0)
        self.assertAlmostEqual(UniversalJoint.outputAngle(180.0, 40.0), 180.0)
        self.assertAlmostEqual(UniversalJoint.outputAngle(30.0, 0.0), 30.0)
        self.assertAlmostEqual(UniversalJoint.speedRatio(0.0, 40.0), 1.0 / math.cos(math.radians(40.0)))
        self.assertAlmostEqual(UniversalJoint.speedRatio(90.0, 40.0), math.cos(math.radians(40.0)))

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = cmds.listHistory(self.owner + ".matrix", pruneDagObjects=True) or []
        upstream += cmds.listHistory(self.owner + ".speedRatio", pruneDagObjects=True) or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        shaft = cmds.createNode("transform", name="undoShaft")
        target = cmds.createNode("transform", name="undoTarget")
        cmds.setAttr(target + ".translate", 5, 1, 0)
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        UniversalJoint.create(shaft, target, name="undoJoint")
        self.assertTrue(cmds.objExists("undoJoint"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoJoint"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoJoint.speedRatio"))

    def test_arguments(self):
        """軸の不正、transform以外・同じノード・名前の重複を拒否する。"""
        for kwargs in ({"axis": "w"}, {"pinAxis": "q"}, {"axis": "y", "pinAxis": "y"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                UniversalJoint.create(self.shaft, self.target, name="bad", **kwargs)
        node = cmds.createNode("multiplyDivide")
        with self.assertRaises(ValueError):
            UniversalJoint.create(node, self.target, name="bad")
        with self.assertRaises(ValueError):
            UniversalJoint.create(self.shaft, self.shaft, name="bad")
        with self.assertRaises(ValueError):
            UniversalJoint.create(self.shaft, self.target, name="uj")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
