"""長短フラグの戻り値・競合検査・アトリビュート別名を実Mayaで検証する。"""

import sys
import inspect
import unittest
import uuid
from unittest.mock import patch

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

    def test_explicit_parameters_do_not_query_maya_help(self):
        """長短名を引数へ公開し、実行中にhelpや別名メタデータを使わない。"""
        node = mlib.createNode("transform")
        parameters = inspect.signature(node.getTranslate).parameters
        self.assertIn("worldSpace", parameters)
        self.assertIn("ws", parameters)
        self.assertEqual(parameters["ws"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertFalse(hasattr(type(node).getTranslate, "__mlib_flag_aliases__"))
        with patch.object(cmds, "help", side_effect=AssertionError("runtime help lookup")):
            child = mlib.createNode("transform", n="explicitChild", p=node)
            child.setTranslate((1, 2, 3), ws=False, at=4, fast=True)
            mlib.select(child, r=True)
            self.assertEqual(mlib.ls(sl=True, typ="transform"), [child])
            self.assertEqual(tuple(child.getTranslate(ws=False, at=4)), (1, 2, 3))

    def test_alias_conflicts_and_missing_values_precede_undo(self):
        """False/Noneの重複と必須値欠落も、Undoや書込みを開始する前に拒否する。"""
        node = mlib.createNode("transform")
        matrix = mlib.createNode("multMatrix")
        attempts = (
            lambda: node.setTranslate((1, 2, 3), worldSpace=False, ws=False),
            lambda: node.reset(attributes=None, attrs=None),
            lambda: node.addAttr(longName="value", ln="value"),
            lambda: matrix.setInput(idx=2),
            lambda: matrix.setInput(value=mlib.maths.Matrix()),
        )
        with patch.object(cmds, "undoInfo", side_effect=AssertionError("Undo must not start")):
            for operation in attempts:
                with self.assertRaises(TypeError):
                    operation()

    def test_reserved_keyword_and_required_alias(self):
        """予約語の辞書指定と、indexの短名で必須番号を満たす経路を確認する。"""
        roots = mlib.ls(assemblies=True, long=True)
        short_roots = mlib.ls(long=True, **{"as": True})
        self.assertEqual([node.getFullName() for node in roots],
                         [node.getFullName() for node in short_roots])
        with self.assertRaises(TypeError):
            mlib.ls(assemblies=False, **{"as": False})
        matrix = mlib.createNode("multMatrix")
        value = mlib.maths.Matrix(translate=(1, 2, 3))
        self.assertIs(matrix.setInput(idx=2, value=value, fast=True), matrix)
        self.assertTrue(matrix.getInput(idx=2).isEquivalent(value))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
