"""Hlib.nodes.skincluster の SkinCluster ウェイト移送APIを検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import Hlib
Hlib.reload()
from Hlib.nodes.skincluster import SkinCluster


class SkinClusterTransferWeightsBatchTest(unittest.TestCase):
    """transfer_weights_batch が preserved_selection 経由で選択状態を保存・復元することを検証する。"""

    def setUp(self):
        self.root = cmds.createNode("joint", name="hlibSkinClusterRoot")
        self.child = cmds.createNode("joint", name="hlibSkinClusterChild", parent=self.root)
        cmds.setAttr(self.child + ".translateY", 1.0)
        self.mesh_transform, _ = cmds.polyCube(name="hlibSkinClusterMesh")
        skin_name = cmds.skinCluster(self.root, self.child, self.mesh_transform)[0]
        self.skin = SkinCluster(skin_name)

    def tearDown(self):
        if cmds.objExists(self.mesh_transform):
            cmds.delete(self.mesh_transform)
        if cmds.objExists(self.root):
            cmds.delete(self.root)
        cmds.select(clear=True)

    def test_restores_prior_selection_after_transfer(self):
        cmds.select(self.mesh_transform, replace=True)

        self.skin.transfer_weights_batch([(self.child, self.root)])

        self.assertEqual(cmds.ls(sl=True, long=True), cmds.ls(self.mesh_transform, long=True))

    def test_restores_empty_selection_when_nothing_was_selected(self):
        cmds.select(clear=True)

        self.skin.transfer_weights_batch([(self.child, self.root)])

        self.assertEqual(cmds.ls(sl=True), [])

    def test_influences_still_include_both_joints_after_transfer(self):
        # transfer_weights_batch はウェイト移送のみを行い influence の削除はしない。
        self.skin.transfer_weights_batch([(self.child, self.root)])

        self.assertIn(self.child, self.skin.influences())
        self.assertIn(self.root, self.skin.influences())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
