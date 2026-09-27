"""Node.deleteへの委譲と標準削除のUndoを検証する。"""

import unittest
import uuid
from unittest.mock import patch
import maya.cmds as cmds
import hlib


class NodeDeleteTest(unittest.TestCase):
    """親子の一括削除とJoint専用処理との区別を確認する。"""

    def setUp(self):
        self.previous = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        self.namespace = ':nodeDelete_' + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)
        cmds.namespace(set=self.namespace)

    def tearDown(self):
        cmds.namespace(set=self.previous)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def test_command_delegates_and_batch_undo(self):
        root = hlib.createNode('transform', skipSelect=True)
        child = hlib.createNode('transform', parent=root, skipSelect=True)
        names = [root.full_name(), child.full_name()]
        original = hlib.nodes.Node.delete
        with patch.object(hlib.nodes.Node, 'delete', autospec=True, side_effect=original) as method:
            hlib.delete([root, child, root])
            self.assertEqual(method.call_count, 1)
        self.assertTrue(all(not cmds.objExists(name) for name in names))
        cmds.undo()
        self.assertTrue(all(cmds.objExists(name) for name in names))
        cmds.redo()
        self.assertTrue(all(not cmds.objExists(name) for name in names))

    def test_instance_delete_and_invalid_node(self):
        node = hlib.createNode('transform', skipSelect=True)
        node.delete()
        self.assertFalse(node.is_valid())
        with self.assertRaises(RuntimeError):
            node.delete()

    def test_joint_command_uses_specialized_delete(self):
        joint = hlib.createNode('joint', skipSelect=True)
        child = hlib.createNode('joint', parent=joint, skipSelect=True)
        original = hlib.nodes.Joint.delete
        with patch.object(hlib.nodes.Joint, 'delete', autospec=True, side_effect=original) as method:
            hlib.delete(joint.full_name())
            self.assertEqual(method.call_count, 1)
        self.assertFalse(joint.is_valid())
        self.assertTrue(child.is_valid())
        cmds.undo()
        self.assertTrue(joint.is_valid())
        self.assertEqual(child.parent_node().uuid(), joint.uuid())

    def test_components_mixed_with_node_and_wildcard(self):
        mesh = hlib.createPolygon(ch=False)
        hlib.delete([mesh.transform(), mesh.full_name() + '.f[0]'])
        self.assertFalse(mesh.is_valid())
        for name in ('matchA','matchB'):
            hlib.createNode('transform', name=name, skipSelect=True)
        hlib.delete(self.namespace + ':match*')
        self.assertFalse(cmds.ls(self.namespace + ':match*'))
