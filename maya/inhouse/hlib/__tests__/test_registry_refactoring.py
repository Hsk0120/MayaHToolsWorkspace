"""型継承の状態変更と、拡張の検証失敗からの回復を検証する。"""

import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import maya.cmds as cmds
import hlib
from hlib._core import typeHierarchy
from hlib._core.registry import NodeRegistry
from hlib.common.plugin import Plugin


class TypeHierarchyStateTest(unittest.TestCase):
    """未知型の導入とPlugin操作後の型選択を確認する。"""

    def setUp(self):
        """他テストのキャッシュを判定に含めない。"""
        typeHierarchy.clear_cache()

    def tearDown(self):
        """模擬した型の結果を後続テストへ残さない。"""
        typeHierarchy.clear_cache()

    def test_unknown_type_is_queried_again_after_becoming_available(self):
        """照会の失敗・空結果の後に、導入済みの継承型を選べる。"""
        for missing in (RuntimeError("Unknown node type"), None, []):
            with self.subTest(missing=repr(missing)):
                typeHierarchy.clear_cache()
                registry = NodeRegistry(object, resolve_inherited_types=True)
                registry.register("locator", str)
                with mock.patch.object(cmds, "nodeType", side_effect=[missing, ["dependNode", "locator", "optionalLocator"]]) as query:
                    self.assertIs(registry.wrapper_class("optionalLocator"), object)
                    self.assertIs(registry.wrapper_class("optionalLocator"), str)
                    self.assertIs(registry.wrapper_class("optionalLocator"), str)
                self.assertEqual(query.call_count, 2)

    def test_successful_plugin_operations_refresh_registered_ancestor(self):
        """正常なload/unloadの後に同じ型名を照会し直す。"""
        for operation in ("load", "unload"):
            with self.subTest(operation=operation):
                typeHierarchy.clear_cache()
                registry = NodeRegistry(object, resolve_inherited_types=True)
                registry.register("transform", str)
                registry.register("locator", int)
                plugin = Plugin("fixturePlugin")
                command = "loadPlugin" if operation == "load" else "unloadPlugin"
                with mock.patch.object(cmds, "nodeType", side_effect=[
                        ["dependNode", "transform", "optionalNode"],
                        ["dependNode", "locator", "optionalNode"]]) as query, \
                        mock.patch.object(cmds, command, return_value=None), \
                        mock.patch.object(Plugin, "isLoaded", return_value=True):
                    self.assertIs(registry.wrapper_class("optionalNode"), str)
                    self.assertIs(getattr(plugin, operation)(), plugin)
                    self.assertIs(registry.wrapper_class("optionalNode"), int)
                self.assertEqual(query.call_count, 2)

    def test_rejected_plugin_operations_preserve_cached_result(self):
        """標準コマンドが拒否したload/unloadでは既存結果を失わない。"""
        for operation in ("load", "unload"):
            with self.subTest(operation=operation):
                typeHierarchy.clear_cache()
                command = "loadPlugin" if operation == "load" else "unloadPlugin"
                with mock.patch.object(cmds, "nodeType", return_value=["dependNode", "fixtureNode"]) as query:
                    before = typeHierarchy.inherited_node_types("fixtureNode")
                    with mock.patch.object(cmds, command, side_effect=RuntimeError("Rejected")):
                        with self.assertRaisesRegex(RuntimeError, "Rejected"):
                            getattr(Plugin("fixturePlugin"), operation)()
                    self.assertIs(typeHierarchy.inherited_node_types("fixtureNode"), before)
                self.assertEqual(query.call_count, 1)

    def test_silent_load_failure_preserves_cache_and_existing_error(self):
        """例外なしの初期化失敗も、成功扱いやキャッシュ解除をしない。"""
        with mock.patch.object(cmds, "nodeType", return_value=["dependNode", "fixtureNode"]) as query:
            before = typeHierarchy.inherited_node_types("fixtureNode")
            with mock.patch.object(cmds, "loadPlugin", return_value=None), \
                    mock.patch.object(Plugin, "isLoaded", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "Plugin initialization did not complete"):
                    Plugin("fixturePlugin").load()
            self.assertIs(typeHierarchy.inherited_node_types("fixtureNode"), before)
        self.assertEqual(query.call_count, 1)

    def test_native_plugin_round_trip_refreshes_successful_queries(self):
        """実Mayaの標準プラグインload/unloadでも成功結果を照会し直す。"""
        plugin = Plugin("matrixNodes")
        was_loaded = plugin.isLoaded()
        try:
            with mock.patch.object(cmds, "nodeType", wraps=cmds.nodeType) as query:
                before = typeHierarchy.inherited_node_types("locator")
                self.assertEqual(typeHierarchy.inherited_node_types("locator"), before)
                plugin.load(quiet=True)
                self.assertEqual(typeHierarchy.inherited_node_types("locator"), before)
                plugin.unload()
                self.assertEqual(typeHierarchy.inherited_node_types("locator"), before)
            self.assertEqual(query.call_count, 3)
        finally:
            if was_loaded and not plugin.isLoaded():
                plugin.load(quiet=True)
            elif not was_loaded and plugin.isLoaded():
                plugin.unload()


class ExtensionStageRecoveryTest(unittest.TestCase):
    """import成功後の検証失敗も、一回のreloadで新しい宣言に更新する。"""

    def test_availability_and_declaration_errors_recover_on_reload(self):
        """可用性・後続のPlug宣言の失敗ではNodeを部分登録しない。"""
        with tempfile.TemporaryDirectory(prefix="hlib_extension_stages_") as directory:
            name = "hlib_fixture_stage_recovery"
            folder = Path(directory) / name
            folder.mkdir()
            declaration = folder / "__init__.py"
            declaration.write_text(
                'HLIB_EXTENSION_API = 1\ndef is_available(): raise RuntimeError("SDK not ready")\n',
                encoding="utf-8")
            for suffix, body in (
                    ("nodes", 'from hlib.nodes import Node\nclass StageNode(Node): pass\n'
                     '_WRAPPER_CLASSES = {"fixtureStageRecovery": StageNode}\n'),
                    ("plugs", '_WRAPPER_CLASSES = {"fixtureStageData": object()}\n')):
                (folder / suffix).mkdir()
                (folder / suffix / "__init__.py").write_text(body, encoding="utf-8")
            sys.path.insert(0, directory)
            try:
                importlib.invalidate_caches()
                hlib.reload()
                self.assertEqual(hlib._core.extensions.status()[name]["reason"], "SDK not ready")
                declaration.write_text('HLIB_EXTENSION_API = 1\ndef is_available(): return True\n', encoding="utf-8")
                hlib.reload()
                self.assertEqual(hlib._core.extensions.status()[name]["state"], "error")
                self.assertIsNone(hlib.nodes.Node._registry.lookup("fixtureStageRecovery"))
                (folder / "plugs" / "__init__.py").write_text(
                    'from hlib.plugs import Plug\nclass StagePlug(Plug): pass\n'
                    '_WRAPPER_CLASSES = {"fixtureStageData": StagePlug}\n', encoding="utf-8")
                hlib.reload()
                self.assertEqual(hlib._core.extensions.status()[name]["state"], "loaded")
                self.assertIsNotNone(hlib.nodes.Node._registry.lookup("fixtureStageRecovery"))
                self.assertIsNotNone(hlib.plugs.Plug._registry.lookup("fixtureStageData"))
            finally:
                sys.path.remove(directory)
                hlib.reload()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
