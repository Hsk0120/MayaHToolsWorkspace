"""SkinClusters.removeInfluences の fast と、既スキン判定・setWeights の fast の約束を固定する(2.1.0 担当B)。

- removeInfluences(fast=True) は単数 removeInfluence へ fast を渡し、cmds を呼ばず Undo に記録しない。
  通常経路と同じウェイト・登録になり、通常経路は Undo 1 回で戻る。
- 未対応(geometry が 2 個の skinCluster)は、どの skinCluster も変更する前に NotImplementedError。
- SkinCluster.deforms / bind の既スキン判定は DagNode.getSkinClusters と同じ規則で、cmds.listHistory を使わない。
- setWeights(fast=True) は MFnSkinCluster.setWeights を使わず、通常経路と同じ生値・同じ既存要素になる。
"""

import unittest
from contextlib import ExitStack
from unittest.mock import patch

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import SkinCluster, SkinClusters
from support.specCase import NamespaceCase


class _SkinCase(NamespaceCase):
    """3本の joint(root→mid→tip)と、それにバインドした円柱を作る。"""

    PREFIX = "mlibSpecSkinFast_"

    def setUp(self):
        super().setUp()
        self.selection = cmds.ls(selection=True, long=True)
        self.root = self.make("joint", "root")
        self.mid = self.make("joint", "mid", parent=self.root)
        self.tip = self.make("joint", "tip", parent=self.mid)
        cmds.setAttr(self.mid + ".ty", 1)
        cmds.setAttr(self.tip + ".ty", 1)
        self.other = self.make("joint", "other")

    def tearDown(self):
        if self.selection:
            cmds.select(self.selection, replace=True)
        else:
            cmds.select(clear=True)
        super().tearDown()

    def skin(self, joints=None, height=2):
        mesh = cmds.polyCylinder(name=self.name("mesh#"), height=height, subdivisionsHeight=4)[0]
        cmds.move(0, 1, 0, mesh)
        joints = joints or [self.root, self.mid, self.tip, self.other]
        skin = cmds.skinCluster(joints, mesh, toSelectedBones=True)[0]
        cmds.select(clear=True)
        return mesh, SkinCluster(skin)

    def raw(self, skin):
        """weightList の既存要素と値を、論理番号つきで返す。"""
        name = skin.getFullName()
        rows = []
        for vertex in cmds.getAttr(name + ".weightList", multiIndices=True) or []:
            prefix = "{}.weightList[{}].weights".format(name, vertex)
            indices = cmds.getAttr(prefix, multiIndices=True) or []
            rows.append({index: round(cmds.getAttr("{}[{}]".format(prefix, index)), 9) for index in indices})
        return rows

    def no_cmds(self, *names):
        stack = ExitStack()
        for name in names:
            stack.enter_context(patch.object(cmds, name, side_effect=AssertionError(name)))
        return stack


class RemoveInfluencesFastTest(_SkinCase):

    def test_fast_matches_normal(self):
        """transferToParent の両方で、fast と通常は同じ登録・ウェイトになる。

        transferToParent=False で複数を続けて外すと、残りの合計が 0 になった頂点の再配分が
        単数 removeInfluence の fast(core/skinEdit)と cmds で異なるため、False は 1 本だけ外す。
        """
        for transfer, joints in ((True, [self.tip, self.mid]), (False, [self.tip])):
            with self.subTest(transferToParent=transfer):
                _, normal = self.skin()
                _, fast = self.skin()
                SkinClusters([normal]).removeInfluences(joints, transferToParent=transfer)
                cmds.setAttr(self.make() + ".tx", 3)
                undo_name = cmds.undoInfo(query=True, undoName=True)
                with self.no_cmds("skinCluster", "skinPercent", "setAttr", "undoInfo"):
                    result = SkinClusters([fast]).removeInfluences(joints, transferToParent=transfer, fast=True)
                self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
                self.assertIsInstance(result, SkinClusters)
                self.assertEqual([node.getFullName() for node in fast.getInfluences()],
                                 [node.getFullName() for node in normal.getInfluences()])
                names = [self.root, self.other]
                for value, expected in zip(fast.getWeights(names), normal.getWeights(names)):
                    self.assertAlmostEqual(value, expected, places=9)

    def test_normal_undo_once(self):
        """通常経路は Undo 1 回で登録とウェイトが戻る。"""
        _, skin = self.skin()
        before = list(skin.getWeights([self.root, self.mid, self.tip, self.other]))
        cmds.flushUndo()
        SkinClusters([skin]).removeInfluences([self.tip, self.mid])
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibSkinClustersRemoveInfluences")
        cmds.undo()
        self.assertEqual(len(skin.getInfluences()), 4)
        self.assertSequenceAlmostEqual(skin.getWeights([self.root, self.mid, self.tip, self.other]), before)

    def test_fast_not_implemented_before_any_change(self):
        """2つ目の skinCluster が geometry を 2 個持つと、1つ目も変更しない。"""
        _, first = self.skin()
        _, second = self.skin()
        extra = cmds.polyCube(name=self.name("extra"))[0]
        cmds.skinCluster(second.getFullName(), edit=True, geometry=extra)
        before = self.raw(first)
        with self.assertRaises(NotImplementedError):
            SkinClusters([first, second]).removeInfluences(self.tip, fast=True)
        self.assertEqual(len(first.getInfluences()), 4)
        self.assertEqual(self.raw(first), before)

    def test_fast_type_and_validation(self):
        """fast は bool だけ。全登録の解除は fast でも変更前に ValueError。"""
        _, skin = self.skin([self.root, self.mid])
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            SkinClusters([skin]).removeInfluences(self.mid, fast=1)
        with self.assertRaises(ValueError):
            SkinClusters([skin]).removeInfluences([self.root, self.mid], fast=True)
        self.assertEqual(len(skin.getInfluences()), 2)


