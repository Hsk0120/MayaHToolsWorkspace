"""Pistonの両端の相互エイム・上方向・伸縮量・ストローク超過を、OpenMayaで求めた期待値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import Piston


def _world(node):
    """ワールド行列。"""
    return om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _position(matrix):
    """行列の位置をMVectorで返す。"""
    return om.MVector(matrix[12], matrix[13], matrix[14])


def _rotation(matrix):
    """行列の回転だけをMMatrixで返す。"""
    return om.MTransformationMatrix(om.MMatrix(matrix)).rotation(asQuaternion=True).asMatrix()


class PistonTest(unittest.TestCase):
    """標準ノードの数値評価・作成時の姿勢・相互エイム・同一平面・距離出力・引数検査を確認する。"""

    def setUp(self):
        """回転した親の下に、別々の親を持つシリンダーとロッドの取付け位置を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.frame = cmds.createNode("transform", name="frame")
        cmds.setAttr(self.frame + ".rotate", 10, 25, -5)
        cmds.setAttr(self.frame + ".translate", 3, 4, 5)
        self.arm = cmds.createNode("transform", name="arm", parent=self.frame)
        cmds.setAttr(self.arm + ".translate", 12, 3, 0)
        self.base = cmds.createNode("joint", name="cylinder", parent=self.frame)
        cmds.setAttr(self.base + ".translate", 0, 1, 0)
        # 部品の軸は両端を結ぶ線と一致させない(生成時の差を保つことの確認)。
        cmds.setAttr(self.base + ".rotate", 0, 0, 20)
        self.tip = cmds.createNode("joint", name="rod", parent=self.arm)
        cmds.setAttr(self.tip + ".translate", 1, 0, 0.5)
        cmds.setAttr(self.tip + ".rotate", 15, 0, 160)

    def build(self, **kwargs):
        """セットアップと、出力をoffsetParentMatrixで受ける結果transformを各端の親の下に作る。"""
        owner = Piston.create(self.base, self.tip, **kwargs).container
        results = []
        for role, parent in (("base", self.frame), ("tip", self.arm)):
            result = cmds.createNode("transform", name="result_" + role, parent=parent)
            cmds.connectAttr(str(owner) + "." + role + "Matrix", result + ".offsetParentMatrix")
            results.append(result)
        return owner, results

    def restState(self):
        """生成時の両端のワールド行列と、各端のローカル軸で見た相手の向き。"""
        base, tip = _world(self.base), _world(self.tip)
        direction = (_position(tip) - _position(base)).normal()
        return {
            "base": (base, direction * _rotation(base).inverse()),
            "tip": (tip, (-direction) * _rotation(tip).inverse()),
        }

    def check(self, owner, results, rest, minimum, maximum, up=None):
        """出力の位置・相手への向き・上方向の平面・距離の出力を確認する。"""
        base, tip = _world(self.base), _world(self.tip)
        direction = (_position(tip) - _position(base)).normal()
        outputs = {"base": _world(results[0]), "tip": _world(results[1])}
        for role, node, target in (("base", base, direction), ("tip", tip, -direction)):
            actual = outputs[role]
            # 位置は入力の現在位置のまま。
            self.assertTrue(_position(actual).isEquivalent(_position(node), 1e-4))
            # 生成時に相手を向いていたローカルの向きが、現在も相手を向く。
            local_direction = rest[role][1]
            self.assertTrue((local_direction * _rotation(actual)).isEquivalent(target, 1e-4), role)
        if up is not None:
            # 両端の出力のup方向は、両端を結ぶ線と共通の上方向が張る平面に乗る(ねじれない)。
            normal = (direction ^ up).normal()
            for role in ("base", "tip"):
                rest_up = rest[role][2]
                self.assertAlmostEqual((rest_up * _rotation(outputs[role])) * normal, 0.0, places=4)
        length = (_position(tip) - _position(base)).length()
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".length"), length, places=4)
        rest_length = cmds.getAttr(str(owner) + ".restLength")
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".extension"), length - rest_length, places=4)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".overStroke"),
                               Piston.overStroke(length, minimum, maximum), places=4)
        return length

    def test_rest_pose_does_not_jump(self):
        """生成直後の出力は、各端の入力と同じワールド行列になる。"""
        owner, results = self.build()
        self.assertTrue(_world(results[0]).isEquivalent(_world(self.base), 1e-4))
        self.assertTrue(_world(results[1]).isEquivalent(_world(self.tip), 1e-4))
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".extension"), 0.0, places=5)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".overStroke"), 0.0, places=5)

    def test_parts_keep_facing_each_other(self):
        """相手側の親を回転・移動しても、両端が互いを向き、位置は入力のまま。"""
        rest = self.restState()
        owner, results = self.build()
        rest_length = cmds.getAttr(str(owner) + ".restLength")
        for rotate, translate in (((0, 0, 30), (12, 3, 0)), ((0, 0, -25), (14, 1, 0)),
                                  ((0, 0, 60), (8, 5, 0)), ((0, 0, 0), (12, 3, 0))):
            cmds.setAttr(self.arm + ".rotate", *rotate)
            cmds.setAttr(self.arm + ".translate", *translate)
            self.check(owner, results, rest, rest_length * 0.5, rest_length * 1.5)
        self.assertTrue(_world(results[0]).isEquivalent(_world(self.base), 1e-4))

    def test_coplanar_up(self):
        """両端を結ぶ線が平面内で動くとき、両端のup軸はその平面の法線と直交したままになる。"""
        owner, results = self.build()
        base_up = om.MVector(0, 1, 0) * _rotation(_world(self.base))
        tip_up_local = base_up * _rotation(_world(self.tip)).inverse()
        rest = self.restState()
        rest["base"] = rest["base"] + (om.MVector(0, 1, 0),)
        rest["tip"] = rest["tip"] + (tip_up_local,)
        up = base_up
        rest_length = cmds.getAttr(str(owner) + ".restLength")
        for rotate in ((0, 0, 20), (0, 0, -40), (0, 30, 10)):
            cmds.setAttr(self.arm + ".rotate", *rotate)
            self.check(owner, results, rest, rest_length * 0.5, rest_length * 1.5, up=up)

    def test_stroke_outputs(self):
        """距離がminimum・maximumを越えた量を、正負の符号付きで出力する。"""
        owner, results = self.build(minimum=8.0, maximum=14.0)
        rest = self.restState()
        values = []
        for translate in ((12, 3, 0), (20, 3, 0), (6, 1, 0), (2, 1, 0), (12, 3, 0)):
            cmds.setAttr(self.arm + ".translate", *translate)
            self.check(owner, results, rest, 8.0, 14.0)
            values.append(cmds.getAttr(str(owner) + ".overStroke"))
        self.assertGreater(values[1], 0.0)
        self.assertLess(values[3], 0.0)
        self.assertAlmostEqual(values[4], 0.0, places=6)
        cmds.setAttr(str(owner) + ".maximum", 10.0)
        cmds.setAttr(self.arm + ".translate", 20, 3, 0)
        self.check(owner, results, rest, 8.0, 10.0)

    def test_length_in_centimeters(self):
        """UIの長さ単位がmでも、距離の出力はcmのまま。"""
        owner, results = self.build()
        expected = cmds.getAttr(str(owner) + ".length")
        cmds.currentUnit(linear="m")
        try:
            self.assertAlmostEqual(cmds.getAttr(str(owner) + ".length"), expected, places=4)
        finally:
            cmds.currentUnit(linear="cm")

    def test_invalid_arguments(self):
        """範囲外の値・軸・同じ位置・既存の名前を拒否する。"""
        for kwargs in ({"aimAxis": "w"}, {"aimAxis": "y", "upAxis": "y"}, {"minimum": 5, "maximum": 5},
                       {"minimum": -1}, {"maximum": float("inf")}):
            with self.assertRaises(ValueError):
                Piston.create(self.base, self.tip, **kwargs)
        with self.assertRaises(ValueError):
            Piston.create(self.base, self.base)
        same = cmds.createNode("transform", name="samePlace", parent=self.frame)
        cmds.setAttr(same + ".translate", 0, 1, 0)
        with self.assertRaises(ValueError):
            Piston.create(self.base, same)
        Piston.create(self.base, self.tip, name="taken")
        with self.assertRaises(ValueError):
            Piston.create(self.base, self.tip, name="taken")

    def test_undo_removes_graph(self):
        """生成を1回のUndoで取り消せる。"""
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        before = set(cmds.ls())
        Piston.create(self.base, self.tip, name="undoPiston")
        self.assertTrue(cmds.objExists("undoPiston"))
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main()
