"""VirtualChainの仮想のFK階層を、独立に書いた行列の式と本物の親子の階層で確かめる。"""

import random
import unittest

from maya import cmds
from maya.api import OpenMaya as om2

from mlrig.setups import VirtualChain

#: 位置の許容(cm)。blendMatrix は行列を成分に分けて組み直すので、倍精度の丸めの範囲で確かめる。
TOLERANCE = 1e-6


def _world(node):
    return om2.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _local(node):
    return om2.MMatrix(cmds.getAttr(node + ".matrix"))


def _close(test, first, second, message=None):
    for a, b in zip(first, second):
        test.assertLess(abs(a - b), TOLERANCE, message)


def _pose(node, generator):
    cmds.setAttr(node + ".translate", *[generator.uniform(-2, 2) for _ in range(3)])
    cmds.setAttr(node + ".rotate", *[generator.uniform(-120, 120) for _ in range(3)])
    cmds.setAttr(node + ".scale", *[generator.uniform(0.5, 1.5) for _ in range(3)])


class VirtualChainTest(unittest.TestCase):
    """作成時の不変、FKの式・本物の階層との一致、follow、親の移動、所有とUndo・引数を確認する。"""

    def setUp(self):
        """回転した親の下に、兄弟として並べた3つのコントロール(作成時に回転・スケールを持つ)を作る。"""
        cmds.file(new=True, force=True)
        self.group = cmds.createNode("transform", name="ctrls")
        cmds.setAttr(self.group + ".translate", 1, 2, 3)
        cmds.setAttr(self.group + ".rotate", 10, 20, 30)
        self.controls = []
        for index in range(3):
            node = cmds.createNode("transform", name="ctrl{}".format(index), parent=self.group)
            cmds.setAttr(node + ".translate", 3 * index, 0.5 * index, 0)
            cmds.setAttr(node + ".rotate", 0, 0, -15 * index)
            cmds.setAttr(node + ".scale", 1, 1 + 0.1 * index, 1)
            self.controls.append(node)
        self.rest_world = [_world(node) for node in self.controls]
        self.rest_local = [_local(node) for node in self.controls]
        self.setup = VirtualChain.create(self.controls, name="chain")
        self.owner = str(self.setup.container)

    def _expected(self):
        """W_i = M_i * M_i(作成時)^-1 * W_i(作成時) * W_(i-1)(作成時)^-1 * W_(i-1) を根元から順に求める。"""
        result = [_world(self.controls[0])]
        for index in range(1, len(self.controls)):
            node = self.controls[index]
            result.append(_local(node) * self.rest_local[index].inverse() * self.rest_world[index]
                          * self.rest_world[index - 1].inverse() * result[-1])
        return result

    def test_rest_unchanged(self):
        """作成しても姿勢は跳ねず、follow は keyable で既定1、getControls は作成時の順。"""
        for node, rest in zip(self.controls, self.rest_world):
            _close(self, _world(node), rest, node)
        for attribute in ("follow1", "follow2"):
            self.assertEqual(cmds.getAttr(self.owner + "." + attribute), 1.0)
            self.assertTrue(cmds.getAttr(self.owner + "." + attribute, keyable=True))
        self.assertFalse(cmds.objExists(self.owner + ".follow0"))
        self.assertEqual([node.getName() for node in self.setup.getControls()], self.controls)
        self.assertEqual(cmds.listRelatives(self.controls[2], parent=True), [self.group])

    def test_formula(self):
        """乱数の姿勢30組で、各コントロールのワールド行列が独立に書いた式と一致する。"""
        generator = random.Random(3)
        for _ in range(30):
            for node in self.controls:
                _pose(node, generator)
            for index, (node, expected) in enumerate(zip(self.controls, self._expected())):
                _close(self, _world(node), expected, index)

    def test_matches_real_hierarchy(self):
        """本物の親子に組んだ複製へ、作成時からの同じ局所の変化を入れるとワールド行列が一致する。"""
        real = []
        for index in range(len(self.controls)):
            copy = cmds.createNode("transform", name="real{}".format(index),
                                   parent=real[-1] if real else self.group)
            cmds.xform(copy, matrix=list(self.rest_world[index]), worldSpace=True)
            real.append(copy)
        real_rest = [_local(copy) for copy in real]
        generator = random.Random(5)
        for _ in range(20):
            for index, (node, copy) in enumerate(zip(self.controls, real)):
                _pose(node, generator)
                # 作成時からの局所の変化 D = M * M(作成時)^-1 を、本物の階層の局所行列へも同じく掛ける。
                delta = _local(node) * self.rest_local[index].inverse()
                cmds.xform(copy, matrix=list(delta * real_rest[index]), objectSpace=True)
            for node, copy in zip(self.controls, real):
                _close(self, _world(node), _world(copy), node)

    def test_follow_weight(self):
        """follow を0にしたつなぎは前を追わず、その先は自分を追い続ける。0.5は位置が中間。"""
        generator = random.Random(9)
        for node in self.controls:
            _pose(node, generator)
        followed = _world(self.controls[1])
        cmds.setAttr(self.owner + ".follow1", 0)
        parent = _world(self.group)
        # 追わないときは作成時の offsetParentMatrix のまま(= M * M(作成時)^-1 * W(作成時))。
        free = _local(self.controls[1]) * self.rest_local[1].inverse() * self.rest_world[1]
        _close(self, _world(self.controls[1]), free)
        _close(self, om2.MMatrix(cmds.getAttr(self.controls[1] + ".offsetParentMatrix")),
               self.rest_local[1].inverse() * self.rest_world[1] * parent.inverse())
        # 2番目は1番目を追い続ける。
        _close(self, _world(self.controls[2]), self._expected_from(1)[2])
        cmds.setAttr(self.owner + ".follow1", 0.5)
        middle = om2.MTransformationMatrix(_world(self.controls[1])).translation(om2.MSpace.kWorld)
        ends = [om2.MTransformationMatrix(item).translation(om2.MSpace.kWorld) for item in (free, followed)]
        # blendMatrix は offsetParentMatrix を成分ごとに混ぜるので、局所の移動が0でなければ位置は線形にならない。
        # ここでは中間が両端の間(両端を結ぶ線からの距離が両端の距離より小さい)ことだけを確かめる。
        span = (ends[1] - ends[0]).length()
        self.assertLess((middle - ends[0]).length(), span)
        self.assertLess((middle - ends[1]).length(), span)

    def _expected_from(self, start):
        """start番目から先を、start番目の実際のワールド行列を根として式で求める。"""
        result = {start: _world(self.controls[start])}
        for index in range(start + 1, len(self.controls)):
            node = self.controls[index]
            result[index] = (_local(node) * self.rest_local[index].inverse() * self.rest_world[index]
                             * self.rest_world[index - 1].inverse() * result[index - 1])
        return result

    def test_parent_moves_once(self):
        """実際の親を動かすと、全体が親と一緒に1回だけ動く(二重に掛からない)。"""
        before = [_world(node) for node in self.controls]
        group_rest = _world(self.group)
        cmds.setAttr(self.group + ".translate", -4, 1, 7)
        cmds.setAttr(self.group + ".rotate", 50, -30, 80)
        cmds.setAttr(self.group + ".scale", 2, 2, 2)
        change = group_rest.inverse() * _world(self.group)
        for node, rest in zip(self.controls, before):
            _close(self, _world(node), rest * change, node)

    def test_container_and_undo(self):
        """生成ノードはcontainerが所有し、作成はUndoで消えRedoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {node for node in cmds.ls("chain_*") if cmds.nodeType(node) != "hyperLayout"}
        self.assertEqual(len(created), 4)
        self.assertTrue(created <= members)
        self.assertFalse(set(self.controls) & members)
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        nodes = [cmds.createNode("transform", name="c{}".format(index)) for index in range(2)]
        cmds.setAttr(nodes[1] + ".translateX", 2)
        cmds.flushUndo()
        VirtualChain.create(nodes, name="chain")
        self.assertTrue(cmds.objExists("chain.follow1"))
        cmds.undo()
        self.assertFalse(cmds.objExists("chain"))
        self.assertFalse(cmds.ls("chain_*"))
        self.assertFalse(cmds.listConnections(nodes[1] + ".offsetParentMatrix", source=True))
        cmds.redo()
        self.assertTrue(cmds.objExists("chain.follow1"))
        cmds.setAttr(nodes[0] + ".translateY", 3)
        self.assertAlmostEqual(cmds.xform(nodes[1], query=True, translation=True, worldSpace=True)[1], 3.0)

    def test_arguments(self):
        """1つだけ・重複・存在しない・Transformでない・先祖の関係・接続済み・名前の重複を拒否する。"""
        child = cmds.createNode("transform", name="child", parent=self.controls[0])
        loose = [cmds.createNode("transform", name="loose{}".format(index)) for index in range(2)]
        mesh_shape = cmds.createNode("mesh", name="meshShape")
        cases = (
            [loose[0]],
            [loose[0], loose[0]],
            [loose[0], "missingNode"],
            [loose[0], mesh_shape],
            [self.controls[0], child],
            [child, self.controls[0]],
            [loose[0], self.controls[1]],
        )
        for controls in cases:
            with self.subTest(controls=controls), self.assertRaises(ValueError):
                VirtualChain.create(controls, name="bad")
        with self.assertRaises(ValueError):
            VirtualChain.create(loose, name="chain")
        self.assertFalse(cmds.objExists("bad"))
        self.assertFalse(cmds.listConnections(loose[1] + ".offsetParentMatrix", source=True))


if __name__ == "__main__":
    unittest.main()
