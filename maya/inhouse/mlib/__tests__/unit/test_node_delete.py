"""Node.deleteへの委譲と標準削除のUndoを検証する。"""

import unittest
import uuid
from unittest.mock import patch

import mlib
import maya.cmds as cmds


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
        root = mlib.createNode('transform', skipSelect=True)
        child = mlib.createNode('transform', parent=root, skipSelect=True)
        names = [root.getFullName(), child.getFullName()]
        # 2026-10-26 の削除の一括化で、各Node.deleteへの委譲から1回のcmds.deleteへ変わった。
        # 重複・親子を含めてもMayaの1回の削除にまとめることを確かめる。
        with patch.object(cmds, 'delete', wraps=cmds.delete) as method:
            mlib.delete([root, child, root])
            self.assertEqual(method.call_count, 1)
        self.assertTrue(all(not cmds.objExists(name) for name in names))
        cmds.undo()
        self.assertTrue(all(cmds.objExists(name) for name in names))
        cmds.redo()
        self.assertTrue(all(not cmds.objExists(name) for name in names))

    def test_instance_delete_and_invalid_node(self):
        node = mlib.createNode('transform', skipSelect=True)
        node.delete()
        self.assertFalse(node.isValid())
        with self.assertRaises(RuntimeError):
            node.delete()

    def test_safe_preserves_incoming_outgoing_and_message(self):
        source = mlib.createNode('multiplyDivide', skipSelect=True)
        destination = mlib.createNode('multiplyDivide', skipSelect=True)
        cmds.connectAttr(source.getFullName() + '.outputX', destination.getFullName() + '.input1X')
        before_undo = cmds.undoInfo(query=True, undoName=True)
        self.assertIsNone(source.delete(safe=True))
        self.assertIsNone(destination.delete(safe=True))
        self.assertTrue(source.isValid() and destination.isValid())
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), before_undo)
        owner = mlib.createNode('network', skipSelect=True)
        cmds.addAttr(owner.getFullName(), longName='ref', attributeType='message')
        cmds.connectAttr(source.getFullName() + '.message', owner.getFullName() + '.ref')
        owner.delete(safe=True)
        self.assertTrue(owner.isValid())
        destination.delete()  # 既定値は従来どおり接続があっても削除する。
        self.assertFalse(destination.isValid())

    def test_safe_protects_connected_descendants_and_shader_membership(self):
        root = mlib.createNode('transform', skipSelect=True)
        child = mlib.createNode('transform', parent=root, skipSelect=True)
        source = mlib.createNode('multiplyDivide', skipSelect=True)
        cmds.connectAttr(source.getFullName() + '.outputX', child.getFullName() + '.tx')
        root.delete(safe=True)
        self.assertTrue(root.isValid() and child.isValid())
        mesh = mlib.getNode(cmds.polyCube(ch=False)[0]).getShape()
        mesh.getTransform().delete(safe=True)
        self.assertTrue(mesh.isValid())
        mesh.delete(safe=True)
        self.assertTrue(mesh.isValid())

    def test_safe_validation_and_no_exception_suppression(self):
        node = mlib.createNode('transform', skipSelect=True)
        with self.assertRaises(TypeError):
            node.delete(safe='yes')
        self.assertTrue(node.isValid())
        cmds.lockNode(node.getFullName(), lock=True)
        try:
            with self.assertRaises(RuntimeError):
                node.delete(safe=True)
            self.assertTrue(node.isValid())
        finally:
            cmds.lockNode(node.getFullName(), lock=False)

    def test_joint_command_uses_standard_delete(self):
        joint = mlib.createNode('joint', skipSelect=True)
        child = mlib.createNode('joint', parent=joint, skipSelect=True)
        original = mlib.nodes.Joint.delete
        with patch.object(mlib.nodes.Joint, 'delete', autospec=True, side_effect=original) as method:
            mlib.delete(joint.getFullName())
            self.assertEqual(method.call_count, 1)
        self.assertFalse(joint.isValid())
        self.assertFalse(child.isValid())
        cmds.undo()
        self.assertTrue(joint.isValid())
        self.assertEqual(child.getParent().getUuid(), joint.getUuid())

    def test_components_mixed_with_node_and_wildcard(self):
        mesh = mlib.getNode(cmds.polyCube(ch=False)[0]).getShape()
        # 公開済みの入力規則ではNodeと名前の混在は不可。名前へ揃えて実行する。
        with self.assertRaises(TypeError):
            mlib.delete([mesh.getTransform(), mesh.getFullName() + '.f[0]'])
        mlib.delete([mesh.getTransform().getFullName(), mesh.getFullName() + '.f[0]'])
        self.assertFalse(mesh.isValid())
        for name in ('matchA','matchB'):
            mlib.createNode('transform', name=name, skipSelect=True)
        mlib.delete(self.namespace + ':match*')
        self.assertFalse(cmds.ls(self.namespace + ':match*'))


if __name__ == "__main__":
    unittest.main()
