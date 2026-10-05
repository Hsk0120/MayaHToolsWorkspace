"""DagPoseの保存・復元・メンバー編集とUndoを実Mayaで検証する。"""
from maya.api.OpenMaya import MSpace
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
        self.assertIsInstance(hlib.getNode(pose.fullName()), hlib.nodes.DagPose)
        self.assertFalse(pose.isBindPose())
        self.assertEqual(len(pose.members()), 2)

        self.assertEqual(pose.memberIndices(), [0, 1])
        self.assertEqual(list(pose.getMatrix(self.child)), cmds.getAttr(self.child + ".matrix"))
        self.assertEqual(list(pose.getMatrix(self.child, ws=True)), cmds.getAttr(self.child + ".worldMatrix[0]"))
        self.assertTrue(pose.isAtPose())
        cmds.setAttr(self.child + ".ty", 4)
        self.assertEqual([x.fullName() for x in pose.notAtPose()], [hlib.getNode(self.child).fullName()])
        self.assertFalse(pose.isAtPose())

    def test_sparse_member_indices(self):
        pose = self.pose()
        extra = cmds.createNode("transform", name=self.ns + ":extra")
        pose.addMembers(extra)
        extra_index = pose.memberIndex(extra)
        pose.removeMembers(self.child)
        self.assertEqual(pose.memberIndices(), [0, extra_index])
        self.assertEqual(pose.memberIndex(extra), extra_index)
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
        self.assertEqual(len(pose.members()), 1)
        pose.addMembers(self.child)
        self.assertEqual(len(pose.members()), 2)
        cmds.undo()
        self.assertEqual(len(pose.members()), 1)
        cmds.redo()
        pose.removeMembers(self.child)
        self.assertTrue(cmds.objExists(self.child))
        self.assertEqual(len(pose.members()), 1)
        cmds.undo()
        self.assertEqual(len(pose.members()), 2)
        with self.assertRaises(ValueError):
            pose.addMembers([])
        other = cmds.createNode("transform", name=self.ns + ":other")
        with self.assertRaises(ValueError):
            pose.reset([self.root, other])
        with self.assertRaises(ValueError):
            pose.removeMembers([self.root, other])
        self.assertEqual(len(pose.members()), 2)

    def test_bind_pose_and_skin_matrices(self):
        mesh = cmds.polyCube(name=self.ns + ":mesh")[0]
        skin = cmds.skinCluster([self.root, self.child], mesh, name=self.ns + ":skin")[0]
        pose_name = cmds.listConnections(skin + ".bindPose", source=True, destination=False)[0]
        cmds.rename(pose_name, self.ns + ":bindPose")
        pose = hlib.getNode(self.ns + ":bindPose")
        self.assertEqual(hlib.nodes.DagPose.fromSkinCluster(skin).fullName(), pose.fullName())
        self.assertTrue(pose.isBindPose())
        self.assertEqual([x.fullName() for x in pose.skinClusters()], [skin])
        before = cmds.getAttr(skin + ".bindPreMatrix[1]")
        cmds.setAttr(self.child + ".ty", 4)
        pose.reset()
        self.assertEqual(cmds.getAttr(skin + ".bindPreMatrix[1]"), before)
        self.assertTrue(pose.isAtPose())
        cmds.disconnectAttr(pose.fullName() + ".message", skin + ".bindPose")
        self.assertIsNone(hlib.nodes.DagPose.fromSkinCluster(skin))
        with self.assertRaises(ValueError):
            hlib.nodes.DagPose.fromSkinCluster(self.root)

    def make_skin(self):
        mesh = cmds.polyCube(name=self.ns + ":mesh")[0]
        name = cmds.skinCluster([self.root, self.child], mesh, name=self.ns + ":skin")[0]
        skin = hlib.getNode(name)
        cmds.rename(skin.bindPose().fullName(), self.ns + ":bindPose")
        return skin

    def test_skin_restore_and_bulk(self):
        skin = self.make_skin()
        pose = skin.bindPose()
        self.assertIsInstance(pose, hlib.nodes.DagPose)
        cmds.setAttr(self.child + ".ty", 4)
        self.assertIs(skin.restoreBindPose(), skin)
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 0)
        cmds.undo()
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 4)
        cmds.redo()
        self.assertTrue(pose.isAtPose())
        skins = hlib.nodes.SkinClusters([skin])
        self.assertEqual(skins.bindPose()[0].fullName(), pose.fullName())
        cmds.setAttr(self.child + ".ty", 7)
        self.assertEqual(len(skins.restoreBindPose(ws=False)), 1)
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 0)
        cmds.undo()
        self.assertAlmostEqual(cmds.getAttr(self.child + ".ty"), 7)

    def test_skin_reset_scope_undo_and_missing_pose(self):
        skin = self.make_skin()
        pose = skin.bindPose()
        other = cmds.createNode("transform", name=self.ns + ":other")
        pose.addMembers(other)
        old_other = list(pose.getMatrix(other))
        old_child = list(pose.getMatrix(self.child))
        old_bind = cmds.getAttr(skin.fullName() + ".bindPreMatrix[1]")
        cmds.setAttr(other + ".ty", 9)
        cmds.setAttr(self.child + ".ty", 4)
        self.assertIs(skin.resetBindPose(), skin)
        self.assertEqual(list(pose.getMatrix(other)), old_other)
        self.assertNotEqual(list(pose.getMatrix(self.child)), old_child)
        self.assertEqual(cmds.getAttr(skin.fullName() + ".bindPreMatrix[1]"), old_bind)
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
        cmds.disconnectAttr(pose.fullName() + ".message", skin.fullName() + ".bindPose")
        self.assertIsNone(skin.bindPose())
        with self.assertRaises(RuntimeError):
            skin.restoreBindPose()
        with self.assertRaises(RuntimeError):
            skin.resetBindPose()

    def test_explicit_targets_and_creation_undo(self):
        other = cmds.createNode("transform", name=self.ns + ":other")
        cmds.select(other)
        pose = self.pose(bindPose=True)
        name = pose.fullName()
        self.assertTrue(pose.isBindPose())
        self.assertNotIn(hlib.getNode(other), pose.members())
        self.assertEqual(cmds.ls(selection=True), [other])
        cmds.undo()
        self.assertFalse(cmds.objExists(name))
        cmds.redo()
        self.assertTrue(cmds.objExists(name))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
