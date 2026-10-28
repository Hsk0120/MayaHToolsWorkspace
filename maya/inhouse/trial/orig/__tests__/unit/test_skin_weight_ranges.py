"""SkinCluster.setWeightsの範囲指定setAttrと、要素ごとの書込みとの一致を実Mayaで検証する。

通常経路は連続した論理番号を ``weights[a:b]`` の1回のsetAttrへまとめる。番号の穴・指定順・
ロック・入力接続での部分更新とエラー文言・Undo/Redoが、要素ごとの書込みと同じことを確かめる。
"""

import sys
import unittest
import uuid
from unittest.mock import patch

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import skinCluster as skin_module
from mlib.nodes.skinCluster import SkinCluster


class SkinWeightRangeWriteTest(unittest.TestCase):
    """範囲指定の書込みが、従来の要素ごとのsetAttrと同じ結果になることを検証する。"""

    def setUp(self):
        self.ns = "mlibWeightRange_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        cmds.select(clear=True)
        self.joints = [cmds.joint(position=(0, i, 0), name=f"{self.ns}:j{i}") for i in range(5)]
        cmds.select(clear=True)
        self.mesh = cmds.polyCube(name=self.ns + ":mesh", constructionHistory=False)[0]
        name = cmds.skinCluster(self.joints, self.mesh, toSelectedBones=True, name=self.ns + ":skin")[0]
        self.skin = mlib.getNode(name)
        cmds.setAttr(name + ".normalizeWeights", 0)
        self.prefix = self.skin.getFullName() + ".weightList"
        self.count = cmds.polyEvaluate(self.mesh, vertex=True)

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def element(self, vertex, index):
        return f"{self.prefix}[{vertex}].weights[{index}]"

    def raw(self, indices):
        return [[cmds.getAttr(self.element(v, i)) for i in indices] for v in range(self.count)]

    def sequential_error(self, vertex, index, value=0.5):
        """従来の要素ごとのsetAttrが同じ要素で送出するエラー文言を取得する。"""
        with self.assertRaises(RuntimeError) as context:
            cmds.setAttr(self.element(vertex, index), value)
        return str(context.exception)

    def test_consecutive_runs(self):
        self.assertEqual(SkinCluster._consecutive_runs([]), [])
        self.assertEqual(SkinCluster._consecutive_runs([0, 1, 2, 3]), [(0, 0, 4)])
        self.assertEqual(SkinCluster._consecutive_runs([0, 1, 3, 2]), [(0, 0, 2), (2, 3, 1), (3, 2, 1)])
        self.assertEqual(SkinCluster._consecutive_runs([3, 4, 0, 1]), [(0, 3, 2), (2, 0, 2)])
        self.assertEqual(SkinCluster._consecutive_runs([2, 1, 0]), [(0, 2, 1), (1, 1, 1), (2, 0, 1)])

    def test_contiguous_influences_use_one_call_per_vertex(self):
        """連続した論理番号は頂点ごとに1回、穴や逆順では区間ごとに書く。"""
        calls = []
        original = skin_module.set_attr

        def record(name, *values, **kwargs):
            calls.append((name, values))
            return original(name, *values, **kwargs)

        values = [0.1, 0.2, 0.3, 0.4] * self.count
        with patch.object(skin_module, "set_attr", side_effect=record):
            self.skin.setWeights(self.joints[:4], values)
        self.assertEqual(len(calls), self.count)
        self.assertEqual(calls[0], (self.element(0, "0:3"), (0.1, 0.2, 0.3, 0.4)))
        self.assertEqual(self.raw(range(4)), [[0.1, 0.2, 0.3, 0.4]] * self.count)

        calls.clear()
        with patch.object(skin_module, "set_attr", side_effect=record):
            self.skin.setWeights([self.joints[0], self.joints[2], self.joints[3]], [0.5, 0.25, 0.125])
        self.assertEqual(len(calls), self.count * 2)
        self.assertEqual(calls[0][0], self.element(0, 0))
        self.assertEqual(calls[1], (self.element(0, "2:3"), (0.25, 0.125)))

    def test_order_and_holes_match_logical_indices(self):
        """物理番号と論理番号の穴、指定順の入れ替えで値が正しい論理番号へ入る。"""
        cmds.skinCluster(self.skin.getFullName(), edit=True, removeInfluence=self.joints[1])
        order = [self.joints[4], self.joints[3], self.joints[0], self.joints[2]]
        values = [v for vertex in range(self.count) for v in (vertex, vertex + 0.25, vertex + 0.5, vertex + 0.75)]
        self.skin.setWeights(order, values)
        for vertex in range(self.count):
            self.assertEqual(cmds.getAttr(self.element(vertex, 4)), vertex)
            self.assertEqual(cmds.getAttr(self.element(vertex, 3)), vertex + 0.25)
            self.assertEqual(cmds.getAttr(self.element(vertex, 0)), vertex + 0.5)
            self.assertEqual(cmds.getAttr(self.element(vertex, 2)), vertex + 0.75)
        self.assertNotIn(1, cmds.getAttr(self.prefix + "[0].weights", multiIndices=True))
        self.assertEqual(list(self.skin.getWeights(order)), values)

    def test_undo_redo_restores_ranges_in_one_step(self):
        before = self.raw(range(5))
        values = [0.2] * 5
        self.skin.setWeights(self.joints, values)
        after = self.raw(range(5))
        self.assertEqual(after, [values] * self.count)
        cmds.undo()
        self.assertEqual(self.raw(range(5)), before)
        cmds.redo()
        self.assertEqual(self.raw(range(5)), after)

    def assert_partial_failure(self, vertex, blocked, prepare):
        """blockedの要素が拒否された時、手前だけ更新されて同じ文言で失敗することを確かめる。"""
        prepare()
        before = self.raw(range(4))
        expected_message = self.sequential_error(vertex, blocked)
        self.assertEqual(self.raw(range(4)), before)
        values = [0.1, 0.2, 0.3, 0.4]
        with self.assertRaises(RuntimeError) as context:
            self.skin.setWeights(self.joints[:4], values)
        self.assertEqual(str(context.exception), expected_message)
        current = self.raw(range(4))
        for v in range(self.count):
            if v < vertex:
                self.assertEqual(current[v], values)
            elif v == vertex:
                self.assertEqual(current[v], values[:blocked] + before[v][blocked:])
            else:
                self.assertEqual(current[v], before[v])
        cmds.undo()
        self.assertEqual(self.raw(range(4)), before)

    def test_locked_middle_element_updates_preceding_only(self):
        self.assert_partial_failure(1, 2, lambda: cmds.setAttr(self.element(1, 2), lock=True))

    def test_locked_first_element(self):
        self.assert_partial_failure(2, 0, lambda: cmds.setAttr(self.element(2, 0), lock=True))

    def test_locked_last_element(self):
        self.assert_partial_failure(3, 3, lambda: cmds.setAttr(self.element(3, 3), lock=True))

    def test_connected_element_updates_preceding_only(self):
        source = cmds.createNode("transform", name=self.ns + ":driver")
        self.assert_partial_failure(
            1, 1, lambda: cmds.connectAttr(source + ".translateX", self.element(1, 1)))

    def test_locked_row_fails_at_first_element(self):
        self.assert_partial_failure(
            2, 0, lambda: cmds.setAttr(f"{self.prefix}[2].weights", lock=True))

    def test_fast_rejects_locked_or_connected_before_changes(self):
        """fastは従来どおり全要素を先に検査し、親側のロックも要素名で拒否する。"""
        before = self.raw(range(4))
        cmds.setAttr(f"{self.prefix}[3].weights", lock=True)
        with self.assertRaises(RuntimeError) as context:
            self.skin.setWeights(self.joints[:4], [0.1, 0.2, 0.3, 0.4], fast=True)
        self.assertEqual(str(context.exception),
                         "Attribute is locked or connected: " + self.skin.getName() + ".weightList[3].weights[0]")
        self.assertEqual(self.raw(range(4)), before)
        cmds.setAttr(f"{self.prefix}[3].weights", lock=False)
        source = cmds.createNode("transform", name=self.ns + ":driver")
        cmds.connectAttr(source + ".translateX", self.element(4, 2))
        with self.assertRaises(RuntimeError) as context:
            self.skin.setWeights(self.joints[:4], [0.1, 0.2, 0.3, 0.4], fast=True)
        self.assertEqual(str(context.exception),
                         "Attribute is locked or connected: " + self.skin.getName() + ".weightList[4].weights[2]")
        self.assertEqual(self.raw(range(4))[:4], before[:4])
        cmds.disconnectAttr(source + ".translateX", self.element(4, 2))
        self.skin.setWeights(self.joints[:4], [0.1, 0.2, 0.3, 0.4], fast=True)
        self.assertEqual(self.raw(range(4)), [[0.1, 0.2, 0.3, 0.4]] * self.count)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
