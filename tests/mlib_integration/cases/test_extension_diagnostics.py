"""初期化状態と現在の可用性を非ロード診断する入口を検証する。"""
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from maya import cmds
import mlib


class ExtensionDiagnosticsIntegrationTest(unittest.TestCase):
    def test_known_extensions_do_not_load_plugins_or_change_scene(self):
        """同梱拡張の実照会でプラグイン・シーン・型登録が変わらない。"""
        from mlib.core import extensions
        previous = extensions.status()
        plugins = cmds.pluginInfo(query=True, listPlugins=True) or []
        nodes = cmds.ls(long=True) or []
        registry = mlib.nodes.Node._registry._snapshot()
        with patch.object(cmds, "loadPlugin", side_effect=AssertionError("Unexpected plugin load")):
            result = extensions.getDiagnostics()
        self.assertEqual(extensions.status(), previous)
        self.assertEqual(cmds.pluginInfo(query=True, listPlugins=True) or [], plugins)
        self.assertEqual(cmds.ls(long=True) or [], nodes)
        self.assertEqual(mlib.nodes.Node._registry._snapshot(), registry)
        self.assertIn("mlib_bifrost", result)

if __name__ == "__main__":
    unittest.main()
