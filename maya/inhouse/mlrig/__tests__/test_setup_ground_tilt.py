"""GroundTiltの足の面の向き・胴体の傾きと上下を、OpenMayaで求めた期待値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import GroundTilt

FEET = (("frontLeft", (3, 0, 1.5)), ("frontRight", (3, 0, -1.5)),
        ("backLeft", (-3, 0, 1.5)), ("backRight", (-3, 0, -1.5)))


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _position(node):
    """ワールド位置をMVectorで返す。"""
    return om.MVector(cmds.xform(node, query=True, worldSpace=True, translation=True))


def _translation(vector):
    """位置だけの行列。"""
    return om.MMatrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, vector[0], vector[1], vector[2], 1])


def _plane(points):
    """足の位置から、(面の向きの回転行列, 中心, 前後の向き, 左右の向き)を独立に計算する。"""
    front, back = (points[0] + points[1]) * 0.5, (points[2] + points[3]) * 0.5
    left, right = (points[0] + points[2]) * 0.5, (points[1] + points[3]) * 0.5
    center = (points[0] + points[1] + points[2] + points[3]) * 0.25
    x = (front - center).normal()
    z = (left - center) - x * ((left - center) * x)
    z.normalize()
    y = z ^ x
    rotation = om.MMatrix([x[0], x[1], x[2], 0, y[0], y[1], y[2], 0, z[0], z[1], z[2], 0, 0, 0, 0, 1])
    return rotation, center, (front - back).normal(), (left - right).normal()


class GroundTiltTest(unittest.TestCase):
    """作成時の姿勢・前後左右の傾き・平行移動・割合・胴体の動き・確認用の角度・所有・Undo・引数を確認する。"""

    def setUp(self):
        """回転した親の下の胴体と、地面の4本の足の接地点を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.root = cmds.createNode("transform", name="root")
        cmds.setAttr(self.root + ".rotateY", 30)
        self.body = cmds.createNode("transform", name="body", parent=self.root)
        cmds.setAttr(self.body + ".translate", 0.5, 5, 0.2)
        cmds.setAttr(self.body + ".rotate", 5, 0, -3)
        self.feet = []
        for name, position in FEET:
            foot = cmds.createNode("transform", name=name, parent=self.root)
            cmds.setAttr(foot + ".translate", *position)
            self.feet.append(foot)
        self.rest = _plane([_position(foot) for foot in self.feet])

    def build(self, **kwargs):
        """セットアップと、matrixをoffsetParentMatrixで受ける結果transformをワールドに作る。"""
        owner = str(GroundTilt.create(self.body, *self.feet, **kwargs).container)
        result = cmds.createNode("transform", name="result")
        cmds.connectAttr(owner + ".matrix", result + ".offsetParentMatrix")
        return owner, result

    def expected(self, owner):
        """現在の足と胴体から、補正後の胴体のワールド行列・lift・pitch・rollを独立に計算する。"""
        rotation, center, _, _ = _plane([_position(foot) for foot in self.feet])
        rest_rotation, rest_center, forward, side = self.rest
        delta = rest_rotation.inverse() * rotation
        tilt = cmds.getAttr(owner + ".tilt")
        quaternion = om.MQuaternion.slerp(om.MQuaternion(), om.MTransformationMatrix(delta).rotation(True), tilt)
        lift = cmds.getAttr(owner + ".height") * (center.y - rest_center.y)
        body = _matrix(self.body + ".worldMatrix[0]")
        position = om.MVector(body[12], body[13], body[14])
        matrix = (body * _translation(-position) * quaternion.asMatrix() * _translation(position)
                  * _translation(om.MVector(0, lift, 0)))
        angles = []
        for direction in (forward, side):
            turned = (direction * delta).normal()
            angles.append(math.degrees(math.asin(turned.y)) - math.degrees(math.asin(direction.y)))
        return matrix, lift, angles

    def check(self, owner, result):
        """出力の行列・lift・pitch・rollと、結果transformのワールド行列を確認する。"""
        matrix, lift, angles = self.expected(owner)
        self.assertTrue(_matrix(owner + ".matrix").isEquivalent(matrix, 1e-4))
        self.assertTrue(_matrix(result + ".worldMatrix[0]").isEquivalent(matrix, 1e-4))
        self.assertAlmostEqual(cmds.getAttr(owner + ".lift"), lift, places=4)
        self.assertAlmostEqual(cmds.getAttr(owner + ".pitch"), angles[0], places=3)
        self.assertAlmostEqual(cmds.getAttr(owner + ".roll"), angles[1], places=3)
        return angles

    def test_rest_pose_does_not_jump(self):
        """生成直後の出力は胴体の入力と同じワールド行列で、角度とliftは0。"""
        owner, result = self.build()
        self.assertTrue(_matrix(owner + ".matrix").isEquivalent(_matrix(self.body + ".worldMatrix[0]"), 1e-5))
        for attr in ("pitch", "roll", "lift"):
            self.assertAlmostEqual(cmds.getAttr(owner + "." + attr), 0.0, places=5)
        self.check(owner, result)

    def test_front_and_side_tilt(self):
        """前足を上げると胴体の前が上がり、左足を上げると左が上がる。"""
        owner, result = self.build()
        for foot in self.feet[:2]:
            cmds.setAttr(foot + ".translateY", 1.5)
        pitch, roll = self.check(owner, result)
        self.assertGreater(pitch, 10.0)
        self.assertAlmostEqual(roll, 0.0, places=3)
        for foot in self.feet:
            cmds.setAttr(foot + ".translateY", 0)
        for foot in (self.feet[0], self.feet[2]):
            cmds.setAttr(foot + ".translateY", 1.0)
        pitch, roll = self.check(owner, result)
        self.assertGreater(roll, 10.0)
        self.assertAlmostEqual(pitch, 0.0, places=3)

    def test_uneven_ground_and_ratios(self):
        """凸凹な地面・足の水平移動・tiltとheightの割合・胴体の移動と回転で期待値と一致する。"""
        owner, result = self.build()
        for foot, y in zip(self.feet, (1.2, -0.4, 0.3, 2.0)):
            cmds.setAttr(foot + ".translateY", y)
        self.check(owner, result)
        cmds.setAttr(self.feet[0] + ".translateX", 4.5)
        cmds.setAttr(self.feet[3] + ".translateZ", -2.5)
        self.check(owner, result)
        cmds.setAttr(owner + ".tilt", 0.5)
        cmds.setAttr(owner + ".height", 0.25)
        self.check(owner, result)
        cmds.setAttr(self.body + ".translate", 2, 6, -1)
        cmds.setAttr(self.body + ".rotate", 0, 40, 10)
        self.check(owner, result)
        cmds.setAttr(owner + ".tilt", 0.0)
        cmds.setAttr(owner + ".height", 0.0)
        self.assertTrue(_matrix(owner + ".matrix").isEquivalent(_matrix(self.body + ".worldMatrix[0]"), 1e-5))

    def test_flat_move_only_lifts(self):
        """4本の足が平らなまま一緒に上下・水平移動しても回転せず、liftだけ変わる。"""
        owner, result = self.build()
        for foot, (_, position) in zip(self.feet, FEET):
            cmds.setAttr(foot + ".translate", position[0] + 3, 2.0, position[2] - 1)
        self.check(owner, result)
        body = _matrix(self.body + ".worldMatrix[0]")
        self.assertTrue(_matrix(owner + ".matrix").isEquivalent(body * _translation(om.MVector(0, 2.0, 0)), 1e-5))

    def test_owned_and_undo(self):
        """演算ノードはcontainerが所有し、生成を1回のUndoで取り消し、Redoで戻せる。"""
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        before = set(cmds.ls())
        owner = str(GroundTilt.create(self.body, *self.feet, name="undoTilt").container)
        members = {node for node in cmds.container(owner, query=True, nodeList=True) or []
                   if cmds.nodeType(node) != "hyperLayout"}
        created = {node for node in set(cmds.ls()) - before - {owner} if cmds.nodeType(node) != "hyperLayout"}
        self.assertEqual({cmds.ls(node)[0] for node in members}, created)
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoTilt"))

    def test_invalid_arguments(self):
        """同じtransform・重なる中点・平行な向き・有限でない割合・既存の名前を拒否する。"""
        with self.assertRaises(ValueError):
            GroundTilt.create(self.body, self.feet[0], self.feet[0], self.feet[2], self.feet[3])
        with self.assertRaises(ValueError):
            GroundTilt.create(self.body, *self.feet, tilt=float("nan"))
        line = []
        for index in range(4):
            node = cmds.createNode("transform", name="line{}".format(index))
            cmds.setAttr(node + ".translateX", index)
            line.append(node)
        with self.assertRaises(ValueError):
            GroundTilt.create(self.body, *line)
        GroundTilt.create(self.body, *self.feet, name="taken")
        with self.assertRaises(ValueError):
            GroundTilt.create(self.body, *self.feet, name="taken")


if __name__ == "__main__":
    unittest.main()
