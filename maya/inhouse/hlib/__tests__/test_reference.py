"""hlib.nodes.reference の Reference と hlib.files.list_references を検証するMaya内テスト。"""

import os
import sys
import tempfile
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.nodes import Node
from hlib.nodes.reference import Reference
from hlib.namespaces import Namespace
from hlib.files import list_references


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
        self.assertEqual(reference.filename(), cmds.referenceQuery(self.ref_node_name, filename=True))

    def test_namespace_returns_namespace_instance(self):
        reference = Node(self.ref_node_name)
        namespace = reference.namespace()
        self.assertIsInstance(namespace, Namespace)
        self.assertEqual(namespace, Namespace(self.namespace_name))

    def test_is_loaded_and_nodes(self):
        reference = Node(self.ref_node_name)
        self.assertTrue(reference.is_loaded())
        nodes = reference.nodes()
        self.assertEqual(len(nodes), 1)
        self.assertTrue(nodes[0].name().startswith(self.namespace_name + ":"))

    def test_parent_reference_is_none_for_top_level(self):
        reference = Node(self.ref_node_name)
        self.assertIsNone(reference.parent_reference())

    def test_unload_load_round_trip(self):
        reference = Node(self.ref_node_name)
        result = reference.unload()
        self.assertIs(result, reference)
        self.assertFalse(reference.is_loaded())
        self.assertFalse(cmds.referenceQuery(self.ref_node_name, isLoaded=True))

        result = reference.load()
        self.assertIs(result, reference)
        self.assertTrue(reference.is_loaded())

    def test_nodes_raises_when_unloaded(self):
        reference = Node(self.ref_node_name)
        reference.unload()
        with self.assertRaises(RuntimeError):
            reference.nodes()

    def test_remove_deletes_reference_node(self):
        reference = Node(self.ref_node_name)
        reference.remove()
        self.assertFalse(cmds.objExists(self.ref_node_name))

    def test_list_references_includes_created_reference(self):
        references = list_references()
        self.assertIn(self.ref_node_name, [reference.name() for reference in references])

    def test_list_references_top_level_only_excludes_none_here(self):
        # このテストではネストした参照を作らないため、top_level_only=True でも
        # 通常の一覧と同じ結果になることだけを確認する。
        all_refs = {reference.name() for reference in list_references()}
        top_refs = {reference.name() for reference in list_references(top_level_only=True)}
        self.assertEqual(all_refs, top_refs)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
