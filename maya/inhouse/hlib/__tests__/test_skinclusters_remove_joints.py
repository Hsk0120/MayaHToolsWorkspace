"""一括influence解除はjointを残し、保持したskinClusterだけを編集する。"""
import sys
import unittest
import uuid

import maya.cmds as cmds
import hlib


class RemoveJointsTest(unittest.TestCase):
    def setUp(self):
        self.ns = ':hlibRemoveInfluences_' + uuid.uuid4().hex
        self.previous = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        self.selection = cmds.ls(selection=True, long=True) or []
        cmds.namespace(add=self.ns)
        cmds.namespace(set=self.ns)
        self.parent = cmds.createNode('joint', name='parent')
        self.child = cmds.createNode('joint', name='child', parent=self.parent)
        self.other = cmds.createNode('joint', name='other')

    def tearDown(self):
        cmds.namespace(set=self.previous)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)
        if self.selection:
            cmds.select(self.selection, replace=True)
        else:
            cmds.select(clear=True)

    def skin(self, joints):
        mesh = cmds.polyCube()[0]
        return hlib.node(cmds.skinCluster(joints, mesh, toSelectedBones=True)[0])

    def test_parent_transfer_scope_and_undo(self):
        skin = self.skin([self.parent, self.child])
        untouched = self.skin([self.parent, self.child])
        skin.set_weights([self.parent, self.child], [0.25, 0.75])
        before = list(skin.get_weights([self.parent, self.child]))
        collection = hlib.nodes.SkinClusters([skin])
        collection.remove_joints([self.child, self.child])
        self.assertTrue(cmds.objExists(self.child))
        self.assertEqual(cmds.listRelatives(self.child, parent=True), [self.parent])
        self.assertFalse(skin.has_influence(self.child))
        self.assertTrue(untouched.has_influence(self.child))
        self.assertEqual(list(skin.get_weights([self.parent])), [1.0] * 8)
        cmds.undo()
        self.assertEqual(list(skin.get_weights([self.parent, self.child])), before)
        cmds.redo()
        self.assertFalse(skin.has_influence(self.child))
        self.assertTrue(cmds.objExists(self.child))

    def test_without_ancestor_matches_maya(self):
        for transfer in (True, False):
            actual = self.skin([self.child, self.other])
            expected = self.skin([self.child, self.other])
            for skin in (actual, expected):
                skin.set_weights([self.child, self.other], [0.75, 0.25])
            cmds.skinCluster(expected.full_name(), edit=True, removeInfluence=self.child)
            hlib.nodes.SkinClusters([actual]).remove_joints(self.child, transfer_to_parent=transfer)
            self.assertEqual(list(actual.get_weights([self.other])), list(expected.get_weights([self.other])))
            self.assertTrue(cmds.objExists(self.child))

    def test_remove_all_rejected_before_any_skin_changes(self):
        first = self.skin([self.parent, self.child])
        last = self.skin([self.child])
        with self.assertRaises(ValueError):
            hlib.nodes.SkinClusters([first, last]).remove_joints(self.child)
        self.assertTrue(first.has_influence(self.child))
        self.assertTrue(last.has_influence(self.child))
        self.assertTrue(cmds.objExists(self.child))

    def test_chain_and_unregistered_joint(self):
        leaf = cmds.createNode('joint', name='leaf', parent=self.child)
        skin = self.skin([self.parent, self.child, leaf])
        skin.set_weights([self.parent, self.child, leaf], [0.1, 0.2, 0.7])
        hlib.nodes.SkinClusters([skin]).remove_influences([self.child, leaf, self.other])
        weights = list(skin.get_weights([self.parent]))
        self.assertEqual(len(weights), 8)
        for weight in weights:
            self.assertAlmostEqual(weight, 1.0)
        self.assertEqual(cmds.listRelatives(leaf, parent=True), [self.child])
        self.assertTrue(cmds.objExists(self.child))


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
