"""hlib._core.registry の NodeRegistry と登録デコレータを検証するMaya内テスト。

NodeRegistry / node_wrapper / plug_wrapper / collection_export は純粋 Python ロジック
だが、CLAUDE.md の方針に従い hlib 経由（Maya 内）で実行する。
"""

import sys
import unittest

import hlib
hlib.reload()
from hlib._core.registry import NodeRegistry, collection_export, node_wrapper, plug_wrapper


class _FallbackClass:
    def __init__(self, value=None):
        self.value = value


class _RegisteredClass:
    def __init__(self, value=None):
        self.value = value


class NodeRegistryTest(unittest.TestCase):
    """register/get/lookup/wrapper_class/clear/register_discovered の基本動作を検証する。"""

    def setUp(self):
        self.registry = NodeRegistry(_FallbackClass)

    def test_unregistered_type_falls_back_and_lookup_returns_none(self):
        self.assertIs(self.registry.wrapper_class("unregisteredType"), _FallbackClass)
        self.assertIs(self.registry.get("unregisteredType"), _FallbackClass)
        self.assertIsNone(self.registry.lookup("unregisteredType"))

    def test_register_and_get(self):
        self.registry.register("myType", _RegisteredClass)
        self.assertIs(self.registry.get("myType"), _RegisteredClass)
        self.assertIs(self.registry.lookup("myType"), _RegisteredClass)
        self.assertIs(self.registry.wrapper_class("otherType"), _FallbackClass)

    def test_register_rejects_invalid_input(self):
        with self.assertRaises(ValueError):
            self.registry.register("", _RegisteredClass)
        with self.assertRaises(TypeError):
            self.registry.register("myType", object())

    def test_clear_removes_all_registrations(self):
        self.registry.register("myType", _RegisteredClass)
        self.registry.clear()
        self.assertIs(self.registry.wrapper_class("myType"), _FallbackClass)

    def test_register_discovered_replaces_existing_registrations(self):
        self.registry.register("staleType", _RegisteredClass)
        self.registry.register_discovered({"myType": _RegisteredClass})
        self.assertIs(self.registry.wrapper_class("staleType"), _FallbackClass)
        self.assertIs(self.registry.get("myType"), _RegisteredClass)


class WrapperDecoratorsTest(unittest.TestCase):
    """node_wrapper/plug_wrapper/collection_export がメタデータを正しく付与することを検証する。"""

    def test_node_wrapper_sets_metadata(self):
        @node_wrapper("customNodeType", public=False)
        class CustomNode:
            pass

        self.assertEqual(CustomNode.__hlib_node_type__, "customNodeType")
        self.assertFalse(CustomNode.__hlib_public__)

    def test_node_wrapper_rejects_empty_type(self):
        with self.assertRaises(ValueError):
            node_wrapper("")(_RegisteredClass)

    def test_node_wrapper_rejects_non_class(self):
        with self.assertRaises(TypeError):
            node_wrapper("customNodeType")(object())

    def test_plug_wrapper_sets_metadata(self):
        @plug_wrapper("customAttrType")
        class CustomPlug:
            pass

        self.assertEqual(CustomPlug.__hlib_plug_type__, "customAttrType")
        self.assertTrue(CustomPlug.__hlib_public__)

    def test_collection_export_sets_metadata(self):
        @collection_export(public=False)
        class CustomCollection:
            pass

        self.assertTrue(CustomCollection.__hlib_collection__)
        self.assertFalse(CustomCollection.__hlib_public__)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
