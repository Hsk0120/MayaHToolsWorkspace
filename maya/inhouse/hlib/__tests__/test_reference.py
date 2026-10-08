"""hlib.nodes.reference の Reference と hlib.common.references.listReferences を検証するMaya内テスト。"""

import os
import sys
import tempfile
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.nodes import Node
from hlib.nodes.reference import Reference
from hlib.common import Namespace
from hlib.common.references import createReference, listReferences


class ReferenceTest(unittest.TestCase):
    """参照ノードのラップ・照会・ロード制御・削除を検証する。

    現在開いているシーンには一切触れず(file(new=...)等は使わない)、
    一時ファイルへの export と reference の追加・削除だけで完結させる。
    """

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.ref_path = os.path.join(self.tmp_dir, "hlibReferenceTestTarget.ma")
        helper = cmds.createNode("transform", name="hlibReferenceExportHelper")
        cmds.select(helper, replace=True)
        cmds.file(self.ref_path, exportSelected=True, type="mayaAscii", force=True)
        cmds.delete(helper)
        cmds.select(clear=True)
        self.namespace_name = "hlibReferenceTestNs"
        cmds.file(self.ref_path, reference=True, namespace=self.namespace_name, returnNewNodes=False)
        self.ref_node_name = next(
            name for name in cmds.ls(type="reference") if name != "sharedReferenceNode"
        )

    def tearDown(self):
        if cmds.objExists(self.ref_node_name):
            cmds.file(removeReference=True, referenceNode=self.ref_node_name)
        if os.path.exists(self.ref_path):
            os.remove(self.ref_path)
        if os.path.isdir(self.tmp_dir):
            os.rmdir(self.tmp_dir)

    def test_node_resolves_to_reference_wrapper(self):
        reference = Node(self.ref_node_name)
        self.assertIsInstance(reference, Reference)

    def test_filename_matches_referenceQuery(self):
        reference = Node(self.ref_node_name)
        self.assertEqual(reference.getFilename(), cmds.referenceQuery(self.ref_node_name, filename=True))

    def test_namespace_returns_namespace_instance(self):
        reference = Node(self.ref_node_name)
        namespace = reference.getAssociatedNamespace()
        self.assertIsInstance(namespace, Namespace)
        self.assertEqual(namespace, Namespace(self.namespace_name))

    def test_node_namespace_is_separate_from_reference_namespace(self):
        """継承APIはノード自身、専用APIは参照内容を照会する。"""
        reference = Node(self.ref_node_name)
        self.assertEqual(reference.getNamespace(), Namespace(':'))
        self.assertEqual(reference.getAssociatedNamespace(), Namespace(self.namespace_name))
        with self.assertRaises(RuntimeError):
            reference.isRoot()
        self.assertTrue(reference.isTopLevel())

    def test_is_loaded_and_nodes(self):
        reference = Node(self.ref_node_name)
        self.assertTrue(reference.isLoaded())
        nodes = reference.getNodes()
        self.assertEqual(len(nodes), 1)
        self.assertTrue(nodes[0].getName().startswith(self.namespace_name + ":"))

    def test_parent_reference_is_none_for_top_level(self):
        reference = Node(self.ref_node_name)
        self.assertIsNone(reference.getParentReference())

    def test_is_root_root_and_children_for_top_level_reference(self):
        reference = Node(self.ref_node_name)
        self.assertTrue(reference.isTopLevel())
        self.assertEqual(reference.getRoot().getName(), reference.getName())
        self.assertEqual(reference.getChildren(), [])

    def test_edit_strings_nodes_attrs_reflect_applied_edit(self):
        reference = Node(self.ref_node_name)
        self.assertEqual(reference.getEditStrings(), [])
        self.assertEqual(reference.getEditNodeNames(), [])
        self.assertEqual(reference.getEditAttrNames(), [])

        nodeName = f"{self.namespace_name}:hlibReferenceExportHelper"
        cmds.setAttr(nodeName + ".translateX", 3.0)

        editStrings = reference.getEditStrings()
        self.assertTrue(any("translate" in edit for edit in editStrings))
        self.assertIn("|" + nodeName, reference.getEditNodeNames())
        self.assertIn("translate", reference.getEditAttrNames())

    def test_unload_load_round_trip(self):
        reference = Node(self.ref_node_name)
        result = reference.unload()
        self.assertIs(result, reference)
        self.assertFalse(reference.isLoaded())
        self.assertFalse(cmds.referenceQuery(self.ref_node_name, isLoaded=True))

        result = reference.load()
        self.assertIs(result, reference)
        self.assertTrue(reference.isLoaded())

    def test_nodes_raises_when_unloaded(self):
        reference = Node(self.ref_node_name)
        reference.unload()
        with self.assertRaises(RuntimeError):
            reference.getNodes()

    def test_remove_deletes_reference_node(self):
        reference = Node(self.ref_node_name)
        reference.remove()
        self.assertFalse(cmds.objExists(self.ref_node_name))

    def test_list_references_includes_created_reference(self):
        references = listReferences()
        self.assertIn(self.ref_node_name, [reference.getName() for reference in references])

    def test_list_references_top_level_only_excludes_none_here(self):
        # このテストではネストした参照を作らないため、top_level_only=True でも
        # 通常の一覧と同じ結果になることだけを確認する。
        all_refs = {reference.getName() for reference in listReferences()}
        top_refs = {reference.getName() for reference in listReferences(top_level_only=True)}
        self.assertEqual(all_refs, top_refs)