class SkinQueryTest(_SkinCase):

    def test_deforms_without_history_command(self):
        """deforms は getSkinClusters の規則で判定し、cmds.listHistory を呼ばない。"""
        mesh, skin = self.skin()
        other_mesh, other = self.skin()
        shape = cmds.listRelatives(mesh, shapes=True, noIntermediate=True, fullPath=True)[0]
        with self.no_cmds("listHistory", "ls"):
            self.assertTrue(skin.deforms(mesh))
            self.assertTrue(skin.deforms(shape))
            self.assertFalse(skin.deforms(other_mesh))
            # joint は influence であっても変形対象ではない。
            self.assertFalse(skin.deforms(self.root))
            # DAG ノード以外は False。
            self.assertFalse(skin.deforms(skin))
            self.assertEqual(SkinClusters([skin, other]).deforms(other_mesh), [False, True])
        with self.assertRaises(RuntimeError):
            skin.deforms(self.name("missing"))

    def test_deforms_matches_get_skin_clusters(self):
        """deforms の結果は DagNode.getSkinClusters に含まれるかと一致する。"""
        mesh, skin = self.skin()
        node = mlib.getNode(mesh)
        self.assertEqual([found.getUuid() for found in node.getSkinClusters()], [skin.getUuid()])
        self.assertTrue(skin.deforms(node))

    def test_bind_rejects_skinned_geometry(self):
        """bind は既スキンの形状を listHistory を使わずに拒否する。"""
        mesh, _ = self.skin()
        with patch.object(cmds, "listHistory", side_effect=AssertionError("listHistory")):
            with self.assertRaisesRegex(ValueError, "already has a skinCluster"):
                SkinCluster.bind(mesh, [self.root, self.mid])
        fresh = cmds.polyCube(name=self.name("fresh"))[0]
        with patch.object(cmds, "listHistory", side_effect=AssertionError("listHistory")):
            bound = SkinCluster.bind(fresh, [self.root, self.mid], maxInfluences=2)
        self.assertTrue(bound.deforms(fresh))


class SkinMfnTest(_SkinCase):

    def test_mfn_returns_new_function_set(self):
        """mfn() は呼ぶたびに新しい MFnSkinCluster を返し、公開属性 fn は無い。"""
        import maya.api.OpenMayaAnim as oma2

        _, skin = self.skin()
        first, second = skin.mfn(), skin.mfn()
        self.assertIsInstance(first, oma2.MFnSkinCluster)
        self.assertIsNot(first, second)
        self.assertEqual(first.name(), second.name())
        self.assertEqual(len(first.influenceObjects()), 4)
        self.assertFalse(hasattr(skin, "fn"))
        self.assertEqual(len(SkinClusters([skin]).mfn()), 1)


class SetWeightsFastTest(_SkinCase):

    def test_fast_matches_normal_raw_values(self):
        """normalizeWeights の各設定と liw で、fast は通常と同じ値・同じ既存要素になる。

        MFnSkinCluster.setWeights(normalize=False) は normalizeWeights=interactive で
        未指定列を書き換え、0 の要素を削除するため、fast は MPlug への直接書込みを続ける。
        """
        for mode in (0, 1, 2):
            for locked in (False, True):
                with self.subTest(normalizeWeights=mode, lockInfluenceWeights=locked):
                    results = []
                    for fast in (False, True):
                        _, skin = self.skin()
                        cmds.setAttr(skin.getFullName() + ".normalizeWeights", mode)
                        cmds.setAttr(self.tip + ".liw", locked)
                        count = cmds.polyEvaluate(skin.mesh, vertex=True)
                        values = []
                        for vertex in range(count):
                            values += [0.0 if vertex % 2 else 0.3, 0.0 if vertex % 3 else 0.9]
                        skin.setWeights([self.tip, self.root], values, fast=fast)
                        results.append(self.raw(skin))
                        cmds.setAttr(self.tip + ".liw", False)
                    self.assertEqual(results[0], results[1])


if __name__ == "__main__":
    unittest.main()
