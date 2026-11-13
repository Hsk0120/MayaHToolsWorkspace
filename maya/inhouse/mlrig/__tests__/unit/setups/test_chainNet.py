"""ChainNetの受け渡しを、OpenMayaで独立に求めた差の補間と節の積の期待値と比較する。"""

import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import ChainNet

#: 親チェーンA・Bの各節へ与える (rotate(度), translate の加算(cm))。曲げ・ねじり・位置の移動・逆向きを含む。
POSES = [
    ([((0, 0, 30), (0, 0, 0)), ((0, 0, 20), (0, 0, 0)), ((0, 0, 10), (0, 0, 0))],
     [((0, 0, -10), (0, 0, 0)), ((0, 0, -30), (0, 0, 0)), ((0, 0, 0), (0, 0, 0))]),
    ([((15, -20, 40), (0, 0.5, 0)), ((-30, 10, 5), (0, 0, 0.3)), ((0, 45, -20), (0.2, 0, 0))],
     [((0, 0, 0), (0, 0, 0)), ((10, 0, 60), (0, -0.4, 0)), ((25, -35, 10), (0, 0, 0))]),
    ([((-50, 30, 70), (0, 0, 0)), ((40, -60, 0), (0, 0, 0)), ((0, 0, -80), (0, 0, 0))],
     [((60, 20, -40), (0.3, 0.3, 0)), ((-20, 50, 30), (0, 0, 0)), ((90, 0, 10), (0, 0, 0))]),
]


def _matrix(plug):
    """plugの行列。"""
    return om.MMatrix(cmds.getAttr(plug))


def _blend(first, second, weight):
    """blendMatrixと同じ補間(位置・scaleは線形、回転はクォータニオンの球面線形補間)の独立計算。"""
    a, b = om.MTransformationMatrix(first), om.MTransformationMatrix(second)
    result = om.MTransformationMatrix()
    ta, tb = a.translation(om.MSpace.kTransform), b.translation(om.MSpace.kTransform)
    result.setTranslation(ta + (tb - ta) * weight, om.MSpace.kTransform)
    qa, qb = a.rotation(asQuaternion=True), b.rotation(asQuaternion=True)
    result.setRotation(om.MQuaternion.slerp(qa, qb, weight))
    sa, sb = a.scale(om.MSpace.kTransform), b.scale(om.MSpace.kTransform)
    result.setScale([x + (y - x) * weight for x, y in zip(sa, sb)], om.MSpace.kTransform)
    return result.asMatrix()