class CreateReferenceTest(unittest.TestCase):
    """hlib.common.references.createReference による参照の新規作成を検証する。"""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.ref_path = os.path.join(self.tmp_dir, "hlibCreateReferenceTarget.ma")
        helper = cmds.createNode("transform", name="hlibCreateReferenceHelper")
        cmds.select(helper, replace=True)
        cmds.file(self.ref_path, exportSelected=True, type="mayaAscii", force=True)
        cmds.delete(helper)
        cmds.select(clear=True)
        self.created = None

    def tearDown(self):
        if self.created is not None and cmds.objExists(self.created.getName()):
            cmds.file(removeReference=True, referenceNode=self.created.getName())
        if os.path.exists(self.ref_path):
            os.remove(self.ref_path)
        if os.path.isdir(self.tmp_dir):
            os.rmdir(self.tmp_dir)

    def test_creates_reference_under_requested_namespace(self):
        self.created = createReference(self.ref_path, namespace="hlibCreateReferenceNs")
        self.assertIsInstance(self.created, Reference)
        self.assertTrue(self.created.isLoaded())
        self.assertTrue(cmds.objExists("hlibCreateReferenceNs:hlibCreateReferenceHelper"))
        self.assertEqual(self.created.getAssociatedNamespace(), Namespace("hlibCreateReferenceNs"))

    def test_created_reference_is_included_in_list_references(self):
        self.created = createReference(self.ref_path, namespace="hlibCreateReferenceNs2")
        self.assertIn(self.created.getName(), [reference.getName() for reference in listReferences()])

    def test_invalid_path_raises_value_error(self):
        with self.assertRaises(ValueError):
            createReference("")


class NestedReferenceTest(unittest.TestCase):
    """入れ子(参照が別の参照を持つ)構成での親子関係の解決を検証する。"""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.leaf_path = os.path.join(self.tmp_dir, "hlibNestedLeaf.ma")
        self.mid_path = os.path.join(self.tmp_dir, "hlibNestedMid.ma")

        cmds.file(new=True, force=True)
        cmds.polyCube(name="leafCube")
        cmds.file(rename=self.leaf_path)
        cmds.file(save=True, type="mayaAscii", force=True)

        cmds.file(new=True, force=True)
        cmds.file(self.leaf_path, reference=True, namespace="hlibNestedLeafNs")
        cmds.file(rename=self.mid_path)
        cmds.file(save=True, type="mayaAscii", force=True)

        cmds.file(new=True, force=True)
        self.top = createReference(self.mid_path, namespace="hlibNestedMidNs")
        self.nested_name = next(
            name for name in cmds.ls(type="reference")
            if name not in ("sharedReferenceNode", self.top.getName())
        )

    def tearDown(self):
        if cmds.objExists(self.top.getName()):
            cmds.file(removeReference=True, referenceNode=self.top.getName())
        for path in (self.leaf_path, self.mid_path):
            if os.path.exists(path):
                os.remove(path)
        if os.path.isdir(self.tmp_dir):
            os.rmdir(self.tmp_dir)

    def test_top_level_reference_reports_nested_child(self):
        self.assertTrue(self.top.isTopLevel())
        self.assertEqual(self.top.getRoot().getName(), self.top.getName())
        child_names = [child.getName() for child in self.top.getChildren()]
        self.assertEqual(child_names, [self.nested_name])

    def test_nested_reference_resolves_parent_and_root(self):
        nested = Node(self.nested_name)
        self.assertFalse(nested.isTopLevel())
        self.assertEqual(nested.getParentReference().getName(), self.top.getName())
        self.assertEqual(nested.getRoot().getName(), self.top.getName())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
