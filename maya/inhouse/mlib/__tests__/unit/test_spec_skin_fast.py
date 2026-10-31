"""既スキン判定・setWeights の fast の約束を固定する(2.1.0 担当B)。

- SkinCluster.deforms / bind の既スキン判定は DagNode.getSkinClusters と同じ規則で、cmds.listHistory を使わない。
- setWeights(fast=True) は MFnSkinCluster.setWeights を使わず、通常経路と同じ生値・同じ既存要素になる。
"""

import unittest
from contextlib import ExitStack
from unittest.mock import patch

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import SkinCluster
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
            self.assertTrue(other.deforms(other_mesh))
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
                mlib.bindSkin([self.root, self.mid], mesh)
        fresh = cmds.polyCube(name=self.name("fresh"))[0]
        with patch.object(cmds, "listHistory", side_effect=AssertionError("listHistory")):
            bound = mlib.bindSkin([self.root, self.mid], fresh, maximumInfluences=2)
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
