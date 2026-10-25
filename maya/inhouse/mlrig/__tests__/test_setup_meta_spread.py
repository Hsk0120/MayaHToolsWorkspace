"""MetaSpreadの回転の分配を、OpenMayaのクォータニオンの球面線形補間で求めた期待値と比較する。"""

import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import MetaSpread

#: 両端のjointへ与える回転(度)。広げる・握る・ねじる・逆向きを含む。
POSES = [((0, 0, 0), (0, 0, 0)), ((0, 15, 0), (0, -25, 0)), ((20, 0, 10), (-30, 5, 40)),
         ((0, 0, 0), (0, 40, 0)), ((10, -20, 5), (0, 0, 0)), ((-35, 30, -15), (25, -40, 30))]


def _local(node):
    """ローカル行列(jointOrientを含む)。"""
    return om.MMatrix(cmds.getAttr(node + ".matrix"))


def _rotation(matrix):
    """行列の回転のクォータニオン。"""
    return om.MTransformationMatrix(matrix).rotation(asQuaternion=True)


class MetaSpreadTest(unittest.TestCase):
    """作成時に跳ねない・両端の回転の分配・位置の保持・weightの変更・引数検査・Undoを確認する。"""

    def setUp(self):
        """回転した手の下に、jointOrientの異なる4本の中手骨を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.hand = cmds.createNode("transform", name="hand")
        cmds.setAttr(self.hand + ".translate", 40, 120, 3)
        cmds.setAttr(self.hand + ".rotate", 10, -60, 25)
        self.metas = []
        for index in range(4):
            joint = cmds.createNode("joint", name="meta{}".format(index), parent=self.hand)
            cmds.setAttr(joint + ".translate", 1.0, 0.2 * index, 1.5 - index)
            cmds.setAttr(joint + ".jointOrient", 3 * index, -8 * index, 5 * index)
            self.metas.append(joint)

    def build(self, **kwargs):
        """セットアップと、出力をoffsetParentMatrixで受ける結果jointを手の下に作る。"""
        graph = MetaSpread.create(self.metas[0], self.metas[3], self.metas[1:3], name="metaSp", **kwargs)
        owner = str(graph.container)
        results = []
        for index in range(2):
            result = cmds.createNode("joint", name="result{}".format(index), parent=self.hand)
            cmds.connectAttr("{}.matrix{}".format(owner, index), result + ".offsetParentMatrix")
            results.append(result)
        return owner, results

    def test_no_pop_on_create(self):
        """作成直後の出力は間のjointのワールド行列と一致する。"""
        before = [om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]")) for node in self.metas[1:3]]
        owner, results = self.build()
        for matrix, result in zip(before, results):
            self.assertTrue(om.MMatrix(cmds.getAttr(result + ".worldMatrix[0]")).isEquivalent(matrix, 1e-5))
        self.assertAlmostEqual(cmds.getAttr(owner + ".weight0"), 1.0 / 3.0)
        self.assertAlmostEqual(cmds.getAttr(owner + ".weight1"), 2.0 / 3.0)

    def test_distribution(self):
        """間のjointの回転 = 生成時の回転 * slerp(P0, P1, weight)、位置は生成時のまま。"""
        rest = [_local(node) for node in self.metas]
        owner, results = self.build()
        for first, last in POSES:
            cmds.setAttr(self.metas[0] + ".rotate", *first)
            cmds.setAttr(self.metas[3] + ".rotate", *last)
            p0 = _rotation(rest[0]).inverse() * _rotation(_local(self.metas[0]))
            p1 = _rotation(rest[3]).inverse() * _rotation(_local(self.metas[3]))
            for index, result in enumerate(results):
                weight = cmds.getAttr("{}.weight{}".format(owner, index))
                # 短い側の弧で補間する(内積が負なら一方の符号を反転)。
                dot = p0.x * p1.x + p0.y * p1.y + p0.z * p1.z + p0.w * p1.w
                target = om.MQuaternion(-p1.x, -p1.y, -p1.z, -p1.w) if dot < 0 else p1
                blend = om.MQuaternion.slerp(p0, target, weight)
                expected = _rotation(rest[index + 1]) * blend
                actual = _rotation(om.MMatrix(cmds.getAttr(result + ".offsetParentMatrix")))
                self.assertTrue(actual.isEquivalent(expected, 1e-4) or actual.isEquivalent(expected.negate(), 1e-4),
                                (first, last, index))
                position = om.MMatrix(cmds.getAttr(result + ".offsetParentMatrix"))
                self.assertTrue(om.MVector(position[12], position[13], position[14]).isEquivalent(
                    om.MVector(rest[index + 1][12], rest[index + 1][13], rest[index + 1][14]), 1e-5))

    def test_one_end_only(self):
        """一方の端だけを回すと、間のjointは割合に応じた角度だけ回る。"""
        owner, results = self.build(weights=[0.25, 0.75])
        cmds.setAttr(self.metas[3] + ".rotateY", 40)
        for index, ratio in enumerate((0.25, 0.75)):
            actual = _rotation(om.MMatrix(cmds.getAttr(results[index] + ".offsetParentMatrix")))
            delta = _rotation(self._restLocal(index + 1)).inverse() * actual
            self.assertAlmostEqual(om.MAngle(delta.asAxisAngle()[1]).asDegrees(), 40.0 * ratio, places=4)

    def _restLocal(self, index):
        """jointOrientだけのローカル行列(rotateが0のときの回転)。"""
        orient = cmds.getAttr(self.metas[index] + ".jointOrient")[0]
        rotation = om.MEulerRotation(*[om.MAngle(v, om.MAngle.kDegrees).asRadians() for v in orient])
        return rotation.asMatrix()

    def test_weight_attribute(self):
        """weightを0にすると一方の端、1にするともう一方の端と同じ親空間の差で回る。"""
        owner, results = self.build()
        cmds.setAttr(self.metas[0] + ".rotate", 0, 20, 0)
        cmds.setAttr(self.metas[3] + ".rotate", 0, -30, 10)
        for weight, end in ((0.0, 0), (1.0, 3)):
            cmds.setAttr(owner + ".weight0", weight)
            p = _rotation(self._restLocal(end)).inverse() * _rotation(_local(self.metas[end]))
            expected = _rotation(self._restLocal(1)) * p
            actual = _rotation(om.MMatrix(cmds.getAttr(results[0] + ".offsetParentMatrix")))
            self.assertTrue(actual.isEquivalent(expected, 1e-4) or actual.isEquivalent(expected.negate(), 1e-4),
                            weight)

    def test_bad_arguments(self):
        """不正な引数は何も作らずにValueErrorになる。"""
        before = set(cmds.ls())
        other = cmds.createNode("joint", name="otherParent")
        before.add(other)
        for args, kwargs in (((self.metas[0], self.metas[3], []), {}),
                             ((self.metas[0], self.metas[0], self.metas[1:3]), {}),
                             ((self.metas[0], self.metas[3], [other]), {}),
                             ((self.metas[0], self.metas[3], self.metas[1:3]), {"weights": [0.5]}),
                             ((self.metas[0], self.metas[3], self.metas[1:3]), {"weights": [0.5, 1.5]})):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                MetaSpread.create(*args, **kwargs)
        self.assertEqual(set(cmds.ls()), before)
        MetaSpread.create(self.metas[0], self.metas[3], self.metas[1:3], name="metaSp")
        with self.assertRaises(ValueError):
            MetaSpread.create(self.metas[0], self.metas[3], self.metas[1:3], name="metaSp")

    def test_undo(self):
        """1回のUndoで生成物が消える。"""
        cmds.undoInfo(state=True, infinity=True)
        before = set(cmds.ls())
        MetaSpread.create(self.metas[0], self.metas[3], self.metas[1:3], name="metaSp")
        self.assertNotEqual(set(cmds.ls()), before)
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main(argv=["metaSpread"], exit=False, verbosity=2)
