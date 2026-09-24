"""hlib._core.registry の NodeRegistry と登録デコレータを検証するMaya内テスト。

NodeRegistry / node_wrapper / plug_wrapper / collection_export は純粋 Python ロジック
だが、CLAUDE.md の方針に従い hlib 経由（Maya 内）で実行する。
"""

import sys
import unittest

import hlib
hlib.reload()
from hlib._core.registry import NodeRegistry, collection_export, node_wrapper, plug_wrapper
from hlib._core.type_hierarchy import inherited_node_types


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


class NodeRegistryInheritedTypesTest(unittest.TestCase):
    """resolve_inherited_types=True 時の継承チェーン経由の解決を検証する(実際のMayaノードタイプ継承を使う)。"""

    def test_falls_back_to_nearest_registered_ancestor(self):
        registry = NodeRegistry(_FallbackClass, resolve_inherited_types=True)
        registry.register("transform", _RegisteredClass)
        # joint は transform を継承する組み込みノードタイプ。joint 自体は未登録。
        self.assertIs(registry.wrapper_class("joint"), _RegisteredClass)

    def test_disabled_by_default_ignores_inheritance(self):
        registry = NodeRegistry(_FallbackClass)
        registry.register("transform", _RegisteredClass)
        self.assertIs(registry.wrapper_class("joint"), _FallbackClass)

    def test_exact_match_takes_precedence_over_ancestor(self):
        class _JointClass:
            pass

        registry = NodeRegistry(_FallbackClass, resolve_inherited_types=True)
        registry.register("transform", _RegisteredClass)
        registry.register("joint", _JointClass)
        self.assertIs(registry.wrapper_class("joint"), _JointClass)

    def test_unrecognized_type_falls_back_without_raising(self):
        registry = NodeRegistry(_FallbackClass, resolve_inherited_types=True)
        registry.register("transform", _RegisteredClass)
        self.assertIs(registry.wrapper_class("hlibBogusTypeXYZ"), _FallbackClass)

    def test_no_ancestor_registered_falls_back(self):
        registry = NodeRegistry(_FallbackClass, resolve_inherited_types=True)
        # locator の系統には何も登録しないため、フォールバックのままになる。
        self.assertIs(registry.wrapper_class("locator"), _FallbackClass)


class NodeTypeHierarchyTest(unittest.TestCase):
    """hlib._core.type_hierarchy.inherited_node_types の照会・キャッシュを検証する。"""

    def test_chain_is_self_first_then_ancestors_toward_base(self):
        chain = inherited_node_types("joint")
        self.assertEqual(chain[0], "joint")
        self.assertEqual(chain[-1], "containerBase")
        self.assertIn("transform", chain)
        self.assertLess(chain.index("transform"), chain.index("containerBase"))

    def test_unrecognized_type_returns_itself_only(self):
        self.assertEqual(inherited_node_types("hlibBogusTypeXYZ"), ("hlibBogusTypeXYZ",))

    def test_repeated_calls_return_cached_equal_result(self):
        first = inherited_node_types("locator")
        second = inherited_node_types("locator")
        self.assertEqual(first, second)


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
