"""膝が横にずれた脚で、HingeIKの膝が1軸だけで曲がることを確かめる。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import HingeIK

#: 足首(ikHandle)を動かす量。どれも届く範囲。
MOVES = [(0.0, 2.0, 2.0), (2.0, 3.0, 1.0), (-1.5, 3.0, 1.0), (1.0, 4.0, -2.0), (-2.0, 2.0, -1.0)]


def _position(node):
    return om.MVector(cmds.xform(node, query=True, worldSpace=True, translation=True))


def _matrix(node):
    return om.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))


def _localAxis(node, axis):
    """jointのローカル軸のワールドの向き。"""
    unit = om.MVector(*[float(axis == name) for name in "xyz"])
    return (unit * _matrix(node)).normal()


def _rotateAbout(vector, axis, degrees):
    return vector.rotateBy(om.MQuaternion(math.radians(degrees), om.MVector(axis).normal()))


class HingeIKTest(unittest.TestCase):
    """作成時の姿勢・膝の1軸回転・足首の到達・ヒンジ軸の指定・引数検査・Undoを確認する。"""

    def setUp(self):
        """付け根・膝・足首が一平面に並ばない(膝が横にずれた)脚を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.pelvis = cmds.createNode("transform", name="pelvis")
        cmds.setAttr(self.pelvis + ".rotate", 5, 15, -3)
        cmds.select(self.pelvis)
        self.hip = cmds.joint(name="hip", position=(0, 10, 0))
        self.knee = cmds.joint(name="knee", position=(1.2, 5, 1.0))
        self.ankle = cmds.joint(name="ankle", position=(0, 0, 0.5))
        cmds.joint(self.hip, edit=True, orientJoint="xyz", secondaryAxisOrient="zup", children=True,
                   zeroScaleOrient=True)

    def _reach(self, handle):
        return (_position(self.ankle) - _position(handle)).length()

    def _checkPoses(self, ik, other_axes):
        rest = cmds.getAttr(ik.handle + ".translate")[0]
        for move in MOVES:
            cmds.setAttr(ik.handle + ".translate", *[r + m for r, m in zip(rest, move)])
            rotate = cmds.getAttr(self.knee + ".rotate")[0]
            for axis in other_axes:
                self.assertAlmostEqual(rotate["xyz".index(axis)], 0.0, places=4, msg="knee rotates on " + axis)
            self.assertLess(self._reach(ik.handle), 1e-3)
        cmds.setAttr(ik.handle + ".translate", *rest)

    def test_no_pop_on_create(self):
        """作成の前後で、付け根・足首の行列と膝の位置が変わらない。"""
        before = {node: _matrix(node) for node in (self.hip, self.ankle)}
        knee = _position(self.knee)
        HingeIK.create(self.hip, self.knee, self.ankle, name="legIK")
        for node, matrix in before.items():
            self.assertTrue(_matrix(node).isEquivalent(matrix, 1e-4), node)
        self.assertLess((_position(self.knee) - knee).length(), 1e-5)

    def test_knee_bends_on_one_axis(self):
        """足首を動かしても膝はZだけで回り、足首は目標に届く。"""
        ik = HingeIK.create(self.hip, self.knee, self.ankle, name="legIK")
        self.assertEqual(cmds.joint(self.knee, query=True, degreeOfFreedom=True), "z")
        self._checkPoses(ik, "xy")

    def test_hinge_axis_matches_plane_normal_by_default(self):
        """ヒンジ軸を省略すると3点の平面の法線になり、膝のローカルZと一致する。"""
        normal = ((_position(self.knee) - _position(self.hip)) ^ (_position(self.ankle) - _position(self.knee))).normal()
        ik = HingeIK.create(self.hip, self.knee, self.ankle, name="legIK")
        self.assertAlmostEqual(ik.hinge * normal, 1.0, places=6)
        self.assertAlmostEqual(_localAxis(self.knee, "z") * normal, 1.0, places=5)

    def test_explicit_tilted_hinge(self):
        """平面の法線から傾けたヒンジ軸を渡すと、膝はその軸だけで回る。"""
        thigh = _position(self.knee) - _position(self.hip)
        normal = (thigh ^ (_position(self.ankle) - _position(self.knee))).normal()
        hinge = _rotateAbout(normal, thigh, 25.0)
        ik = HingeIK.create(self.hip, self.knee, self.ankle, name="legIK", hinge=hinge)
        self.assertAlmostEqual(_localAxis(self.knee, "z") * hinge.normal(), 1.0, places=5)
        self._checkPoses(ik, "xy")

    def test_y_axis(self):
        """axis="y" ならローカルYがヒンジ軸になり、膝はYだけで回る。"""
        ik = HingeIK.create(self.hip, self.knee, self.ankle, name="legIK", axis="y")
        self.assertAlmostEqual(_localAxis(self.knee, "y") * ik.hinge, 1.0, places=5)
        self._checkPoses(ik, "xz")

    def test_pole_vector_keeps_one_axis(self):
        """ポールベクターを動かしても膝は1軸のまま、足首は届く。"""
        ik = HingeIK.create(self.hip, self.knee, self.ankle, name="legIK")
        cmds.setAttr(ik.handle + ".translateZ", cmds.getAttr(ik.handle + ".translateZ") + 2)
        hip_rotation = cmds.getAttr(self.hip + ".rotate")[0]
        for position in ((6, 5, 2), (-4, 5, 5), (3, 5, 8)):
            cmds.xform(ik.pole, worldSpace=True, translation=position)
            rotate = cmds.getAttr(self.knee + ".rotate")[0]
            self.assertAlmostEqual(rotate[0], 0.0, places=4)
            self.assertAlmostEqual(rotate[1], 0.0, places=4)
            self.assertLess(self._reach(ik.handle), 1e-3)
        self.assertNotEqual(cmds.getAttr(self.hip + ".rotate")[0], hip_rotation)

    def test_arguments(self):
        """軸・親子関係・一直線のチェーンを検査する。"""
        with self.assertRaises(ValueError):
            HingeIK.create(self.hip, self.knee, self.ankle, axis="x")
        with self.assertRaises(ValueError):
            HingeIK.create(self.hip, self.ankle, self.knee)
        cmds.select(clear=True)
        straight = [cmds.joint(position=(0, y, 0)) for y in (10, 5, 0)]
        with self.assertRaises(ValueError):
            HingeIK.create(*straight)

    def test_undo(self):
        """1回のUndoで、膝のjointOrient・自由度と生成物が元に戻る。"""
        orient = cmds.getAttr(self.knee + ".jointOrient")[0]
        nodes = set(cmds.ls())
        HingeIK.create(self.hip, self.knee, self.ankle, name="legIK")
        cmds.undo()
        # IKを初めて使ったときにMayaが作る共通のソルバーノードは除く。
        solvers = set(cmds.ls(type=("ikSolver", "hikSolver")) or [])
        self.assertEqual(set(cmds.ls()) - nodes - solvers, set())
        for value, expected in zip(cmds.getAttr(self.knee + ".jointOrient")[0], orient):
            self.assertAlmostEqual(value, expected, places=5)
        self.assertEqual(cmds.joint(self.knee, query=True, degreeOfFreedom=True), "xyz")


if __name__ == "__main__":
    unittest.main()
