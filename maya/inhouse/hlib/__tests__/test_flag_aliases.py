"""長短フラグの戻り値・競合検査・属性別名を実Mayaで検証する。"""

import sys
import unittest
import uuid

import maya.cmds as cmds
import hlib


class FlagAliasesTest(unittest.TestCase):
    def setUp(self):
        self.selection = cmds.ls(selection=True, long=True) or []
        self.previous_namespace = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        self.namespace = ':hlibFlags_' + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)
        cmds.namespace(set=self.namespace)

    def tearDown(self):
        cmds.namespace(set=self.previous_namespace)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        if self.selection:
            cmds.select(self.selection, replace=True)
        else:
            cmds.select(clear=True)

    def test_ls_collections_and_reload(self):
        joint = hlib.createNode('joint', n='joint')
        hlib.select(joint, r=True)
        for function in (hlib.ls, hlib.cmds.ls):
            self.assertIsInstance(function(sl=True, typ='joint'), hlib.nodes.Joints)
            self.assertEqual(len(function(selection=True, type='joint')), 1)
            self.assertIsInstance(function(typ='skinCluster'), hlib.nodes.SkinClusters)
        hlib.reload()
        self.assertIsInstance(hlib.ls(sl=True, typ='joint'), hlib.nodes.Joints)

    def test_duplicate_flags_fail_before_edit(self):
        count = len(cmds.ls())
        with self.assertRaises(TypeError):
            hlib.createNode('transform', name='same', n='same')
        self.assertEqual(len(cmds.ls()), count)
        with self.assertRaises(TypeError):
            hlib.ls(selection=True, sl=True)
        with self.assertRaises(TypeError):
            hlib.currentTime(query=True, q=True)

    def test_attribute_names_are_maya_names(self):
        node = hlib.createNode('transform')
        node.tx.set(3.5)
        self.assertEqual(node.translateX.get(), 3.5)
        node.plug('translateX').set(7)
        self.assertEqual(node.plug('tx').get(), 7)
        cmds.addAttr(node.full_name(), longName='customAmount', shortName='ca', attributeType='double')
        node.ca.set(2)
        self.assertEqual(node.customAmount.get(), 2)

    def test_constraint_and_bulk_aliases(self):
        source = hlib.createNode('transform')
        joint = hlib.createNode('joint')
        result = hlib.constraint(source, joint, typ='point', mo=True)
        self.assertEqual(cmds.nodeType(result.full_name()), 'pointConstraint')
        hlib.delete(result)
        joints = hlib.nodes.Joints([joint])
        results = joints.add_constraint(source, typ='point', mo=True)
        self.assertEqual(len(results), 1)
        hlib.delete(results)
        with self.assertRaises(TypeError):
            joint.add_constraint(source, 'point', typ='point')
        with self.assertRaises(TypeError):
            joints.add_constraint(source, type='point', typ='point')

    def test_native_command_specific_flags(self):
        parent = hlib.group(em=True, n='parent')
        node = hlib.createNode('transform', n='child', p=parent.full_name())
        copy = hlib.duplicate(node, n='copy')
        self.assertTrue(cmds.objExists(copy.full_name()))
        # setKeyframeのtはtime。lsのtypeに対する短縮名ではない。
        hlib.setKeyframe(node, at='tx', t=1, v=4)
        self.assertEqual(cmds.keyframe(node.full_name(), q=True, at='tx', vc=True), [4])
        with self.assertRaises(TypeError):
            hlib.setKeyframe(node, time=1, t=1)
        hlib.select(cl=True)
        self.assertEqual(hlib.ls(sl=True), [])


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
