"""明示的なNode/Plug登録と、入力に応じた型選択をMaya内で検証する。"""

import sys
import unittest

import hlib
hlib.reload()
from hlib._core.registry import NodeRegistry
from hlib._core.typeHierarchy import inherited_node_types


class _FallbackClass:
    def __init__(self, value=None):
        self.value = value


class _RegisteredClass:
    def __init__(self, value=None):
        self.value = value


class NodeRegistryTest(unittest.TestCase):
    """register/get/lookup/wrapper_class/clear/replace の基本動作を検証する。"""

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

    def test_replace_replaces_existing_registrations(self):
        self.registry.register("staleType", _RegisteredClass)
        self.registry.replace({"myType": _RegisteredClass})
        self.assertIs(self.registry.wrapper_class("staleType"), _FallbackClass)
        self.assertIs(self.registry.get("myType"), _RegisteredClass)

    def test_replace_validates_all_entries_before_changing_registry(self):
        """不正な後続エントリーで、既存登録を失わず部分登録もしない。"""
        self.registry.register("staleType", _RegisteredClass)
        for invalid, exception in (({"validType": _FallbackClass, "": _RegisteredClass}, ValueError),
                                   ({"validType": _FallbackClass, "invalidType": object()}, TypeError)):
            with self.assertRaises(exception):
                self.registry.replace(invalid)
            self.assertIs(self.registry.lookup("staleType"), _RegisteredClass)
            self.assertIsNone(self.registry.lookup("validType"))


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
    """hlib._core.typeHierarchy.inherited_node_types の照会・キャッシュを検証する。"""

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


class ExplicitRegistrationsTest(unittest.TestCase):
    """公開一覧から独立した明示的な型対応表を検証する。"""

    def test_node_table_matches_initialized_registry(self):
        """Nodeの型対応表に書いたクラスを既存の取得入口で選択する。"""
        registry = hlib.nodes.Node._registry
        for node_type, wrapper in hlib.nodes._WRAPPER_CLASSES.items():
            self.assertIs(registry.lookup(node_type), wrapper)
        self.assertIs(registry.wrapper_class("joint"), hlib.nodes.Joint)
        self.assertIs(registry.wrapper_class("mesh"), hlib.nodes.Mesh)

    def test_plug_table_matches_initialized_registry(self):
        """Plugの型対応表が公開クラスの登録漏れなく初期化される。"""
        registry = hlib.plugs.Plug._registry
        for attr_type, wrapper in hlib.plugs._WRAPPER_CLASSES.items():
            self.assertIs(registry.lookup(attr_type), wrapper)
        self.assertIs(registry.lookup("double"), hlib.plugs.DoublePlug)

    def test_publication_does_not_require_metadata_decorators(self):
        """公開・登録済みクラスへ旧自動検出用メタデータを要求しない。"""
        for wrapper in (hlib.nodes.Joint, hlib.nodes.Joints, hlib.plugs.DoublePlug):
            for name in ("__hlib_node_type__", "__hlib_plug_type__", "__hlib_public__", "__hlib_collection__"):
                self.assertNotIn(name, wrapper.__dict__)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
