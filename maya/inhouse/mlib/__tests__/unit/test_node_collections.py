"""ノードコレクションの継承・参照の契約を検証する。"""
import sys
import unittest
import uuid

import maya.cmds as cmds
import mlib

mlib.reload()


class NodeCollectionsTest(unittest.TestCase):
    """既存シーンと分離した名前空間で複数形APIを検証する。"""

    def setUp(self):
        """検証用ノードを作る。"""
        self.ns = 'mlibCollections_' + uuid.uuid4().hex
        cmds.namespace(add=self.ns)
        self.names = [cmds.createNode('joint', name=self.ns + ':j' + str(i)) for i in range(2)]
        self.joints = mlib.nodes.Joints(self.names)

    def tearDown(self):
        """検証用名前空間を片付ける。"""
        for name in cmds.ls(self.ns + ':*') or []:
            cmds.lockNode(name, lock=False)
        cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def test_hierarchy_inputs_copy_and_strict_type(self):
        """型階層と単一入力・重複・コピーを検証する。"""
        from mlib.nodes import Nodes, Joints, SkinClusters
        self.assertIsInstance(self.joints, Nodes)
        self.assertTrue(issubclass(Joints, Nodes))
        self.assertTrue(issubclass(SkinClusters, Nodes))
        self.assertEqual(len(Nodes(self.names[0])), 1)
        self.assertEqual(len(Joints(self.names + self.names)), 2)
        self.assertEqual(len(Nodes(self.joints)), 2)
        self.assertIs(self.joints.copy()[0], self.joints[0])
        self.assertIsInstance(self.joints[:1], Joints)
        plain = cmds.createNode('transform', name=self.ns + ':plain')
        with self.assertRaises(TypeError):
            Joints([self.names[0], plain])
        with self.assertRaises(TypeError):
            SkinClusters(self.names)
        cmds.rename(self.names[0], self.ns + ':renamed')
        self.assertTrue(self.joints[0].getName().endswith('renamed'))
        self.assertEqual(len(Nodes(self.joints)), 2)
        cmds.delete(self.joints[0])
        self.assertEqual([joint.isValid() for joint in self.joints], [False, True])
        self.assertEqual(len(self.joints[:]), 2)
        with self.assertRaises(RuntimeError):
            Joints(self.joints)

    def test_instance_paths_keep_distinct_world_matrices(self):
        """同じノードでもDAGインスタンス別の行列を保持する。"""
        from mlib.nodes import Nodes
        group = cmds.createNode("transform", name=self.ns + ":group")
        leaf = cmds.createNode("transform", name=self.ns + ":leaf", parent=group)
        other = cmds.instance(group, name=self.ns + ":other")[0]
        cmds.setAttr(other + ".tx", 10)
        paths = cmds.ls(leaf, long=True, allPaths=True)
        nodes = Nodes(paths + paths)
        self.assertEqual(len(nodes), 2)
        self.assertNotEqual(list(nodes[0].getMatrix(worldSpace=True)), list(nodes[1].getMatrix(worldSpace=True)))

    def test_parent_deletion_and_extension_reference(self):
        """親子削除と、派生ラッパーを作り直さず保持することを確認する。"""
        from mlib.nodes import Nodes, Joints, Joint
        class ExtendedJoint(Joint):
            """外部拡張相当の派生型。"""
        wrapped = object.__new__(ExtendedJoint)
        wrapped.__dict__.update(self.joints[0].__dict__)
        self.assertIs(Joints([wrapped])[0], wrapped)
        parent = cmds.createNode('transform', name=self.ns + ':parent')
        child = cmds.createNode('transform', name=self.ns + ':child', parent=parent)
        nodes = Nodes([parent, child])
        mlib.delete(nodes)
        self.assertFalse(cmds.objExists(parent))
        cmds.undo()
        self.assertTrue(cmds.objExists(child))
        self.assertEqual(mlib.ls([]), [])  # 検索の戻り値契約は維持

    def test_instanced_joint_delete(self):
        """同じjointの異なるパスを渡してもノード単位の削除が完了する。"""
        a = cmds.createNode('transform', name=self.ns + ':instanceA')
        b = cmds.createNode('transform', name=self.ns + ':instanceB')
        joint = cmds.createNode('joint', name=self.ns + ':instanceJoint', parent=a)
        cmds.parent(joint, b, addObject=True)
        paths = cmds.ls(joint, long=True, allPaths=True)
        self.assertEqual(len(paths), 2)
        mlib.delete(mlib.nodes.Joints(paths))
        self.assertFalse(cmds.objExists(joint))
        cmds.undo()
        self.assertTrue(cmds.objExists(joint))


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
