"""hlib._core.coerce の to_name/to_names/to_node を検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib._core.coerce import to_name, to_names, to_node
from hlib.nodes import Node


class CoerceTest(unittest.TestCase):
    """Node/文字列の混在入力を正規化する共通ヘルパーを検証する。"""

    def setUp(self):
        self.created = []

    def tearDown(self):
        for name in reversed(self.created):
            if cmds.objExists(name):
                cmds.delete(name)

    def create_transform(self, name):
        node_name = cmds.createNode("transform", name=name)
        self.created.append(node_name)
        return Node(node_name)

    def test_to_name_passes_through_string_without_resolving(self):
        # 存在しない名前でも解決を試みず、そのまま返す。
        self.assertEqual(to_name("doesNotExistYet"), "doesNotExistYet")

    def test_to_name_uses_full_name_for_node(self):
        node = self.create_transform("hlibCoerceToName")
        self.assertEqual(to_name(node), node.full_name())

    def test_to_name_rejects_invalid_types_and_empty_string(self):
        with self.assertRaises(TypeError):
            to_name(123)
        with self.assertRaises(ValueError):
            to_name("")

    def test_to_names_wraps_single_node_or_string(self):
        node = self.create_transform("hlibCoerceToNamesSingle")
        self.assertEqual(to_names(node), [node.full_name()])
        self.assertEqual(to_names("literalName"), ["literalName"])

    def test_to_names_converts_mixed_iterable(self):
        node = self.create_transform("hlibCoerceToNamesMixed")
        result = to_names([node, "literalName"])
        self.assertEqual(result, [node.full_name(), "literalName"])

    def test_to_names_empty_iterable_returns_empty_list(self):
        self.assertEqual(to_names([]), [])

    def test_to_names_propagates_element_errors(self):
        with self.assertRaises(TypeError):
            to_names([123])
        with self.assertRaises(ValueError):
            to_names([""])

    def test_to_node_returns_same_instance_for_node_input(self):
        node = self.create_transform("hlibCoerceToNodeSame")
        self.assertIs(to_node(node), node)

    def test_to_node_resolves_string_to_node(self):
        node = self.create_transform("hlibCoerceToNodeResolve")
        resolved = to_node(node.name())
        self.assertIsInstance(resolved, Node)
        self.assertEqual(resolved.full_name(), node.full_name())

    def test_to_node_rejects_invalid_type(self):
        with self.assertRaises(TypeError):
            to_node(123)

    def test_to_node_raises_when_string_does_not_resolve(self):
        with self.assertRaises(RuntimeError):
            to_node("hlibCoerceDoesNotExist")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
