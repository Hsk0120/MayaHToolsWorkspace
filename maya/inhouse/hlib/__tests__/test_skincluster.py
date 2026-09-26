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
from hlib.decorators import undo_chunk
from hlib.maths import easing


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
    """SkinClusters(コレクション)の influence解除とJoints.delete を検証する。"""

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

    def test_delete_joints_transfers_weight_reparents_children_and_deletes_joint(self):
        self.skin.set_weights([self.root, self.mid, self.leaf], [0.0, 1.0, 0.0])

        mid_joints = Joints([self.mid])
        skin_clusters = mid_joints.skin_clusters()
        self.assertEqual([skin.name() for skin in skin_clusters], [self.skin.name()])

        mid_joints.delete()

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
        cmds.undo()
        self.assertEqual(list(self.skin.get_weights([self.root, self.child])), [1.0, 0.0] * 8)
        cmds.redo()
        self.assertEqual(list(self.skin.get_weights([self.root, self.child])), original_weights)

    def test_set_weights_undo_redo_with_flat_values(self):
        joints = [self.root, self.child]
        before = list(self.skin.get_weights(joints))
        values = [value for i in range(8) for value in (i / 16.0, 0.25)]
        self.skin.set_weights(joints, values)
        self.assertEqual(list(self.skin.get_weights(joints)), values)
        cmds.undo()
        self.assertEqual(list(self.skin.get_weights(joints)), before)
        cmds.redo()
        self.assertEqual(list(self.skin.get_weights(joints)), values)

    def test_partial_weights_and_tool_chunk(self):
        joints = [self.root, self.child]
        before = list(self.skin.get_weights(joints))
        with undo_chunk("weightTool"):
            self.skin.set_weights([self.child], [0.125])
            hlib.node(self.mesh_transform).attr("visibility").set(False)
        after = list(self.skin.get_weights(joints))
        self.assertEqual(after[0::2], before[0::2])
        self.assertEqual(after[1::2], [0.125] * 8)
        cmds.undo()
        self.assertEqual(list(self.skin.get_weights(joints)), before)
        self.assertTrue(cmds.getAttr(self.mesh_transform + ".visibility"))
        cmds.redo()
        self.assertEqual(list(self.skin.get_weights(joints)), after)
        self.assertFalse(cmds.getAttr(self.mesh_transform + ".visibility"))

    def test_sparse_influence_indices(self):
        extra = cmds.createNode("joint", parent=self.root)
        cmds.skinCluster(self.skin.name(), edit=True, addInfluence=extra, weight=0)
        cmds.skinCluster(self.skin.name(), edit=True, removeInfluence=self.child)
        before = list(self.skin.get_weights([self.root, extra]))
        self.skin.set_weights([extra, self.root], [0.25, 0.75])
        self.assertEqual(list(self.skin.get_weights([self.root, extra])), [0.75, 0.25] * 8)
        cmds.undo()
        self.assertEqual(list(self.skin.get_weights([self.root, extra])), before)

    def test_invalid_weights_do_not_partially_write(self):
        joints = [self.root, self.child]
        before = list(self.skin.get_weights(joints))
        for values in ([0.5] * 3, [float("nan"), 1], [1, float("inf")]):
            with self.assertRaises(ValueError):
                self.skin.set_weights(joints, values)
            self.assertEqual(list(self.skin.get_weights(joints)), before)

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


