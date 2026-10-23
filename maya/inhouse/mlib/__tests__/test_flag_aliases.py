"""長短フラグの戻り値・競合検査・アトリビュート別名を実Mayaで検証する。"""

import sys
import unittest
import uuid

import maya.cmds as cmds
import mlib


class FlagAliasesTest(unittest.TestCase):
    def setUp(self):
        self.selection = cmds.ls(selection=True, long=True) or []
        self.previous_namespace = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        self.namespace = ":mlibFlags_" + uuid.uuid4().hex
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
        joint = mlib.createNode("joint", n="joint")
        mlib.select(joint, r=True)
        for function in (mlib.ls, mlib.cmds.ls):
            self.assertIsInstance(function(sl=True, typ="joint"), mlib.nodes.Joints)
            self.assertEqual(len(function(selection=True, type="joint")), 1)
            self.assertIsInstance(function(typ="skinCluster"), mlib.nodes.SkinClusters)
        mlib.reload()
        self.assertIsInstance(mlib.ls(sl=True, typ="joint"), mlib.nodes.Joints)

    def test_duplicate_flags_fail_before_edit(self):
        count = len(cmds.ls())
        with self.assertRaises(TypeError):
            mlib.createNode("transform", name="same", n="same")
        self.assertEqual(len(cmds.ls()), count)
        with self.assertRaises(TypeError):
            mlib.ls(selection=True, sl=True)

    def test_attribute_names_are_maya_names(self):
        node = mlib.createNode("transform")
        node.tx.set(3.5)
        self.assertEqual(node.translateX.get(), 3.5)
        node.getPlug("translateX").set(7)
        self.assertEqual(node.getPlug("tx").get(), 7)
        cmds.addAttr(
            node.getFullName(), longName="customAmount", shortName="ca", attributeType="double"
        )
        node.ca.set(2)
        self.assertEqual(node.customAmount.get(), 2)

    def test_constraint_and_bulk_aliases(self):
        source = mlib.createNode("transform")
        joint = mlib.createNode("joint")
        result = mlib.getNode(joint).addConstraint(source, typ="point", mo=True)
        self.assertEqual(cmds.nodeType(result.getFullName()), "pointConstraint")
        mlib.delete(result)
        joints = mlib.nodes.Joints([joint])
        results = joints.addConstraint(source, typ="point", mo=True)
        self.assertEqual(len(results), 1)
        mlib.delete(results)
        with self.assertRaises(TypeError):
            joint.addConstraint(source, "point", typ="point")
        with self.assertRaises(TypeError):
            joints.addConstraint(source, type="point", typ="point")

    def test_native_command_specific_flags(self):
        parent = mlib.getNode(cmds.group(em=True, n="parent"))
        node = mlib.createNode("transform", n="child", p=parent.getFullName())
        copy = mlib.duplicate(node, n="copy")
        self.assertTrue(cmds.objExists(copy.getFullName()))
        # setKeyframeのtはtime。lsのtypeに対する短縮名ではない。
        cmds.setKeyframe(node, at="tx", t=1, v=4)
        self.assertEqual(cmds.keyframe(node.getFullName(), q=True, at="tx", vc=True), [4])
        mlib.select(cl=True)
        self.assertEqual(mlib.ls(sl=True), [])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
