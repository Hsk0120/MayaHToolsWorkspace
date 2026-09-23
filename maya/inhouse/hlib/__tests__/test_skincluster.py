"""hlib.nodes.skinCluster の SkinCluster ウェイト移送APIを検証するMaya内テスト。"""

import os
import sys
import tempfile
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.nodes.joint import Joint, Joints
from hlib.nodes.skinCluster import SkinCluster


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


class SkinClusterInfluenceTest(unittest.TestCase):
    """has_influence/remove_influence/transfer_weight(単体)を検証する。"""

    def setUp(self):
        self.root = cmds.createNode("joint", name="hlibSkinInfluenceRoot")
        self.mid = cmds.createNode("joint", name="hlibSkinInfluenceMid", parent=self.root)
        cmds.setAttr(self.mid + ".translateY", 1.0)
        self.mesh_transform, _ = cmds.polyCube(name="hlibSkinInfluenceMesh")
        skin_name = cmds.skinCluster(self.root, self.mid, self.mesh_transform)[0]
        self.skin = SkinCluster(skin_name)

    def tearDown(self):
        if cmds.objExists(self.mesh_transform):
            cmds.delete(self.mesh_transform)
        if cmds.objExists(self.root):
            cmds.delete(self.root)
        cmds.select(clear=True)

    def test_has_influence_true_and_false(self):
        self.assertTrue(self.skin.has_influence(self.root))
        self.assertTrue(self.skin.has_influence(self.mid))
        self.assertFalse(self.skin.has_influence("hlibNotAnInfluence"))

    def test_transfer_weight_moves_weight_between_named_influences(self):
        self.skin.set_weights([self.root, self.mid], [0.0, 1.0])
        self.assertEqual(list(self.skin.get_weights([self.root])), [0.0] * 8)
        self.assertEqual(list(self.skin.get_weights([self.mid])), [1.0] * 8)

        self.skin.transfer_weight(self.mid, self.root)

        self.assertEqual(list(self.skin.get_weights([self.root])), [1.0] * 8)
        self.assertEqual(list(self.skin.get_weights([self.mid])), [0.0] * 8)
        # transfer_weight はウェイト移送のみで influence の削除はしない。
        self.assertIn(self.mid, self.skin.influences())

    def test_remove_influence_drops_influence_from_skin_cluster(self):
        self.assertIn(self.mid, self.skin.influences())
        self.skin.remove_influence(self.mid)
        self.assertNotIn(self.mid, self.skin.influences())
        self.assertFalse(self.skin.has_influence(self.mid))