class ChainNetTest(unittest.TestCase):
    """作成時に跳ねない・差の補間と節の積・子の手付けの重なり・bias・片側・長さの違い・所有・引数を確認する。"""

    def setUp(self):
        """回転した胴の下に、jointOrientの異なる3節の親チェーン2本と、その間の子チェーン3本を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.body = cmds.createNode("transform", name="body")
        cmds.setAttr(self.body + ".translate", 5, 30, -2)
        cmds.setAttr(self.body + ".rotate", 20, -35, 10)
        self.masterA = self.chain("masterA", 0.0, 3)
        self.masterB = self.chain("masterB", 4.0, 3)
        self.slaves = [self.chain("slave{}".format(index), z, 3) for index, z in enumerate((1.0, 2.0, 3.0))]

    def chain(self, name, z, count, orient=True):
        """胴の下に、x方向へ並ぶjointのチェーンを作る。根元は offsetParentMatrix に位置を持つ。"""
        joints, parent = [], self.body
        for index in range(count):
            joint = cmds.createNode("joint", name="{}_{}".format(name, index), parent=parent)
            if index:
                cmds.setAttr(joint + ".translate", 2.0, 0.1 * index, 0)
            else:
                rest = om.MTransformationMatrix()
                rest.setTranslation(om.MVector(0, 0, z), om.MSpace.kTransform)
                rest.setRotation(om.MEulerRotation(0.1, 0.2, -0.1))
                cmds.setAttr(joint + ".offsetParentMatrix", list(rest.asMatrix()), type="matrix")
            if orient:
                cmds.setAttr(joint + ".jointOrient", 4 * index, -6 * index, 3 * index)
            cmds.setAttr(joint + ".rotate", 5 * index + z, 0, -2 * index)
            joints.append(joint)
            parent = joint
        return joints

    def pose(self, chain, values):
        """チェーンの各節へ、生成時の値に回転・位置の加算を与える。"""
        for node, (rotate, move) in zip(chain, values):
            cmds.setAttr(node + ".rotate", *rotate)
            for axis, value in zip("XYZ", move):
                plug = node + ".translate" + axis
                cmds.setAttr(plug, self.rests[node][axis] + value)

    def turn(self, node, degrees):
        """節の回転を R = Rd * R0 にする(D = R * R0^-1 が生成時のローカル空間での回転 Rd になる)。"""
        rest = om.MEulerRotation([om.MAngle(v, om.MAngle.kDegrees).asRadians()
                                  for v in self.rotations[node]]).asMatrix()
        turn = om.MEulerRotation([om.MAngle(v, om.MAngle.kDegrees).asRadians() for v in degrees]).asMatrix()
        euler = om.MTransformationMatrix(turn * rest).rotation()
        cmds.setAttr(node + ".rotate", *[om.MAngle(v).asDegrees() for v in (euler.x, euler.y, euler.z)])

    def build(self, masterB=True, slaves=None, **kwargs):
        """セットアップを作り、生成時の値を覚える。"""
        slaves = self.slaves if slaves is None else slaves
        nodes = self.masterA + self.masterB + [node for chain in slaves for node in chain]
        self.rests = {node: dict(zip("XYZ", cmds.getAttr(node + ".translate")[0])) for node in nodes}
        self.rotations = {node: cmds.getAttr(node + ".rotate")[0] for node in nodes}
        self.matrices = {node: _matrix(node + ".matrix") for node in nodes}
        self.offsets = {node: _matrix(node + ".offsetParentMatrix") for node in nodes}
        graph = ChainNet.create(self.masterA, self.masterB if masterB else None, slaves,
                                name="net", connect=True, **kwargs)
        return str(graph.container)

    def delta(self, node):
        """親の節の、生成時のローカル空間での差 D = M * M0^-1。"""
        return _matrix(node + ".matrix") * self.matrices[node].inverse()

    def expected(self, owner, slaves, masterB=True):
        """子チェーンの節のワールド行列の期待値を、親の差の補間と節の積で求める。"""
        results = []
        for slave, chain in enumerate(slaves):
            bias = cmds.getAttr("{}.bias{}".format(owner, slave))
            parent = _matrix(self.body + ".worldMatrix[0]")
            rows = []
            for index, node in enumerate(chain):
                first = self.delta(self.masterA[min(index, len(self.masterA) - 1)])
                second = self.delta(self.masterB[min(index, len(self.masterB) - 1)]) if masterB else om.MMatrix()
                delta = _blend(first, second, bias)
                rest = self.matrices[node]
                local = _matrix(node + ".matrix") * rest.inverse() * delta * rest * self.offsets[node]
                parent = local * parent
                rows.append((node, delta, parent))
            results.append(rows)
        return results

    def assertChains(self, owner, slaves=None, masterB=True, tolerance=1e-4):
        """全ての子の節で、出力の差とワールド行列が期待値と一致する。"""
        slaves = self.slaves if slaves is None else slaves
        for slave, rows in enumerate(self.expected(owner, slaves, masterB)):
            for index, (node, delta, world) in enumerate(rows):
                actual = _matrix("{}.delta{}_{}".format(owner, slave, index))
                self.assertTrue(actual.isEquivalent(delta, tolerance), (node, list(actual), list(delta)))
                actual = _matrix(node + ".worldMatrix[0]")
                self.assertTrue(actual.isEquivalent(world, tolerance), (node, list(actual), list(world)))

    def test_no_pop_on_create(self):
        """作成直後は子の全ての節のワールド行列が変わらず、biasの既定値は等間隔。"""
        nodes = [node for chain in self.slaves for node in chain]
        before = [_matrix(node + ".worldMatrix[0]") for node in nodes]
        owner = self.build()
        for node, matrix in zip(nodes, before):
            self.assertTrue(_matrix(node + ".worldMatrix[0]").isEquivalent(matrix, 1e-9), node)
            self.assertEqual(cmds.listConnections(node + ".offsetParentMatrix", source=True), [owner])
        for index, value in enumerate((0.25, 0.5, 0.75)):
            self.assertAlmostEqual(cmds.getAttr("{}.bias{}".format(owner, index)), value)

    def test_poses_match_independent_blend(self):
        """親の各姿勢で、子の差がblendMatrixと同じ補間の独立計算と一致し、ワールド行列が節の積と一致する。"""
        owner = self.build()
        for valuesA, valuesB in POSES:
            self.pose(self.masterA, valuesA)
            self.pose(self.masterB, valuesB)
            self.assertChains(owner)

    def test_same_motion_and_bias_ends(self):
        """AとBが同じ動きなら、どのbiasでも子は同じ差を受ける。bias=0はA、bias=1はBの差と一致する。"""
        owner = self.build()
        for chain in (self.masterA, self.masterB):
            for node, (rotate, _) in zip(chain, POSES[1][0]):
                self.turn(node, rotate)
        reference = [self.delta(node) for node in self.masterA]
        for slave in range(3):
            for index in range(3):
                actual = _matrix("{}.delta{}_{}".format(owner, slave, index))
                self.assertTrue(actual.isEquivalent(reference[index], 1e-5))
        self.pose(self.masterB, POSES[1][1])
        cmds.setAttr(owner + ".bias0", 0.0)
        cmds.setAttr(owner + ".bias2", 1.0)
        for index in range(3):
            self.assertTrue(_matrix("{}.delta0_{}".format(owner, index)).isEquivalent(
                self.delta(self.masterA[index]), 1e-5))
            self.assertTrue(_matrix("{}.delta2_{}".format(owner, index)).isEquivalent(
                self.delta(self.masterB[index]), 1e-5))
        self.assertChains(owner)

    def test_planar_bend_is_proportional(self):
        """同じ軸だけで曲げると、子の曲がりの角度は bias による線形補間になる。"""
        owner = self.build()
        for chain, degrees in ((self.masterA, 30.0), (self.masterB, -30.0)):
            for node in chain:
                self.turn(node, (0, 0, degrees))
        for slave, bias in enumerate((0.25, 0.5, 0.75)):
            for index in range(3):
                delta = om.MTransformationMatrix(_matrix("{}.delta{}_{}".format(owner, slave, index)))
                axis, angle = delta.rotation(asQuaternion=True).asAxisAngle()
                signed = om.MAngle(angle).asDegrees() * (1 if axis.z >= 0 else -1)
                self.assertAlmostEqual(signed, 30.0 - 60.0 * bias, places=3)
                self.assertAlmostEqual(abs(axis.z), 1.0, places=5) if abs(signed) > 1e-3 else None

    def test_slave_own_animation_layers_on_top(self):
        """子の節を手付けで回しても、親から受けた差の上に重なり、節の積の期待値と一致する。"""
        owner = self.build()
        self.pose(self.masterA, POSES[2][0])
        self.pose(self.masterB, POSES[2][1])
        cmds.setAttr(self.slaves[1][0] + ".rotate", 0, 30, 15)
        cmds.setAttr(self.slaves[1][2] + ".rotate", -20, 0, 40)
        cmds.setAttr(self.slaves[1][1] + ".translateY", 0.6)
        self.assertChains(owner)
        cmds.setAttr(self.body + ".rotate", -40, 70, 5)
        self.assertChains(owner)

    def test_single_master_and_different_lengths(self):
        """Bが無いときbiasはAの動きを弱める割合になる。子が親より長ければ、親の最後の節の差を使う。"""
        cmds.delete(self.slaves[2][0])
        long_chain = self.chain("slaveLong", 3.0, 5, orient=False)
        slaves = [self.slaves[0], long_chain]
        owner = self.build(masterB=False, slaves=slaves)
        self.assertEqual(cmds.getAttr(owner + ".bias0"), 0.0)
        self.pose(self.masterA, POSES[1][0])
        self.assertChains(owner, slaves, masterB=False)
        cmds.setAttr(owner + ".bias1", 0.4)
        self.assertChains(owner, slaves, masterB=False)
        for index in (3, 4):
            self.assertTrue(cmds.objExists("{}.matrix1_{}".format(owner, index)))

    def test_ownership_and_undo(self):
        """生成した演算ノードはcontainerが所有し、1回のUndoで作成前に戻り、Redoで戻る。"""
        before = set(cmds.ls())
        nodes = [node for chain in self.slaves for node in chain]
        rest = [_matrix(node + ".worldMatrix[0]") for node in nodes]
        owner = self.build()
        created = set(cmds.ls()) - before - {owner}
        created -= set(cmds.ls(type="hyperLayout"))
        members = set(cmds.container(owner, query=True, nodeList=True) or [])
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.undo()
        self.assertFalse(cmds.objExists(owner))
        for node, matrix in zip(nodes, rest):
            self.assertIsNone(cmds.listConnections(node + ".offsetParentMatrix", source=True))
            self.assertTrue(_matrix(node + ".worldMatrix[0]").isEquivalent(matrix, 1e-9))
        cmds.redo()
        self.assertTrue(cmds.objExists(owner))
        self.assertEqual(cmds.listConnections(self.slaves[0][0] + ".offsetParentMatrix", source=True), [owner])

    def test_arguments(self):
        """不正な引数・接続済みの子・重複・既存の名前を拒否する。"""
        with self.assertRaises(ValueError):
            ChainNet.create([], self.masterB, self.slaves, name="bad")
        with self.assertRaises(ValueError):
            ChainNet.create(self.masterA, self.masterB, [], name="bad")
        with self.assertRaises(ValueError):
            ChainNet.create(self.masterA, self.masterB, [self.masterA], name="bad")
        with self.assertRaises(ValueError):
            ChainNet.create(self.masterA, self.masterB, self.slaves, name="bad", biases=[0.5])
        with self.assertRaises(ValueError):
            ChainNet.create(self.masterA, self.masterB, self.slaves, name="bad", biases=[0.5, 0.5, 1.5])
        with self.assertRaises(ValueError):
            ChainNet.create(self.masterA, self.masterB, [[self.slaves[0][0], self.slaves[0][0]]], name="bad")
        with self.assertRaises(ValueError):
            ChainNet.create("masterA_0", self.masterB, self.slaves, name="bad")
        with self.assertRaises(ValueError):
            ChainNet.create(self.masterA, self.masterB, [[cmds.createNode("multMatrix")]], name="bad")
        source = cmds.createNode("composeMatrix")
        cmds.connectAttr(source + ".outputMatrix", self.slaves[2][1] + ".offsetParentMatrix")
        with self.assertRaises(ValueError):
            ChainNet.create(self.masterA, self.masterB, self.slaves, name="bad", connect=True)
        self.assertFalse(cmds.objExists("bad"))
        cmds.disconnectAttr(source + ".outputMatrix", self.slaves[2][1] + ".offsetParentMatrix")
        ChainNet.create(self.masterA, self.masterB, self.slaves, name="good")
        with self.assertRaises(ValueError):
            ChainNet.create(self.masterA, self.masterB, self.slaves, name="good")


if __name__ == "__main__":
    unittest.main()
