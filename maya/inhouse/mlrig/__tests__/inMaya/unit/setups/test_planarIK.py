"""途中にずれた骨がある脚で、PlanarIKのIK用チェーンと元のjointの追従を確かめる。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import PlanarIK

MOVES = [(0.0, 2.0, 2.0), (2.0, 3.0, 1.0), (-1.5, 3.0, 1.0), (1.0, 4.0, -2.0), (-2.0, 2.0, -1.0)]


def _position(node):
    return om.MVector(cmds.xform(node, query=True, worldSpace=True, translation=True))


def _matrix(node):
    return om.MMatrix(cmds.xform(node, query=True, worldSpace=True, matrix=True))


def _rotation(node):
    return om.MTransformationMatrix(_matrix(node)).rotation(asQuaternion=True)


class PlanarIKTest(unittest.TestCase):
    """作成時の姿勢・元のjointの位置一致・膝の1軸回転・引数検査・Undoを確認する。"""

    def setUp(self):
        """付け根→ずれた骨→膝→ずれた骨→足首の脚を、向きがばらばらのjointで作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.pelvis = cmds.createNode("transform", name="pelvis")
        cmds.setAttr(self.pelvis + ".rotate", -4, 20, 6)
        cmds.select(self.pelvis)
        self.hip = cmds.joint(name="hip", position=(0, 10, 0))
        self.thighOffset = cmds.joint(name="thighOffset", position=(2.0, 8.0, 0.5))
        self.knee = cmds.joint(name="knee", position=(1.2, 5.0, 1.0))
        self.shinOffset = cmds.joint(name="shinOffset", position=(1.8, 2.5, 1.5))
        self.ankle = cmds.joint(name="ankle", position=(0.0, 0.0, 0.5))
        for joint, orient in zip((self.hip, self.thighOffset, self.knee, self.shinOffset, self.ankle),
                                 ((10, 30, -20), (0, 0, 45), (-15, 5, 60), (30, -10, 0), (0, 90, 0))):
            cmds.xform(joint, worldSpace=True, translation=cmds.xform(joint, query=True, worldSpace=True,
                                                                       translation=True))
            cmds.setAttr(joint + ".jointOrient", *orient)
        self.chain = (self.hip, self.thighOffset, self.knee, self.shinOffset, self.ankle)
        self.normal = ((_position(self.knee) - _position(self.hip)) ^
                       (_position(self.ankle) - _position(self.knee))).normal()

    def test_no_pop_on_create(self):
        """作成の前後で、元のjointの行列が変わらない。"""
        before = {node: _matrix(node) for node in self.chain}
        PlanarIK.create(self.hip, self.knee, self.ankle, name="legIK")
        for node, matrix in before.items():
            self.assertTrue(_matrix(node).isEquivalent(matrix, 1e-4), node)

    def test_follow_and_one_axis(self):
        """足首を動かすと元の足首が届き、膝の曲がりはIK用チェーンの法線まわりの1軸。"""
        ik = PlanarIK.create(self.hip, self.knee, self.ankle, name="legIK")
        rest_root, rest_mid = _rotation(self.hip), _rotation(self.knee)
        rest = cmds.getAttr(ik.handle + ".translate")[0]
        for move in MOVES:
            cmds.setAttr(ik.handle + ".translate", *[r + m for r, m in zip(rest, move)])
            self.assertLess((_position(self.ankle) - _position(ik.handle)).length(), 1e-3)
            for bind, driver in zip((self.hip, self.knee, self.ankle), ik.drivers):
                self.assertLess((_position(bind) - _position(driver)).length(), 1e-4, bind)
            rotate = cmds.getAttr(ik.drivers[1] + ".rotate")[0]
            self.assertAlmostEqual(rotate[0], 0.0, places=4)
            self.assertAlmostEqual(rotate[1], 0.0, places=4)
            # 生成時からの回転の変化(ワールド): 膝の変化 = 曲げ * 付け根の変化(q1*q2 は q1 を先に適用)。
            # 曲げの軸は生成時の平面の法線と平行になる。
            hip_delta = rest_root.inverse() * _rotation(self.hip)
            knee_delta = rest_mid.inverse() * _rotation(self.knee)
            bend = knee_delta * hip_delta.inverse()
            axis, angle = bend.asAxisAngle()
            if abs(angle) > 1e-3:
                self.assertAlmostEqual(abs(axis.normal() * self.normal), 1.0, places=4)

    def test_offset_bones_keep_length(self):
        """途中のずれた骨の長さ(ローカルの移動)は変わらない。"""
        ik = PlanarIK.create(self.hip, self.knee, self.ankle, name="legIK")
        lengths = [cmds.getAttr(node + ".translate")[0] for node in self.chain[1:]]
        cmds.setAttr(ik.handle + ".translate", 1, 2, 3)
        self.assertEqual([cmds.getAttr(node + ".translate")[0] for node in self.chain[1:]], lengths)

    def test_drivers_are_planar(self):
        """IK用のjointは一平面上にあり、膝のローカルZは平面の法線。"""
        ik = PlanarIK.create(self.hip, self.knee, self.ankle, name="legIK")
        z = (om.MVector(0, 0, 1) * _matrix(ik.drivers[1])).normal()
        self.assertAlmostEqual(z * self.normal, 1.0, places=5)
        self.assertEqual(cmds.joint(ik.drivers[1], query=True, degreeOfFreedom=True), "z")
        self.assertFalse(cmds.getAttr(ik.drivers[0] + ".visibility"))

    def test_drivers_follow_parent(self):
        """IK用のjointは元の付け根の親の子で、骨盤を動かすと付いていく。"""
        ik = PlanarIK.create(self.hip, self.knee, self.ankle, name="legIK")
        cmds.setAttr(self.pelvis + ".translateX", 5)
        self.assertLess((_position(self.hip) - _position(ik.drivers[0])).length(), 1e-4)

    def test_arguments(self):
        """親子関係と一直線のチェーンを検査する。"""
        with self.assertRaises(ValueError):
            PlanarIK.create(self.knee, self.hip, self.ankle)
        cmds.select(clear=True)
        straight = [cmds.joint(position=(0, y, 0)) for y in (10, 5, 0)]
        with self.assertRaises(ValueError):
            PlanarIK.create(*straight)

    def test_undo(self):
        """1回のUndoで、生成物とコンストレイントが消え、元のjointは元のまま。"""
        nodes = set(cmds.ls())
        before = {node: _matrix(node) for node in self.chain}
        PlanarIK.create(self.hip, self.knee, self.ankle, name="legIK")
        cmds.undo()
        # IKを初めて使ったときにMayaが作る共通のソルバーノードは除く。
        solvers = set(cmds.ls(type=("ikSolver", "hikSolver")) or [])
        self.assertEqual(set(cmds.ls()) - nodes - solvers, set())
        for node, matrix in before.items():
            self.assertTrue(_matrix(node).isEquivalent(matrix, 1e-4), node)


if __name__ == "__main__":
    unittest.main()
