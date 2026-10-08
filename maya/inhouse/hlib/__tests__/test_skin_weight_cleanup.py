"""不正な疎ウェイト除去とforce付きinfluence解除を実Mayaで検証する。"""

import math
import sys
import unittest

import maya.cmds as cmds
import hlib


class SkinWeightCleanupTest(unittest.TestCase):
    """正常値・登録・ロック・Undoを保持して不正な既存要素だけを除去する。"""

    def setUp(self):
        """非正規化ウェイトを持つ3influenceの独立シーンを用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        self.parent = hlib.getNode(cmds.createNode("joint", name="cleanupParent"))
        self.child = hlib.getNode(cmds.createNode("joint", name="cleanupChild", parent=str(self.parent)))
        self.other = hlib.getNode(cmds.createNode("joint", name="cleanupOther"))
        self.names = [str(node) for node in (self.parent, self.child, self.other)]
        self.skin = self._skin("cleanupMesh", self.names)

    def _skin(self, name, influences):
        """指定influenceのcubeをバインドし、正規化を無効にする。

        Args:
            name (str): メッシュ名。
            influences (list[str]): 登録するinfluence名。

        Returns:
            SkinCluster: 作成したラッパー。
        """
        mesh = cmds.polyCube(name=name, constructionHistory=False)[0]
        skin = hlib.getNode(cmds.skinCluster(influences, mesh, toSelectedBones=True)[0])
        cmds.setAttr(str(skin) + ".normalizeWeights", 0)
        cmds.setAttr(str(skin) + ".maintainMaxInfluences", False)
        if len(influences) == 3:
            skin.setWeights(influences, [0.4, 1.0, 0.6])
        return skin

    def _index(self, joint, skin=None):
        """influenceの物理順とは異なる論理番号を取得する。

        Args:
            joint (Joint): 登録済みinfluence。
            skin (SkinCluster | None): 対象。省略時はsetUpのskin。

        Returns:
            int: weightList内の論理番号。
        """
        skin = self.skin if skin is None else skin
        return skin.fn.indexForInfluenceObject(joint.mpath())

    def _row(self, vertex=0, skin=None):
        """指定頂点のweights配列Plugを取得する。

        Args:
            vertex (int): 頂点番号。
            skin (SkinCluster | None): 対象。省略時はsetUpのskin。

        Returns:
            MPlug: weights配列。
        """
        skin = self.skin if skin is None else skin
        return skin.getPlug("weightList").mplug().elementByLogicalIndex(vertex).child(0)

    def _indices(self, vertex=0, skin=None):
        """未作成要素を作らず既存論理番号を返す。

        Args:
            vertex (int): 頂点番号。
            skin (SkinCluster | None): 対象。

        Returns:
            set[int]: 既存weights要素の論理番号。
        """
        return set(self._row(vertex, skin).getExistingArrayAttributeIndices())

    def _inject(self, index, value, vertex=0, skin=None):
        """公開setterの検証を通さず、既存破損データをraw MPlugで再現する。

        Args:
            index (int): 登録済みまたは未登録の論理番号。
            value (float): 負値・非有限値等の保存値。
            vertex (int): 頂点番号。
            skin (SkinCluster | None): 対象。

        Returns:
            MPlug: 生成・更新した要素。
        """
        plug = self._row(vertex, skin).elementByLogicalIndex(index)
        plug.setDouble(value)
        actual = plug.asDouble()
        if math.isnan(value):
            self.assertTrue(math.isnan(actual))
        else:
            self.assertEqual(actual, value)
        return plug

    def test_cleanup_removes_negative_nan_and_infinities_without_normalization(self):
        """負値・非有限値の要素だけを除去し、1超と微小な正値を維持する。"""
        parent, child, other = [self._index(joint) for joint in (self.parent, self.child, self.other)]
        self.skin.setWeights(self.names, [1.4, 1e-8, 0.6])
        self._inject(parent, -0.25, vertex=0)
        self._inject(child, math.nan, vertex=1)
        self._inject(other, math.inf, vertex=2)
        self._inject(parent, -math.inf, vertex=3)
        self.assertIs(self.skin.removeInvalidWeights(), self.skin)
        for vertex, index in ((0, parent), (1, child), (2, other), (3, parent)):
            self.assertNotIn(index, self._indices(vertex))
        values = list(self.skin.getWeights(self.names))
        self.assertEqual(values[12:15], [1.4, 1e-8, 0.6])
        self.assertEqual(values[0:3], [0.0, 1e-8, 0.6])
        self.assertEqual(cmds.getAttr(str(self.skin) + ".normalizeWeights"), 0)
        self.assertFalse(cmds.getAttr(str(self.skin) + ".maintainMaxInfluences"))
        self.assertEqual(len(self.skin.getInfluences()), 3)

    def test_cleanup_uses_registered_sparse_logical_indices(self):
        """削除で空いた番号と未登録番号だけを除去し、疎な正規登録を保持する。"""
        old_child = self._index(self.child)
        other = self._index(self.other)
        self.skin.removeInfluence(self.child, transfer_to_parent=False)
        self.skin.setWeights([str(self.parent), str(self.other)], [1.4, 0.6])
        self.assertNotEqual(other, 1)
        self._inject(old_child, 0.75)
        self._inject(77, 0.0)
        self.skin.removeInvalidWeights()
        self.assertNotIn(old_child, self._indices())
        self.assertNotIn(77, self._indices())
        self.assertIn(other, self._indices())
        self.assertEqual(list(self.skin.getWeights([str(self.parent), str(self.other)])), [1.4, 0.6] * 8)

    def test_cleanup_is_one_undo_redo_and_restores_the_original_elements(self):
        """1回のUndoでNaNと未登録要素を復元し、Redoで再除去する。"""
        child = self._index(self.child)
        self._inject(child, math.nan)
        self._inject(77, 0.5)
        cmds.flushUndo()
        self.skin.removeInvalidWeights()
        self.assertNotIn(child, self._indices())
        self.assertNotIn(77, self._indices())
        cmds.undo()
        self.assertTrue(math.isnan(self._row().elementByLogicalIndex(child).asDouble()))
        self.assertEqual(self._row().elementByLogicalIndex(77).asDouble(), 0.5)
        cmds.redo()
        self.assertNotIn(child, self._indices())
        self.assertNotIn(77, self._indices())

    def test_force_and_f_repair_before_transfer_and_keep_the_old_return_type(self):
        """force/fは不正要素の除去と登録解除を1回のUndoへまとめる。"""
        child = self._index(self.child)
        self._inject(child, math.nan)
        self._inject(77, 0.5)
        with self.assertRaises(ValueError):
            self.skin.removeInfluence(self.child)
        self.assertTrue(self.skin.hasInfluence(str(self.child)))
        self.assertIn(77, self._indices())
        for flag in ("force", "f"):
            with self.subTest(flag=flag):
                cmds.flushUndo()
                self.assertIsNone(self.skin.removeInfluence(self.child, **{flag: True}))
                self.assertFalse(self.skin.hasInfluence(str(self.child)))
                self.assertTrue(self.child.isValid())
                self.assertNotIn(77, self._indices())
                values = list(self.skin.getWeights([str(self.parent), str(self.other)]))
                self.assertEqual(values[:2], [0.4, 0.6])
                self.assertAlmostEqual(values[2], 1.4)
                self.assertAlmostEqual(values[3], 0.6)
                cmds.undo()
                self.assertTrue(self.skin.hasInfluence(str(self.child)))
                self.assertIn(77, self._indices())
                self.assertTrue(math.isnan(self._row().elementByLogicalIndex(child).asDouble()))
                cmds.redo()
                self.assertFalse(self.skin.hasInfluence(str(self.child)))
                cmds.undo()

    def test_joint_and_collection_force_entries_keep_their_returns(self):
        """Jointの全skin委譲とSkinClusters一括処理でforceを引き継ぐ。"""
        second = self._skin("cleanupSecond", self.names)
        for skin in (self.skin, second):
            self._inject(77, 0.5, skin=skin)
        self.assertIs(self.child.removeInfluence(force=True), self.child)
        self.assertTrue(self.child.isValid())
        for skin in (self.skin, second):
            self.assertFalse(skin.hasInfluence(str(self.child)))
            self.assertNotIn(77, self._indices(skin=skin))
        cmds.undo()
        skins = hlib.nodes.SkinClusters([self.skin, second])
        self.assertIs(skins.removeInvalidWeights(), skins)
        for skin in skins:
            self.assertNotIn(77, self._indices(skin=skin))
        cmds.undo()
        self.assertIs(skins.removeInfluences(self.child, f=True), skins)
        for skin in skins:
            self.assertFalse(skin.hasInfluence(str(self.child)))
            self.assertNotIn(77, self._indices(skin=skin))

    def test_preflight_last_influence_and_unknown_influence_do_not_repair_first(self):
        """最後の登録や未登録対象の拒否は、他skinの不正除去より前に行う。"""
        self._inject(77, 0.5)
        single = self._skin("cleanupSingle", [str(self.child)])
        actions = (
            lambda: self.child.removeInfluence(force=True),
            lambda: hlib.nodes.SkinClusters([self.skin, single]).removeInfluences(self.child, force=True),
            lambda: single.removeInfluence(self.child, force=True),
        )
        for action in actions:
            with self.assertRaises(ValueError):
                action()
            self.assertIn(77, self._indices())
            self.assertTrue(self.skin.hasInfluence(str(self.child)))
            self.assertEqual(len(single.getInfluences()), 1)
        outside = hlib.getNode(cmds.createNode("joint", name="cleanupOutside"))
        with self.assertRaises(ValueError):
            self.skin.removeInfluence(outside, force=True)
        self.assertIn(77, self._indices())

    def test_flag_type_and_duplicate_alias_errors_have_no_side_effects(self):
        """不正bool型とforce/f重複を単数・Joint・複数・未使用解除で拒否する。"""
        self._inject(77, 0.5)
        skins = hlib.nodes.SkinClusters([self.skin])
        actions = (
            lambda **flags: self.skin.removeInfluence(self.child, **flags),
            lambda **flags: self.child.removeInfluence(self.skin, **flags),
            lambda **flags: skins.removeInfluences(self.child, **flags),
            lambda **flags: self.skin.removeUnusedInfluences(**flags),
        )
        for action in actions:
            for flags in ({"force": "True"}, {"f": 1}, {"force": True, "f": True}):
                with self.subTest(flags=flags):
                    with self.assertRaises(TypeError):
                        action(**flags)
                    self.assertIn(77, self._indices())
                    self.assertTrue(self.skin.hasInfluence(str(self.child)))
        with self.assertRaises(TypeError):
            self.skin.removeInvalidWeights(fast=1)
        self.assertIn(77, self._indices())

    def test_nurbs_cleanup_and_unsupported_parent_transfer_preflight(self):
        """生ウェイトの除去はNURBSにも対応し、未対応の祖先移送は修復前に拒否する。"""
        surface = cmds.nurbsPlane(name="cleanupSurface", degree=1, patchesU=1,
                                  patchesV=1, constructionHistory=False)[0]
        skin = hlib.getNode(cmds.skinCluster(self.names, surface, toSelectedBones=True)[0])
        self._inject(77, 0.5, skin=skin)
        with self.assertRaises(ValueError):
            skin.removeInfluence(self.child, force=True)
        self.assertIn(77, self._indices(skin=skin))
        self.assertTrue(skin.hasInfluence(str(self.child)))
        self.assertIs(skin.removeInvalidWeights(), skin)
        self.assertNotIn(77, self._indices(skin=skin))

    def test_locks_and_input_connections_reject_cleanup_and_force_without_unlocking(self):
        """liw・配列親・leafロック・入力接続はforceでも解除しない。"""
        self._inject(77, 0.5)
        paths = (str(self.other) + ".lockInfluenceWeights", str(self.skin) + ".weightList",
                 self._row().elementByLogicalIndex(self._index(self.parent)).name())
        for path in paths:
            is_liw = path.endswith(".lockInfluenceWeights")
            cmds.setAttr(path, True) if is_liw else cmds.setAttr(path, lock=True)
            try:
                for action in (self.skin.removeInvalidWeights, lambda: self.skin.removeInfluence(self.child, force=True)):
                    with self.assertRaises(RuntimeError):
                        action()
                    self.assertIn(77, self._indices())
                    self.assertTrue(self.skin.hasInfluence(str(self.child)))
                self.assertTrue(cmds.getAttr(path) if is_liw else cmds.getAttr(path, lock=True))
            finally:
                cmds.setAttr(path, False) if is_liw else cmds.setAttr(path, lock=False)
        driver = cmds.createNode("multDoubleLinear", name="cleanupDriver")
        weight = self._row().elementByLogicalIndex(self._index(self.parent)).name()
        cmds.connectAttr(driver + ".output", weight)
        with self.assertRaises(RuntimeError):
            self.skin.removeInvalidWeights()
        with self.assertRaises(RuntimeError):
            self.skin.removeInfluence(self.child, f=True)
        self.assertIn(77, self._indices())
        self.assertTrue(cmds.isConnected(driver + ".output", weight))

    def test_layer_and_invalid_leaf_output_connections_are_not_bypassed(self):
        """レイヤー関連接続と不正leafの出力を自動切断しない。"""
        invalid = self._inject(77, 0.5)
        layer = hlib.createNode("network", name="cleanup_ngSkinLayerData")
        socket = self.skin.addAttr("cleanupLayer", attributeType="message")
        socket.connect(layer.getPlug("message"))
        for action in (self.skin.removeInvalidWeights, lambda: self.skin.removeInfluence(self.child, force=True)):
            with self.assertRaises(RuntimeError):
                action()
            self.assertIn(77, self._indices())
        socket.disconnect()
        sink = hlib.createNode("network", name="cleanupSink").addAttr("value", attributeType="double")
        cmds.connectAttr(invalid.name(), str(sink))
        with self.assertRaises(RuntimeError):
            self.skin.removeInvalidWeights()
        with self.assertRaises(RuntimeError):
            self.skin.removeInfluence(self.child, force=True)
        self.assertIn(77, self._indices())
        self.assertTrue(cmds.isConnected(invalid.name(), str(sink)))

    def test_unused_force_keeps_joint_nodes_and_rejects_empty_registration(self):
        """未使用検索の型・順序を維持し、force解除とUndoでjointを保持する。"""
        self.skin.setWeights(self.names, [1.0, 0.0, 0.0])
        self._inject(77, 0.5)
        unused = self.skin.getUnusedInfluences()
        self.assertEqual([node.getUuid() for node in unused], [self.child.getUuid(), self.other.getUuid()])
        result = self.skin.removeUnusedInfluences(f=True)
        self.assertEqual([node.getUuid() for node in result], [node.getUuid() for node in unused])
        self.assertTrue(all(joint.isValid() for joint in (self.parent, self.child, self.other)))
        self.assertEqual(len(self.skin.getInfluences()), 1)
        self.assertNotIn(77, self._indices())
        cmds.undo()
        self.assertEqual(len(self.skin.getInfluences()), 3)
        self.assertIn(77, self._indices())
        self.skin.setWeights(self.names, [0.0, 0.0, 0.0])
        with self.assertRaises(ValueError):
            self.skin.removeUnusedInfluences(force=True)
        self.assertIn(77, self._indices())
        self.assertEqual(len(self.skin.getInfluences()), 3)

    def test_clean_noop_and_fast_cleanup_do_not_create_undo_entries(self):
        """正常データのno-opとfast除去はUndoキューへ追加しない。"""
        before = list(self.skin.getWeights(self.names))
        cmds.flushUndo()
        sentinel = cmds.createNode("network", name="cleanupUndoSentinel")
        undo_name = cmds.undoInfo(query=True, undoName=True)
        self.assertIs(self.skin.removeInvalidWeights(), self.skin)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        self.assertEqual(list(self.skin.getWeights(self.names)), before)
        self._inject(77, 0.5)
        self.assertIs(self.skin.removeInvalidWeights(fast=True), self.skin)
        self.assertNotIn(77, self._indices())
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        cmds.undo()
        self.assertFalse(cmds.objExists(sentinel))
        self.assertTrue(self.skin.isValid())
        self.assertNotIn(77, self._indices())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