class SkinClusterRedistributeWeightsTest(unittest.TestCase):
    """redistribute_weights によるイージング再分配を検証する。"""

    def setUp(self):
        self.root = cmds.createNode("joint", name="hlibSkinRedistributeRoot")
        self.child = cmds.createNode("joint", name="hlibSkinRedistributeChild", parent=self.root)
        cmds.setAttr(self.child + ".translateY", 1.0)
        self.mesh_transform, _ = cmds.polyCube(name="hlibSkinRedistributeMesh")
        skin_name = cmds.skinCluster(self.root, self.child, self.mesh_transform)[0]
        self.skin = SkinCluster(skin_name)

    def tearDown(self):
        if cmds.objExists(self.mesh_transform):
            cmds.delete(self.mesh_transform)
        if cmds.objExists(self.root):
            cmds.delete(self.root)

    def test_redistribute_weights_applies_easing_and_keeps_each_vertex_normalized(self):
        self.skin.set_weights([self.root, self.child], [0.75, 0.25])

        self.skin.redistribute_weights([0, 3], method="cubic")

        eased_root = easing.ease(0.75, "cubic")
        eased_child = easing.ease(0.25, "cubic")
        eased_total = eased_root + eased_child
        expected_root = eased_root / eased_total
        expected_child = eased_child / eased_total
        weights = list(self.skin.get_weights([self.root, self.child]))
        for vertex in (0, 3):
            self.assertAlmostEqual(weights[vertex * 2], expected_root, places=9)
            self.assertAlmostEqual(weights[vertex * 2 + 1], expected_child, places=9)
        for vertex in range(8):
            if vertex in (0, 3):
                continue
            self.assertAlmostEqual(weights[vertex * 2], 0.75, places=9)
            self.assertAlmostEqual(weights[vertex * 2 + 1], 0.25, places=9)
        for vertex in range(8):
            self.assertAlmostEqual(weights[vertex * 2] + weights[vertex * 2 + 1], 1.0, places=9)

    def test_redistribute_weights_is_undoable(self):
        self.skin.set_weights([self.root, self.child], [0.75, 0.25])
        before = list(self.skin.get_weights([self.root, self.child]))

        self.skin.redistribute_weights([0], method="cubic")
        after = list(self.skin.get_weights([self.root, self.child]))
        self.assertNotEqual(after, before)

        cmds.undo()
        self.assertEqual(list(self.skin.get_weights([self.root, self.child])), before)
        cmds.redo()
        self.assertEqual(list(self.skin.get_weights([self.root, self.child])), after)

    def test_redistribute_weights_empty_vertices_is_a_noop(self):
        self.skin.set_weights([self.root, self.child], [0.75, 0.25])
        before = list(self.skin.get_weights([self.root, self.child]))

        self.skin.redistribute_weights([], method="cubic")

        self.assertEqual(list(self.skin.get_weights([self.root, self.child])), before)

    def test_redistribute_weights_accepts_every_curve_name(self):
        for curve in easing.CURVES:
            with self.subTest(curve=curve):
                self.skin.set_weights([self.root, self.child], [0.75, 0.25])

                self.skin.redistribute_weights([0], method=curve)

                weights = list(self.skin.get_weights([self.root, self.child]))
                self.assertAlmostEqual(weights[0] + weights[1], 1.0, places=9)
                if curve == "linear":
                    self.assertAlmostEqual(weights[0], 0.75, places=9)
                else:
                    # 大きい側の割合が強調され、0.75 より大きくなる。
                    self.assertGreater(weights[0], 0.75)

    def test_redistribute_weights_treats_legacy_sinusoidal_as_sine(self):
        self.skin.set_weights([self.root, self.child], [0.75, 0.25])

        self.skin.redistribute_weights([0], method="sinusoidal")
        self.skin.redistribute_weights([1], method="sine")

        weights = list(self.skin.get_weights([self.root, self.child]))
        self.assertAlmostEqual(weights[0], weights[2], places=12)
        self.assertAlmostEqual(weights[1], weights[3], places=12)
        self.assertGreater(weights[0], 0.75)

    def test_redistribute_weights_raises_for_unsupported_method_and_out_of_range_vertex(self):
        with self.assertRaises(ValueError):
            self.skin.redistribute_weights([0], method="not_a_method")
        with self.assertRaises(ValueError):
            # 旧 API の関数名接頭辞付きの名前は受け付けない。
            self.skin.redistribute_weights([0], method="ease_in_out_cubic")
        with self.assertRaises(IndexError):
            self.skin.redistribute_weights([999], method="cubic")

    def test_redistribute_weights_raises_type_error_for_non_string_method(self):
        self.skin.set_weights([self.root, self.child], [0.75, 0.25])
        before = list(self.skin.get_weights([self.root, self.child]))

        for method in (None, 3, ["cubic"]):
            with self.subTest(method=method):
                with self.assertRaises(TypeError):
                    self.skin.redistribute_weights([0], method=method)

        self.assertEqual(list(self.skin.get_weights([self.root, self.child])), before)

    def test_redistribute_weights_keeps_zero_weight_influences_at_zero(self):
        # どの曲線も ease(0) == 0 のため、効いていない influence に
        # ウェイトが新たに配られることはない。
        grandchild = cmds.createNode(
            "joint", name="hlibSkinRedistributeGrandchild", parent=self.child
        )
        cmds.setAttr(grandchild + ".translateY", 1.0)
        self.skin.add_influences(grandchild)
        influences = [self.root, self.child, grandchild]
        for curve in easing.CURVES:
            with self.subTest(curve=curve):
                self.skin.set_weights(influences, [0.75, 0.25, 0.0])

                self.skin.redistribute_weights([0], method=curve)

                weights = list(self.skin.get_weights(influences))
                self.assertEqual(weights[2], 0.0)
                self.assertAlmostEqual(weights[0] + weights[1], 1.0, places=9)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
