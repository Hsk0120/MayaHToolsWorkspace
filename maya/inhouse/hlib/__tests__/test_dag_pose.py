"""DagPoseの保存・復元・メンバー編集とUndoを実Mayaで検証する。"""
import sys
import unittest
import uuid

import maya.cmds as cmds
import hlib

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
        self.assertIsInstance(hlib.node(pose.full_name), hlib.nodes.DagPose)
        self.assertFalse(pose.is_bind_pose())
        self.assertEqual(len(pose.members()), 2)

        self.assertEqual(pose.member_indices(), [0, 1])
        self.assertEqual(list(pose.get_matrix(self.child)), cmds.getAttr(self.child + ".matrix"))
        self.assertEqual(list(pose.get_matrix(self.child, ws=True)), cmds.getAttr(self.child + ".worldMatrix[0]"))
        self.assertTrue(pose.is_at_pose())
        cmds.setAttr(self.child + ".ty", 4)
        self.assertEqual([x.full_name for x in pose.not_at_pose()], [hlib.node(self.child).full_name])
        self.assertFalse(pose.is_at_pose())

    def test_sparse_member_indices(self):
        pose = self.pose()
        extra = cmds.createNode("transform", name=self.ns + ":extra")
        pose.add(extra)
        extra_index = pose.member_index(extra)
        pose.remove(self.child)
        self.assertEqual(pose.member_indices(), [0, extra_index])
        self.assertEqual(pose.member_index(extra), extra_index)
        self.assertEqual(list(pose.get_matrix(extra)), cmds.getAttr(extra + ".matrix"))

    def test_restore_undo_redo(self):
        pose = self.pose()
        cmds.setAttr(self.child + ".ty", 4)
        pose.restore()
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 0)
        cmds.undo()
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 4)
        cmds.redo()
        self.assertTrue(pose.is_at_pose())
        cmds.setAttr(self.root + ".tx", 20)
        pose.restore(ws=True)
        self.assertAlmostEqual(cmds.getAttr(self.root + ".tx"), 10)

    def test_reset_undo_redo(self):
        pose = self.pose()
        before = list(pose.get_matrix(self.child))
        cmds.setAttr(self.child + ".ty", 4)
        pose.reset(self.child)
        after = list(pose.get_matrix(self.child))
        self.assertNotEqual(before, after)
        self.assertTrue(pose.is_at_pose())
        cmds.undo()
        self.assertEqual(list(pose.get_matrix(self.child)), before)
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 4)
        cmds.redo()
        self.assertEqual(list(pose.get_matrix(self.child)), after)

    def test_members_and_validation(self):
        pose = self.pose(hierarchy=False)
        self.assertEqual(len(pose.members()), 1)
        pose.add(self.child)
        self.assertEqual(len(pose.members()), 2)
        cmds.undo()
        self.assertEqual(len(pose.members()), 1)
        cmds.redo()
        pose.remove(self.child)
        self.assertTrue(cmds.objExists(self.child))
        self.assertEqual(len(pose.members()), 1)
        cmds.undo()
        self.assertEqual(len(pose.members()), 2)
        with self.assertRaises(ValueError):
            pose.add([])
        other = cmds.createNode("transform", name=self.ns + ":other")
        with self.assertRaises(ValueError):
            pose.reset([self.root, other])
        with self.assertRaises(ValueError):
            pose.remove([self.root, other])
        self.assertEqual(len(pose.members()), 2)

    def test_bind_pose_and_skin_matrices(self):
        mesh = cmds.polyCube(name=self.ns + ":mesh")[0]
        skin = cmds.skinCluster([self.root, self.child], mesh, name=self.ns + ":skin")[0]
        pose_name = cmds.listConnections(skin + ".bindPose", source=True, destination=False)[0]
        cmds.rename(pose_name, self.ns + ":bindPose")
        pose = hlib.node(self.ns + ":bindPose")
        self.assertEqual(hlib.nodes.DagPose.from_skin_cluster(skin).full_name, pose.full_name)
        self.assertTrue(pose.is_bind_pose())
        self.assertEqual([x.full_name for x in pose.skin_clusters()], [skin])
        before = cmds.getAttr(skin + ".bindPreMatrix[1]")
        cmds.setAttr(self.child + ".ty", 4)
        pose.reset()
        self.assertEqual(cmds.getAttr(skin + ".bindPreMatrix[1]"), before)
        self.assertTrue(pose.is_at_pose())
        cmds.disconnectAttr(pose.full_name + ".message", skin + ".bindPose")
        self.assertIsNone(hlib.nodes.DagPose.from_skin_cluster(skin))
        with self.assertRaises(ValueError):
            hlib.nodes.DagPose.from_skin_cluster(self.root)

    def make_skin(self):
        mesh = cmds.polyCube(name=self.ns + ":mesh")[0]
        name = cmds.skinCluster([self.root, self.child], mesh, name=self.ns + ":skin")[0]
        skin = hlib.node(name)
        cmds.rename(skin.bind_pose().full_name, self.ns + ":bindPose")
        return skin

    def test_skin_restore_and_bulk(self):
        skin = self.make_skin()
        pose = skin.bind_pose()
        self.assertIsInstance(pose, hlib.nodes.DagPose)
        cmds.setAttr(self.child + ".ty", 4)
        self.assertIs(skin.restore_bind_pose(), skin)
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 0)
        cmds.undo()
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 4)
        cmds.redo()
        self.assertTrue(pose.is_at_pose())
        skins = hlib.nodes.SkinClusters([skin])
        self.assertEqual(skins.bind_pose()[0].full_name, pose.full_name)
        cmds.setAttr(self.child + ".ty", 7)
        self.assertEqual(len(skins.restore_bind_pose(ws=False)), 1)
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 0)
        cmds.undo()
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 7)

    def test_skin_reset_scope_undo_and_missing_pose(self):
        skin = self.make_skin()
        pose = skin.bind_pose()
        other = cmds.createNode("transform", name=self.ns + ":other")
        pose.add(other)
        old_other = list(pose.get_matrix(other))
        old_child = list(pose.get_matrix(self.child))
        old_bind = cmds.getAttr(skin.full_name + ".bindPreMatrix[1]")
        cmds.setAttr(other + ".ty", 9)
        cmds.setAttr(self.child + ".ty", 4)
        self.assertIs(skin.reset_bind_pose(), skin)
        self.assertEqual(list(pose.get_matrix(other)), old_other)
        self.assertNotEqual(list(pose.get_matrix(self.child)), old_child)
        self.assertEqual(cmds.getAttr(skin.full_name + ".bindPreMatrix[1]"), old_bind)
        cmds.undo()
        self.assertEqual(list(pose.get_matrix(self.child)), old_child)
        cmds.redo()
        self.assertNotEqual(list(pose.get_matrix(self.child)), old_child)
        pose.remove(self.child)
        root_before = list(pose.get_matrix(self.root))
        cmds.setAttr(self.root + ".ty", 2)
        with self.assertRaises(ValueError):
            skin.reset_bind_pose()
        self.assertEqual(list(pose.get_matrix(self.root)), root_before)
        cmds.disconnectAttr(pose.full_name + ".message", skin.full_name + ".bindPose")
        self.assertIsNone(skin.bind_pose())
        with self.assertRaises(RuntimeError):
            skin.restore_bind_pose()
        with self.assertRaises(RuntimeError):
            skin.reset_bind_pose()

    def test_explicit_targets_and_creation_undo(self):
        other = cmds.createNode("transform", name=self.ns + ":other")
        cmds.select(other)
        pose = self.pose(bind_pose=True)
        name = pose.full_name
        self.assertTrue(pose.is_bind_pose())
        self.assertNotIn(hlib.node(other), pose.members())
        self.assertEqual(cmds.ls(selection=True), [other])
        cmds.undo()
        self.assertFalse(cmds.objExists(name))
        cmds.redo()
        self.assertTrue(cmds.objExists(name))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
