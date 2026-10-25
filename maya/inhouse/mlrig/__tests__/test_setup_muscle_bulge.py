"""MuscleBulgeの曲げ角・膨らみの割合・補助骨の行列を、OpenMayaで求めた期待値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import MuscleBulge


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _relative(joint):
    """jointの親空間での行列(matrix * offsetParentMatrix)。"""
    return _matrix(joint + ".matrix") * _matrix(joint + ".offsetParentMatrix")


def _direction(joint, axis="x"):
    """親空間で見たjointの長手軸の向き。"""
    unit = om.MVector(*[float(value == axis) for value in "xyz"])
    return (unit * _relative(joint)).normal()


class MuscleBulgeTest(unittest.TestCase):
    """作成時の姿勢・曲げ角・割合・scaleと移動・ひねりの無視・変更・単位・所有・Undo・引数を確認する。"""

    def setUp(self):
        """回転した親の下に、上腕と、jointOrientと初期回転を持つ肘を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.frame = cmds.createNode("transform", name="frame")
        cmds.setAttr(self.frame + ".rotate", 10, 25, -5)
        cmds.setAttr(self.frame + ".translate", 3, 4, 5)
        self.upper = cmds.createNode("joint", name="upperArm", parent=self.frame)
        cmds.setAttr(self.upper + ".rotate", 5, -10, 20)
        self.elbow = cmds.createNode("joint", name="elbow", parent=self.upper)
        cmds.setAttr(self.elbow + ".translate", 12, 0.5, -0.2)
        cmds.setAttr(self.elbow + ".jointOrient", 0, 0, 15)
        cmds.setAttr(self.elbow + ".rotate", 0, 5, 10)
        self.rest_direction = _direction(self.elbow)

    def build(self, **kwargs):
        """セットアップと、matrixをoffsetParentMatrixで受ける補助骨を上腕の下に作る。"""
        owner = str(MuscleBulge.create(self.upper, self.elbow, **kwargs).container)
        helper = cmds.createNode("joint", name="helper", parent=self.upper)
        cmds.connectAttr(owner + ".matrix", helper + ".offsetParentMatrix")
        return owner, helper

    def expected(self, owner, axis="x", pushAxis="y"):
        """現在の姿勢とcontainerの値から、曲げ角・割合・parent空間の行列を独立に計算する。"""
        get = lambda attr: cmds.getAttr(owner + "." + attr)
        angle = math.degrees(self.rest_direction.angle(_direction(self.elbow, axis)))
        start, full = get("startAngle"), get("fullAngle")
        t = min(max((angle - start) / (full - start), 0.0), 1.0)
        weight = t * t * (3 - 2 * t)
        scale = 1 + get("bulge") * weight
        location = om.MVector(*[_relative(self.elbow)[12 + index] for index in range(3)])
        sign = -1.0 if pushAxis.startswith("-") else 1.0
        push = om.MVector(*[sign * float(value == pushAxis[-1]) for value in "xyz"])
        translate = location * get("position") + push * (get("push") * weight)
        values = [0.0] * 16
        for index, value in enumerate("xyz"):
            values[index * 5] = 1.0 if value == axis else scale
        values[12:15] = list(translate)
        values[15] = 1.0
        return angle, weight, om.MMatrix(values)

    def check(self, owner, helper, axis="x", pushAxis="y"):
        """出力の曲げ角・割合・scale・offset・行列・補助骨のワールド行列が期待値と一致するか確認する。"""
        angle, weight, local = self.expected(owner, axis, pushAxis)
        self.assertAlmostEqual(cmds.getAttr(owner + ".bendAngle"), angle, places=3)
        self.assertAlmostEqual(cmds.getAttr(owner + ".weight"), weight, places=5)
        self.assertAlmostEqual(cmds.getAttr(owner + ".scale"),
                               1 + cmds.getAttr(owner + ".bulge") * weight, places=5)
        self.assertAlmostEqual(cmds.getAttr(owner + ".offset"),
                               cmds.getAttr(owner + ".push") * weight, places=5)
        self.assertTrue(_matrix(owner + ".matrix").isEquivalent(local, 1e-4))
        world = local * _matrix(self.upper + ".worldMatrix[0]")
        self.assertTrue(_matrix(owner + ".worldMatrix").isEquivalent(world, 1e-4))
        self.assertTrue(_matrix(helper + ".worldMatrix[0]").isEquivalent(world, 1e-4))
        return angle, weight

    def test_response_formula(self):
        """responseは開始前0・中央0.5・最大以降1のsmoothstep。"""
        self.assertEqual(MuscleBulge.response(10, 45, 135), 0.0)
        self.assertAlmostEqual(MuscleBulge.response(90, 45, 135), 0.5)
        self.assertAlmostEqual(MuscleBulge.response(67.5, 45, 135), 0.15625)
        self.assertEqual(MuscleBulge.response(170, 45, 135), 1.0)

    def test_rest_pose_does_not_jump(self):
        """生成直後は曲げ角0・割合0で、補助骨は上腕の向きのまま肘までの中央に置かれる。"""
        owner, helper = self.build()
        angle, weight = self.check(owner, helper)
        self.assertAlmostEqual(angle, 0.0, places=4)
        self.assertEqual(weight, 0.0)
        location = [_relative(self.elbow)[12 + index] * 0.5 for index in range(3)]
        self.assertTrue(_matrix(owner + ".matrix").isEquivalent(
            om.MMatrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0] + location + [1]), 1e-5))

    def test_bend_drives_bulge(self):
        """肘を各方向へ曲げると、開始角までは膨らまず、途中は急に、最大角以降は一定になる。"""
        owner, helper = self.build()
        weights = []
        for rotate in ((0, 5, 40), (0, 5, 60), (0, 5, 100), (0, 5, 145), (0, 5, 175),
                       (30, -60, 20), (0, -70, 0), (45, 20, -110), (0, 5, 10)):
            cmds.setAttr(self.elbow + ".rotate", *rotate)
            weights.append(self.check(owner, helper)[1])
        self.assertEqual(weights[0], 0.0)
        self.assertGreater(weights[2], weights[1])
        self.assertAlmostEqual(weights[4], 1.0, places=6)
        self.assertAlmostEqual(weights[-1], 0.0, places=6)
        # 曲げる向きによらず、曲げの大きさで膨らむ。
        self.assertGreater(weights[7], 0.0)

    def test_twist_does_not_bulge(self):
        """肘の長手軸回りのひねりだけでは、曲げ角も割合も0のまま。"""
        owner, helper = self.build()
        for twist in (45, 120, -170):
            cmds.setAttr(self.elbow + ".rotate", twist, 5, 10)
            angle, weight = self.check(owner, helper)
            self.assertAlmostEqual(angle, 0.0, places=3)
            self.assertEqual(weight, 0.0)

    def test_attributes_and_length_are_live(self):
        """角度・量・位置の変更と、肘の位置(骨の長さ)の変更が出力へすぐ反映される。"""
        owner, helper = self.build(axis="x", pushAxis="-z")
        cmds.setAttr(self.elbow + ".rotate", 0, 5, 95)
        self.check(owner, helper, pushAxis="-z")
        for attr, value in (("startAngle", 20), ("fullAngle", 80), ("bulge", 0.8), ("push", 2.5),
                            ("position", 0.25)):
            cmds.setAttr(owner + "." + attr, value)
            self.check(owner, helper, pushAxis="-z")
        cmds.setAttr(self.elbow + ".translate", 20, 1, 0)
        self.check(owner, helper, pushAxis="-z")
        self.assertAlmostEqual(_matrix(owner + ".matrix")[14], -2.5, places=4)

    def test_other_axis(self):
        """長手軸をyにすると、yの傾きを曲げ角とし、x・zを膨らませる。"""
        owner, helper = self.build(axis="y", pushAxis="x", name="yAxis")
        rest = _direction(self.elbow, "y")
        self.rest_direction = rest
        for rotate in ((80, 5, 10), (0, 5, 10), (0, 90, 10)):
            cmds.setAttr(self.elbow + ".rotate", *rotate)
            self.check(owner, helper, axis="y", pushAxis="x")

    def test_ui_units(self):
        """UIの角度単位がradianでも、角度の入出力は度のまま。"""
        owner, helper = self.build()
        cmds.setAttr(self.elbow + ".rotate", 0, 5, 100)
        expected = cmds.getAttr(owner + ".bendAngle")
        cmds.currentUnit(angle="rad")
        try:
            self.assertAlmostEqual(cmds.getAttr(owner + ".bendAngle"), expected, places=4)
            self.assertAlmostEqual(cmds.getAttr(owner + ".startAngle"), 45.0, places=6)
        finally:
            cmds.currentUnit(angle="deg")
        self.check(owner, helper)

    def test_owned_and_undo(self):
        """演算ノードはcontainerが所有し、生成を1回のUndoで取り消し、Redoで戻せる。"""
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        before = set(cmds.ls())
        owner = str(MuscleBulge.create(self.upper, self.elbow, name="undoBulge").container)
        members = set(cmds.container(owner, query=True, nodeList=True) or [])
        created = set(cmds.ls()) - before - {owner}
        created = {node for node in created if cmds.nodeType(node) != "hyperLayout"}
        self.assertEqual({cmds.ls(node)[0] for node in members if cmds.nodeType(node) != "hyperLayout"},
                         created)
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoBulge"))

    def test_invalid_arguments(self):
        """範囲外の値・軸・親子でない組・同じ位置・既存の名前を拒否する。"""
        for kwargs in ({"axis": "w"}, {"pushAxis": "+y"}, {"position": 1.5}, {"startAngle": 90, "fullAngle": 90},
                       {"fullAngle": 200}, {"startAngle": -1}, {"bulge": float("nan")}):
            with self.assertRaises(ValueError):
                MuscleBulge.create(self.upper, self.elbow, **kwargs)
        with self.assertRaises(ValueError):
            MuscleBulge.create(self.frame, self.elbow)
        same = cmds.createNode("joint", name="samePlace", parent=self.upper)
        with self.assertRaises(ValueError):
            MuscleBulge.create(self.upper, same)
        MuscleBulge.create(self.upper, self.elbow, name="taken")
        with self.assertRaises(ValueError):
            MuscleBulge.create(self.upper, self.elbow, name="taken")


if __name__ == "__main__":
    unittest.main()
