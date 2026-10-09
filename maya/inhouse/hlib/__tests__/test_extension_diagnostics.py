"""初期化状態と現在の可用性を非ロード診断する入口を検証する。"""
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from maya import cmds
import hlib


class ExtensionDiagnosticsTest(unittest.TestCase):
    def test_current_availability_is_separate_from_initialization(self):
        """現在利用可能でも初期化結果を更新せず、返却を独立した値にする。"""
        from hlib._core import extensions
        name = "hlib_fixture_diag"
        module = ModuleType(name)
        module.HLIB_EXTENSION_API = 1
        module.is_available = Mock(return_value=True)
        states = {name: {"state": "unavailable", "reason": "initial dependency missing"}}
        with patch.dict(sys.modules, {name: module}), patch.object(extensions, "_states", states), \
                patch.object(extensions.importlib, "import_module", side_effect=AssertionError("New import")), \
                patch.object(extensions, "_apply_entries", side_effect=AssertionError("Registration")):
            diagnostic = extensions.diagnostics()[name]
            self.assertTrue(diagnostic["available"])
            self.assertEqual(diagnostic["initialization"]["state"], "unavailable")
            diagnostic["initialization"]["state"] = "modified"
            self.assertEqual(extensions.status()[name]["state"], "unavailable")
            self.assertEqual(module.is_available.call_count, 1)

    def test_failed_missing_and_non_bool_queries_are_unknown(self):
        """照会失敗を未導入Falseと混同せず、理由へ残す。"""
        from hlib._core import extensions
        modules = {}
        for suffix, query in (("error", Mock(side_effect=RuntimeError("dependency broken"))),
                              ("invalid", Mock(return_value=1)), ("false", Mock(return_value=False))):
            module = ModuleType("hlib_fixture_diag_" + suffix)
            module.HLIB_EXTENSION_API = 1
            module.is_available = query
            modules[module.__name__] = module
        absent = "hlib_fixture_diag_absent"
        with patch.dict(sys.modules, modules), patch.object(extensions, "_states", {absent: {"state": "error", "reason": "initial"}}):
            result = extensions.getDiagnostics()
            self.assertIsNone(result[absent]["available"])
            self.assertIn("not imported", result[absent]["reason"])
            self.assertIsNone(result["hlib_fixture_diag_error"]["available"])
            self.assertEqual(result["hlib_fixture_diag_error"]["reason"], "dependency broken")
            self.assertIsNone(result["hlib_fixture_diag_invalid"]["available"])
            self.assertIn("must return bool", result["hlib_fixture_diag_invalid"]["reason"])
            self.assertFalse(result["hlib_fixture_diag_false"]["available"])
            self.assertIsNone(result["hlib_fixture_diag_false"]["initialization"])

    def test_initializing_and_unsupported_declarations_are_not_called(self):
        """初期化途中や未対応宣言を再入させない。"""
        from hlib._core import extensions
        busy, unsupported = ModuleType("hlib_fixture_diag_busy"), ModuleType("hlib_fixture_diag_unmarked")
        busy.HLIB_EXTENSION_API = 1
        busy.__spec__ = SimpleNamespace(_initializing=True)
        busy.is_available = Mock()
        unsupported.is_available = Mock()
        with patch.dict(sys.modules, {busy.__name__: busy, unsupported.__name__: unsupported}):
            result = extensions.getDiagnostics()
            self.assertIsNone(result[busy.__name__]["available"])
            self.assertIn("in progress", result[busy.__name__]["reason"])
            self.assertIsNone(result[unsupported.__name__]["available"])
            busy.is_available.assert_not_called()
            unsupported.is_available.assert_not_called()

    def test_reentrant_diagnostics_are_bounded(self):
        """宣言の照会から診断へ再入しても繰り返し照会しない。"""
        from hlib._core import extensions
        module = ModuleType("hlib_fixture_diag_reentrant")
        module.HLIB_EXTENSION_API = 1
        nested = []

        def query():
            nested.append(extensions.diagnostics()[module.__name__])
            return True

        module.is_available = query
        with patch.dict(sys.modules, {module.__name__: module}):
            self.assertTrue(extensions.getDiagnostics()[module.__name__]["available"])
        self.assertEqual(len(nested), 1)
        self.assertIsNone(nested[0]["available"])
        self.assertIn("query is in progress", nested[0]["reason"])

    def test_known_extensions_do_not_load_plugins_or_change_scene(self):
        """同梱拡張の実照会でプラグイン・シーン・型登録が変わらない。"""
        from hlib._core import extensions
        previous = extensions.status()
        plugins = cmds.pluginInfo(query=True, listPlugins=True) or []
        nodes = cmds.ls(long=True) or []
        registry = hlib.nodes.Node._registry._snapshot()
        with patch.object(cmds, "loadPlugin", side_effect=AssertionError("Unexpected plugin load")):
            result = extensions.diagnostics()
        self.assertEqual(extensions.status(), previous)
        self.assertEqual(cmds.pluginInfo(query=True, listPlugins=True) or [], plugins)
        self.assertEqual(cmds.ls(long=True) or [], nodes)
        self.assertEqual(hlib.nodes.Node._registry._snapshot(), registry)
        self.assertIn("hlib_bifrost", result)


if __name__ == "__main__":
    unittest.main()