class SkinClustersBatchTest(unittest.TestCase):
    """SkinClusters(コレクション)の gather/apply/finalize、remove_joints/remove_influences を検証する。"""

    def setUp(self):
        self.root = cmds.createNode("joint", name="hlibSkinBatchRoot")
        self.mid = cmds.createNode("joint", name="hlibSkinBatchMid", parent=self.root)
        cmds.setAttr(self.mid + ".translateY", 1.0)
        self.leaf = cmds.createNode("joint", name="hlibSkinBatchLeaf", parent=self.mid)
        cmds.setAttr(self.leaf + ".translateY", 1.0)
        self.mesh_transform, _ = cmds.polyCube(name="hlibSkinBatchMesh")
        skin_name = cmds.skinCluster(self.root, self.mid, self.leaf, self.mesh_transform)[0]
        self.skin = SkinCluster(skin_name)

    def tearDown(self):
        if cmds.objExists(self.mesh_transform):
            cmds.delete(self.mesh_transform)
        if cmds.objExists(self.root):
            cmds.delete(self.root)
        cmds.select(clear=True)

    def test_transfer_target_finds_nearest_influence_ancestor(self):
        mid_joint = Joint(self.mid)
        self.assertEqual(mid_joint.transfer_target(self.skin), self.root)

        leaf_joint = Joint(self.leaf)
        self.assertEqual(leaf_joint.transfer_target(self.skin), self.mid)

    def test_sorted_by_depth_orders_deepest_first(self):
        joints = Joints([self.root, self.mid, self.leaf])
        ordered = [joint.name() for joint in joints.sorted_by_depth()]
        self.assertEqual(ordered, [self.leaf, self.mid, self.root])

    def test_remove_joints_transfers_weight_reparents_children_and_deletes_joint(self):
        self.skin.set_weights([self.root, self.mid, self.leaf], [0.0, 1.0, 0.0])

        mid_joints = Joints([self.mid])
        skin_clusters = mid_joints.skin_clusters()
        self.assertEqual([skin.name() for skin in skin_clusters], [self.skin.name()])

        skin_clusters.remove_joints(mid_joints)

        self.assertFalse(cmds.objExists(self.mid))
        self.assertTrue(cmds.objExists(self.leaf))
        self.assertEqual(cmds.listRelatives(self.leaf, parent=True), [self.root])
        self.assertFalse(self.skin.has_influence(self.mid))
        self.assertEqual(list(self.skin.get_weights([self.root])), [1.0] * 8)

    def test_remove_influences_keeps_joint_node_but_drops_influence(self):
        self.skin.set_weights([self.root, self.mid, self.leaf], [0.0, 1.0, 0.0])

        mid_joints = Joints([self.mid])
        mid_joints.skin_clusters().remove_influences(mid_joints)

        self.assertTrue(cmds.objExists(self.mid))
        self.assertFalse(self.skin.has_influence(self.mid))
        self.assertEqual(list(self.skin.get_weights([self.root])), [1.0] * 8)
        # remove_influences は joint ノード自体を削除しないため、階層はそのまま。
        self.assertEqual(cmds.listRelatives(self.leaf, parent=True), [self.mid])


class SkinClusterDumpLoadWeightsTest(unittest.TestCase):
    """dump_weights/load_weights によるウェイトのバックアップ・復元を検証する。"""

    def setUp(self):
        self.root = cmds.createNode("joint", name="hlibSkinDumpRoot")
        self.child = cmds.createNode("joint", name="hlibSkinDumpChild", parent=self.root)
        cmds.setAttr(self.child + ".translateY", 1.0)
        self.mesh_transform, _ = cmds.polyCube(name="hlibSkinDumpMesh")
        skin_name = cmds.skinCluster(self.root, self.child, self.mesh_transform)[0]
        self.skin = SkinCluster(skin_name)
        handle, self.path = tempfile.mkstemp(suffix=".json")
        os.close(handle)

    def tearDown(self):
        if cmds.objExists(self.mesh_transform):
            cmds.delete(self.mesh_transform)
        if cmds.objExists(self.root):
            cmds.delete(self.root)
        if os.path.exists(self.path):
            os.remove(self.path)
        cmds.select(clear=True)

    def test_dump_then_load_round_trips_weights(self):
        self.skin.set_weights([self.root, self.child], [0.75, 0.25])
        original_weights = list(self.skin.get_weights([self.root, self.child]))

        self.skin.dump_weights(self.path)
        self.skin.set_weights([self.root, self.child], [1.0, 0.0])
        self.assertNotEqual(list(self.skin.get_weights([self.root, self.child])), original_weights)

        self.skin.load_weights(self.path)
        self.assertEqual(list(self.skin.get_weights([self.root, self.child])), original_weights)

    def test_load_raises_when_influence_missing(self):
        self.skin.dump_weights(self.path)
        cmds.skinCluster(self.skin.name(), edit=True, removeInfluence=self.child)

        with self.assertRaises(ValueError):
            self.skin.load_weights(self.path)

    def test_load_raises_when_vertex_count_mismatch(self):
        self.skin.dump_weights(self.path)
        cmds.polyExtrudeFacet(self.mesh_transform + ".f[0]")

        with self.assertRaises(ValueError):
            self.skin.load_weights(self.path)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
