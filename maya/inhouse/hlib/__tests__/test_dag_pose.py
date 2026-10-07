"""DagPoseの保存・復元・メンバー編集とUndoを実Mayaで検証する。"""

import sys
import unittest
import uuid
from unittest import mock

import hlib
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace

hlib.reload()


class DagPoseTest(unittest.TestCase):
    def setUp(self):
        self.ns = "hlibPose_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.root = cmds.createNode("joint", name=self.ns + ":root")
        self.child = cmds.createNode("joint", name=self.ns + ":child", parent=self.root)
        cmds.setAttr(self.root + ".tx", 10)
        cmds.setAttr(self.child + ".tx", 3)

    def tearDown(self):
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def pose(self, **kwargs):
        return hlib.nodes.DagPose.create(self.root, name=self.ns + ":pose", **kwargs)

    def test_discovery_and_matrices(self):
        pose = self.pose()
        self.assertIsInstance(hlib.getNode(pose.getFullName()), hlib.nodes.DagPose)
        self.assertFalse(pose.isBindPose())
        self.assertEqual(len(pose.getMembers()), 2)

        self.assertEqual(pose.getMemberIndices(), [0, 1])
        self.assertEqual(list(pose.getMatrix(self.child)), cmds.getAttr(self.child + ".matrix"))
        self.assertEqual(list(pose.getMatrix(self.child, ws=True)), cmds.getAttr(self.child + ".worldMatrix[0]"))
        self.assertTrue(pose.isAtPose())
        cmds.setAttr(self.child + ".ty", 4)
        self.assertEqual([x.getFullName() for x in pose.getNotAtPose()], [hlib.getNode(self.child).getFullName()])
        self.assertFalse(pose.isAtPose())

    def test_sparse_member_indices(self):
        pose = self.pose()
        extra = cmds.createNode("transform", name=self.ns + ":extra")
        pose.addMembers(extra)
        extra_index = pose.getMemberIndex(extra)
        pose.removeMembers(self.child)
        self.assertEqual(pose.getMemberIndices(), [0, extra_index])
        self.assertEqual(pose.getMemberIndex(extra), extra_index)
        self.assertEqual(list(pose.getMatrix(extra)), cmds.getAttr(extra + ".matrix"))

    def test_restore_undo_redo(self):
        pose = self.pose()
        cmds.setAttr(self.child + ".ty", 4)
        pose.restore()
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 0)
        cmds.undo()
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 4)
        cmds.redo()
        self.assertTrue(pose.isAtPose())
        cmds.setAttr(self.root + ".tx", 20)
        pose.restore(ws=True)
        self.assertAlmostEqual(cmds.getAttr(self.root + ".tx"), 10)

    def test_reset_undo_redo(self):
        pose = self.pose()
        before = list(pose.getMatrix(self.child))
        cmds.setAttr(self.child + ".ty", 4)
        pose.reset(self.child)
        after = list(pose.getMatrix(self.child))
        self.assertNotEqual(before, after)
        self.assertTrue(pose.isAtPose())
        cmds.undo()
        self.assertEqual(list(pose.getMatrix(self.child)), before)
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 4)
        cmds.redo()
        self.assertEqual(list(pose.getMatrix(self.child)), after)

    def test_members_and_validation(self):
        pose = self.pose(hierarchy=False)
        self.assertEqual(len(pose.getMembers()), 1)
        pose.addMembers(self.child)
        self.assertEqual(len(pose.getMembers()), 2)
        cmds.undo()
        self.assertEqual(len(pose.getMembers()), 1)
        cmds.redo()
        pose.removeMembers(self.child)
        self.assertTrue(cmds.objExists(self.child))
        self.assertEqual(len(pose.getMembers()), 1)
        cmds.undo()
        self.assertEqual(len(pose.getMembers()), 2)
        with self.assertRaises(ValueError):
            pose.addMembers([])
        other = cmds.createNode("transform", name=self.ns + ":other")
        with self.assertRaises(ValueError):
            pose.reset([self.root, other])
        with self.assertRaises(ValueError):
            pose.removeMembers([self.root, other])
        self.assertEqual(len(pose.getMembers()), 2)

    def test_bind_pose_and_skin_matrices(self):
        mesh = cmds.polyCube(name=self.ns + ":mesh")[0]
        skin = cmds.skinCluster([self.root, self.child], mesh, name=self.ns + ":skin")[0]
        pose_name = cmds.listConnections(skin + ".bindPose", source=True, destination=False)[0]
        cmds.rename(pose_name, self.ns + ":bindPose")
        pose = hlib.getNode(self.ns + ":bindPose")
        self.assertEqual(hlib.nodes.DagPose.fromSkinCluster(skin).getFullName(), pose.getFullName())
        self.assertTrue(pose.isBindPose())
        self.assertEqual([x.getFullName() for x in pose.getSkinClusters()], [skin])
        before = cmds.getAttr(skin + ".bindPreMatrix[1]")
        cmds.setAttr(self.child + ".ty", 4)
        pose.reset()
        self.assertEqual(cmds.getAttr(skin + ".bindPreMatrix[1]"), before)
        self.assertTrue(pose.isAtPose())
        cmds.disconnectAttr(pose.getFullName() + ".message", skin + ".bindPose")
        self.assertIsNone(hlib.nodes.DagPose.fromSkinCluster(skin))
        with self.assertRaises(ValueError):
            hlib.nodes.DagPose.fromSkinCluster(self.root)

    def make_skin(self):
        mesh = cmds.polyCube(name=self.ns + ":mesh")[0]
        name = cmds.skinCluster([self.root, self.child], mesh, name=self.ns + ":skin")[0]
        skin = hlib.getNode(name)
        cmds.rename(skin.getBindPose().getFullName(), self.ns + ":bindPose")
        return skin

    def test_skin_restore_and_bulk(self):
        skin = self.make_skin()
        pose = skin.getBindPose()
        self.assertIsInstance(pose, hlib.nodes.DagPose)
        cmds.setAttr(self.child + ".ty", 4)
        self.assertIs(skin.restoreBindPose(), skin)
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 0)
        cmds.undo()
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 4)
        cmds.redo()
        self.assertTrue(pose.isAtPose())
        skins = hlib.nodes.SkinClusters([skin])
        self.assertEqual(skins.getBindPose()[0].getFullName(), pose.getFullName())
        cmds.setAttr(self.child + ".ty", 7)
        self.assertEqual(len(skins.restoreBindPose(ws=False)), 1)
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 0)
        cmds.undo()
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 7)

    def test_skin_reset_scope_undo_and_missing_pose(self):
        skin = self.make_skin()
        pose = skin.getBindPose()
        other = cmds.createNode("transform", name=self.ns + ":other")
        pose.addMembers(other)
        old_other = list(pose.getMatrix(other))
        old_child = list(pose.getMatrix(self.child))
        old_bind = cmds.getAttr(skin.getFullName() + ".bindPreMatrix[1]")
        cmds.setAttr(other + ".ty", 9)
        cmds.setAttr(self.child + ".ty", 4)
        self.assertIs(skin.resetBindPose(), skin)
        self.assertEqual(list(pose.getMatrix(other)), old_other)
        self.assertNotEqual(list(pose.getMatrix(self.child)), old_child)
        self.assertEqual(cmds.getAttr(skin.getFullName() + ".bindPreMatrix[1]"), old_bind)
        cmds.undo()
        self.assertEqual(list(pose.getMatrix(self.child)), old_child)
        cmds.redo()
        self.assertNotEqual(list(pose.getMatrix(self.child)), old_child)
        pose.removeMembers(self.child)
        root_before = list(pose.getMatrix(self.root))
        cmds.setAttr(self.root + ".ty", 2)
        with self.assertRaises(ValueError):
            skin.resetBindPose()
        self.assertEqual(list(pose.getMatrix(self.root)), root_before)
        cmds.disconnectAttr(pose.getFullName() + ".message", skin.getFullName() + ".bindPose")
        self.assertIsNone(skin.getBindPose())
        with self.assertRaises(RuntimeError):
            skin.restoreBindPose()
        with self.assertRaises(RuntimeError):
            skin.resetBindPose()

    def test_explicit_targets_and_creation_undo(self):
        other = cmds.createNode("transform", name=self.ns + ":other")
        cmds.select(other)
        pose = self.pose(bindPose=True)
        name = pose.getFullName()
        self.assertTrue(pose.isBindPose())
        self.assertNotIn(hlib.getNode(other), pose.getMembers())
        self.assertEqual(cmds.ls(selection=True), [other])
        cmds.undo()
        self.assertFalse(cmds.objExists(name))
        cmds.redo()
        self.assertTrue(cmds.objExists(name))

    def test_merge_saved_data_skin_and_undo(self):
        target = self.pose(hierarchy=False)
        cmds.setAttr(self.child + ".jointOrient", 12, 23, 34)
        cmds.setAttr(self.child + ".rotatePivot", 1, 2, 3)
        source = hlib.nodes.DagPose.create([self.root, self.child], hierarchy=False,
                                         name=self.ns + ":source")
        saved = source._merge_snapshot()
        cmds.setAttr(self.child + ".ty", 8)
        skin = self.make_skin()
        cmds.connectAttr(source.getFullName() + ".message", skin.getFullName() + ".bindPose", force=True)
        bind = cmds.getAttr(skin.getFullName() + ".bindPreMatrix[1]")
        weights = list(skin.getWeights(skin.getInfluences()))
        self.assertIs(target.merge([source, source, target], deleteSources=False), target)
        self.assertEqual(len(target.getMembers()), 2)
        self.assertTrue(target._merge_rows_equal(saved[hlib.getNode(self.child).getFullName()],
                                                target._merge_snapshot()[hlib.getNode(self.child).getFullName()]))
        self.assertEqual(skin.getBindPose(), target)
        self.assertEqual(cmds.getAttr(self.child + ".ty"), 8)
        self.assertEqual(cmds.getAttr(skin.getFullName() + ".bindPreMatrix[1]"), bind)
        self.assertEqual(list(skin.getWeights(skin.getInfluences())), weights)
        cmds.undo()
        self.assertEqual(len(target.getMembers()), 1)
        self.assertEqual(skin.getBindPose(), source)
        cmds.redo()
        self.assertEqual(len(target.getMembers()), 2)
        target.restore()
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 0)
        for value, expected in zip(cmds.getAttr(self.child + ".jointOrient")[0], (12, 23, 34)):
            self.assertAlmostEqual(value, expected)

    def test_merge_conflict_and_current_pose_delete(self):
        target = self.pose()
        cmds.setAttr(self.root + ".ty", 4)
        source = hlib.nodes.DagPose.create(self.root, name=self.ns + ":source")
        original = target._merge_snapshot()
        with self.assertRaises(ValueError):
            target.merge(source, deleteSources=True)
        self.assertEqual(target._merge_snapshot(), original)
        cmds.setAttr(self.child + ".ty", 7)
        source_name = source.getFullName()
        target.merge(source_name, currentPose=True, deleteSources=True)
        self.assertTrue(target.isAtPose())
        self.assertFalse(cmds.objExists(source_name))
        cmds.undo()
        self.assertEqual(target._merge_snapshot(), original)
        self.assertTrue(cmds.objExists(source_name))
        self.assertEqual(cmds.getAttr(self.child + ".ty"), 7)
        cmds.redo()
        self.assertTrue(target.isAtPose())
        self.assertFalse(cmds.objExists(source_name))

    def test_merge_guards(self):
        target = self.pose()
        source = hlib.nodes.DagPose.create(self.root, name=self.ns + ":source")
        other = cmds.createNode("network", name=self.ns + ":consumer")
        cmds.addAttr(other, longName="pose", attributeType="message")
        cmds.connectAttr(source.getFullName() + ".message", other + ".pose")
        with self.assertRaises(RuntimeError):
            target.merge(source, deleteSources=True)
        for kwargs in ({"currentPose": 1}, {"deleteSources": "yes"}):
            with self.assertRaises(ValueError):
                target.merge(source, **kwargs)
        with self.assertRaises(ValueError):
            target.merge(self.root)
        with self.assertRaises(ValueError):
            target.merge([])
        cmds.setAttr(target.getFullName() + ".xformMatrix", lock=True)
        with self.assertRaises(RuntimeError):
            target.merge(source)
        cmds.setAttr(target.getFullName() + ".xformMatrix", lock=False)
        target.merge(source, deleteSources=False)
        self.assertTrue(cmds.isConnected(source.getFullName() + ".message", other + ".pose"))

    def test_merge_bind_poses_delete_and_rollback(self):
        skin = self.make_skin()
        target = skin.getBindPose()
        extra = cmds.createNode("joint", name=self.ns + ":extra")
        mesh = cmds.polyCube(name=self.ns + ":otherMesh")[0]
        other_skin = hlib.getNode(cmds.skinCluster(extra, mesh, name=self.ns + ":otherSkin")[0])
        source = other_skin.getBindPose()
        cmds.rename(source.getFullName(), self.ns + ":otherPose")
        source_name = source.getFullName()
        before_nodes = set(cmds.ls())
        before_members = target.getMembers()
        original_connect = cmds.connectAttr

        def fail_skin_connect(src, dst, **kwargs):
            if dst == other_skin.getFullName() + ".bindPose":
                raise RuntimeError("Injected connection failure")
            return original_connect(src, dst, **kwargs)

        with mock.patch("maya.cmds.connectAttr", side_effect=fail_skin_connect):
            with self.assertRaisesRegex(RuntimeError, "Injected"):
                target.merge(source, currentPose=True, deleteSources=True)
        self.assertEqual(set(cmds.ls()), before_nodes)
        self.assertEqual(target.getMembers(), before_members)
        self.assertEqual(other_skin.getBindPose(), source)
        target.merge([source_name, target.getFullName()])
        self.assertFalse(cmds.objExists(source_name))
        self.assertEqual(other_skin.getBindPose(), target)
        self.assertEqual(skin.getBindPose(), target)
        self.assertIn(hlib.getNode(extra), target.getMembers())
        cmds.undo()
        self.assertTrue(cmds.objExists(source_name))
        self.assertEqual(other_skin.getBindPose().getFullName(), source_name)
        cmds.redo()
        self.assertFalse(cmds.objExists(source_name))

    def test_merge_current_hierarchy_and_sparse_indices(self):
        target = self.pose()
        extra = cmds.createNode("transform", name=self.ns + ":extra")
        target.addMembers(extra)
        target.removeMembers(self.child)
        extra_index = target.getMemberIndex(extra)
        source = hlib.nodes.DagPose.create(self.root, name=self.ns + ":source")
        target.merge(source, deleteSources=False)
        self.assertEqual(target.getMemberIndex(extra), extra_index)
        self.assertGreater(target.getMemberIndex(self.child), extra_index)
        # 同じメンバーの保存済み親だけが異なる場合も通常統合は拒否する。
        cmds.parent(self.child, extra)
        source.reset()
        with self.assertRaises(ValueError):
            target.merge(source)
        target.merge(source, currentPose=True)
        index = target.getMemberIndex(self.child)
        parent_index = target.getMemberIndex(extra)
        self.assertTrue(cmds.isConnected(
            f"{target.getFullName()}.members[{parent_index}]",
            f"{target.getFullName()}.parents[{index}]"))
        self.assertTrue(target.isAtPose())

    def test_merge_current_bind_pose_preserves_skinning(self):
        skin = self.make_skin()
        target = skin.getBindPose()
        source = hlib.nodes.DagPose.create(self.root, name=self.ns + ":source")
        cmds.setAttr(source.getFullName() + ".bindPose", True)
        before_source = source._merge_snapshot()
        original_pose = target._merge_snapshot()
        bind = cmds.getAttr(skin.getFullName() + ".bindPreMatrix[1]")
        joint_bind = cmds.getAttr(self.child + ".bindPose")
        weights = list(skin.getWeights(skin.getInfluences()))
        cmds.setAttr(self.child + ".ty", 4)
        cmds.setAttr(self.root + ".rz", 35)
        mesh = cmds.listConnections(skin.getFullName() + ".outputGeometry[0]", shapes=True)[0]
        points = cmds.xform(mesh + ".vtx[*]", query=True, translation=True, worldSpace=True)
        target.merge(source, currentPose=True, deleteSources=False)
        self.assertTrue(target.isAtPose())
        self.assertEqual(source._merge_snapshot(), before_source)
        self.assertEqual(cmds.getAttr(skin.getFullName() + ".bindPreMatrix[1]"), bind)
        self.assertEqual(cmds.getAttr(self.child + ".bindPose"), joint_bind)
        self.assertEqual(list(skin.getWeights(skin.getInfluences())), weights)
        self.assertEqual(cmds.xform(mesh + ".vtx[*]", query=True, translation=True, worldSpace=True), points)
        cmds.undo()
        self.assertEqual(target._merge_snapshot(), original_pose)
        self.assertTrue(cmds.isConnected(self.child + ".bindPose",
                                        f"{target.getFullName()}.worldMatrix[{target.getMemberIndex(self.child)}]"))
        cmds.redo()
        self.assertTrue(target.isAtPose())

    def test_merge_equal_matrix_different_xform_conflicts(self):
        target = self.pose()
        # 回転がゼロでも回転順の違いは保存データとして保持する。
        cmds.setAttr(self.child + ".rotateOrder", 5)
        source = hlib.nodes.DagPose.create(self.root, name=self.ns + ":source")
        self.assertEqual(list(target.getMatrix(self.child)), list(source.getMatrix(self.child)))
        before = target._merge_snapshot()
        with self.assertRaises(ValueError):
            target.merge(source)
        self.assertEqual(target._merge_snapshot(), before)

    def test_merge_units_and_full_transform_restore(self):
        target = self.pose(hierarchy=False)
        original_linear = cmds.currentUnit(query=True, linear=True)
        original_angle = cmds.currentUnit(query=True, angle=True)
        try:
            cmds.currentUnit(linear="m", angle="rad")
            cmds.setAttr(self.child + ".rotateOrder", 4)
            cmds.setAttr(self.child + ".rotate", 0.2, -0.5, 0.8)
            cmds.setAttr(self.child + ".jointOrient", 0.3, 0.1, 0.4)
            cmds.setAttr(self.child + ".rotateAxis", 0.1, 0.2, 0.3)
            cmds.setAttr(self.child + ".rotatePivot", 0.4, 0.5, 0.6)
            source = hlib.nodes.DagPose.create([self.root, self.child], hierarchy=False,
                                             name=self.ns + ":source")
            attrs = ("translate", "rotate", "rotateOrder", "jointOrient", "rotateAxis", "rotatePivot")
            saved = {a: cmds.getAttr(self.child + "." + a) for a in attrs}
            cmds.setAttr(self.child + ".ty", 3)
            cmds.setAttr(self.child + ".rotate", 0, 0, 0)
            target.merge(source)
            target.restore()
            for attr, value in saved.items():
                current = cmds.getAttr(self.child + "." + attr)
                if isinstance(value, list):
                    for a, b in zip(current[0], value[0]):
                        self.assertAlmostEqual(a, b, places=8, msg=attr)
                else:
                    self.assertEqual(current, value)
        finally:
            cmds.currentUnit(linear=original_linear, angle=original_angle)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
