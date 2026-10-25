"""SpaceBlendの重み付き追従を、OpenMayaで独立に求めた追従先・重み付き平均・球面補間と比較する。"""

import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import SpaceBlend


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _position(matrix):
    """行列の平行移動をMVectorで返す。"""
    return om.MVector(matrix[12], matrix[13], matrix[14])


class SpaceBlendTest(unittest.TestCase):
    """作成時の姿勢・単独の空間・位置の重み付き平均・回転の補間・重みが0・所有・Undo・引数を確認する。"""

    def setUp(self):
        """回転・移動した3つの空間と、それらと別の位置のfollowerを作り、生成時の追従先を記録する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.spaces = []
        for index, (translate, rotate) in enumerate((((0, 0, 0), (0, 0, 0)), ((3, 10, -2), (10, 30, 0)),
                                                     ((-4, 15, 1), (-20, 0, 45)))):
            node = cmds.createNode("transform", name="space" + str(index))
            cmds.setAttr(node + ".translate", *translate)
            cmds.setAttr(node + ".rotate", *rotate)
            self.spaces.append(node)
        self.follower = cmds.createNode("transform", name="follower")
        cmds.setAttr(self.follower + ".translate", 1, 12, 3)
        cmds.setAttr(self.follower + ".rotate", 15, -20, 5)
        rest = _matrix(self.follower + ".worldMatrix[0]")
        self.offsets = [rest * _matrix(space + ".worldMatrix[0]").inverse() for space in self.spaces]
        self.setup = SpaceBlend.create(self.follower, self.spaces, name="blend")
        self.owner = str(self.setup.container)
        self.rest = rest

    def _targets(self):
        """各空間の現在の追従先(独立に計算)。"""
        return [offset * _matrix(space + ".worldMatrix[0]") for offset, space in zip(self.offsets, self.spaces)]

    def _weights(self, *weights):
        for index, weight in enumerate(weights):
            cmds.setAttr("{}.weight{}".format(self.owner, index), weight)

    def _move(self):
        """空間をそれぞれ別に動かす・回す。"""
        cmds.setAttr(self.spaces[0] + ".translate", 2, -1, 0)
        cmds.setAttr(self.spaces[1] + ".rotate", 40, -10, 25)
        cmds.setAttr(self.spaces[1] + ".translate", 5, 8, 0)
        cmds.setAttr(self.spaces[2] + ".translate", -6, 20, 4)
        cmds.setAttr(self.spaces[2] + ".rotate", 0, 60, 45)

    def _assertMatrix(self, actual, expected, tolerance=1e-5):
        for index, (a, b) in enumerate(zip(actual, expected)):
            self.assertAlmostEqual(a, b, delta=tolerance, msg="element {}".format(index))

    def test_rest(self):
        """作成直後は、どの重みでも出力がfollowerの生成時のワールド行列と一致する(跳ねない)。"""
        for weights in ((1, 0, 0), (0, 1, 0), (0.3, 0.5, 2.0), (0, 0, 0)):
            with self.subTest(weights=weights):
                self._weights(*weights)
                self._assertMatrix(_matrix(self.owner + ".matrix"), self.rest)

    def test_single_space(self):
        """1つの空間だけ重みを持つと、その空間の追従先と一致し、他の空間を動かしても変わらない。"""
        self._move()
        targets = self._targets()
        for index in range(3):
            weights = [0.0, 0.0, 0.0]
            weights[index] = 0.7
            with self.subTest(space=index):
                self._weights(*weights)
                self._assertMatrix(_matrix(self.owner + ".matrix"), targets[index])

    def test_weighted_position(self):
        """位置は、重みの合計で割った追従先の位置の平均と一致する。"""
        self._move()
        targets = self._targets()
        for weights in ((1, 1, 0), (1, 1, 1), (0.2, 0.5, 0.3), (2.0, 0.0, 6.0), (0, 3, 1)):
            with self.subTest(weights=weights):
                self._weights(*weights)
                expected = sum((_position(t) * w for t, w in zip(targets, weights)), om.MVector()) / sum(weights)
                actual = _position(_matrix(self.owner + ".matrix"))
                self.assertTrue(actual.isEquivalent(expected, 1e-5), (actual, expected))
                self.assertAlmostEqual(cmds.getAttr(self.owner + ".totalWeight"), sum(weights), delta=1e-6)

    def test_rotation_between_two(self):
        """2つの空間だけなら、回転は w1/(w0+w1) の割合の球面補間と一致する。"""
        self._move()
        targets = self._targets()
        for weights in ((1, 1, 0), (3, 1, 0), (0.25, 0.75, 0)):
            with self.subTest(weights=weights):
                self._weights(*weights)
                first = om.MTransformationMatrix(targets[0]).rotation(asQuaternion=True)
                second = om.MTransformationMatrix(targets[1]).rotation(asQuaternion=True)
                expected = om.MQuaternion.slerp(first, second, weights[1] / (weights[0] + weights[1]))
                actual = om.MTransformationMatrix(_matrix(self.owner + ".matrix")).rotation(asQuaternion=True)
                self.assertTrue(actual.isEquivalent(expected, 1e-5) or actual.isEquivalent(expected.negateIt(), 1e-5))

    def test_ratios_and_zero(self):
        """割合の計算と、重みが全て0なら先頭の空間に追従すること。"""
        self.assertEqual(SpaceBlend.ratios([1.0, 1.0, 2.0]), [0.5, 0.5])
        self.assertEqual(SpaceBlend.ratios([0.0, 0.0, 1.0]), [0.0, 1.0])
        self.assertEqual(SpaceBlend.ratios([0.0, 0.0]), [0.0])
        self._move()
        self._weights(0, 0, 0)
        self._assertMatrix(_matrix(self.owner + ".matrix"), self._targets()[0])

    def test_defaults(self):
        """weightsを省略すると先頭だけ1で、指定した初期値はcontainerへ入る。"""
        self.assertEqual([cmds.getAttr("{}.weight{}".format(self.owner, i)) for i in range(3)], [1.0, 0.0, 0.0])
        setup = SpaceBlend.create(self.follower, self.spaces[:2], name="blend2", weights=(0.25, 0.75))
        self.assertEqual(cmds.getAttr(str(setup.container) + ".weight1"), 0.75)

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = cmds.listHistory(self.owner + ".matrix", pruneDagObjects=True) or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        SpaceBlend.create(self.follower, self.spaces, name="undoBlend")
        self.assertTrue(cmds.objExists("undoBlend"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoBlend"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoBlend.matrix"))

    def test_arguments(self):
        """空間の数・重複・followerを含む・重みの数と値・transform以外・名前の重複を拒否する。"""
        node = cmds.createNode("multiplyDivide")
        cases = (
            ((self.follower, self.spaces[:1]), {}),
            ((self.follower, [self.spaces[0], self.spaces[0]]), {}),
            ((self.follower, [self.follower, self.spaces[0]]), {}),
            ((self.follower, self.spaces), {"weights": (1, 0)}),
            ((self.follower, self.spaces), {"weights": (1, -1, 0)}),
            ((self.follower, self.spaces), {"weights": (1, float("nan"), 0)}),
            ((self.follower, self.spaces), {"weights": (1, float("inf"), 0)}),
            ((node, self.spaces), {}),
            ((self.follower, [self.spaces[0], node]), {}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                SpaceBlend.create(*args, name="bad", **kwargs)
        with self.assertRaises(ValueError):
            SpaceBlend.create(self.follower, self.spaces, name="blend")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()
