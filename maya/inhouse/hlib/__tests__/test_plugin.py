"""hlib.scenes.plugin の Plugin/Plugins を検証するMaya内テスト。"""

import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.scenes import Plugin, Plugins


class PluginTest(unittest.TestCase):
    """既存プラグイン matrixNodes を対象に基本操作を検証する。"""

    plugin_name = "matrixNodes"

    def setUp(self):
        self.was_loaded = cmds.pluginInfo(self.plugin_name, query=True, loaded=True)
        if not self.was_loaded:
            cmds.loadPlugin(self.plugin_name)

    def tearDown(self):
        if self.was_loaded:
            if not cmds.pluginInfo(self.plugin_name, query=True, loaded=True):
                cmds.loadPlugin(self.plugin_name)
        else:
            if cmds.pluginInfo(self.plugin_name, query=True, loaded=True):
                cmds.unloadPlugin(self.plugin_name)

    def test_constructor_rejects_invalid_names(self):
        with self.assertRaises(ValueError):
            Plugin("")
        with self.assertRaises(ValueError):
            Plugin(123)

    def test_name_and_string_representations(self):
        plugin = Plugin(self.plugin_name)
        self.assertEqual(plugin.name(), self.plugin_name)
        self.assertEqual(str(plugin), self.plugin_name)
        self.assertIn(self.plugin_name, repr(plugin))

    def test_is_registered_and_is_loaded_for_known_plugin(self):
        plugin = Plugin(self.plugin_name)
        self.assertTrue(plugin.is_registered())
        self.assertTrue(plugin.is_loaded())

    def test_is_registered_and_is_loaded_for_unknown_plugin(self):
        plugin = Plugin("hlibDoesNotExistPlugin123")
        self.assertFalse(plugin.is_registered())
        self.assertFalse(plugin.is_loaded())
        self.assertIsNone(plugin.path())
        self.assertIsNone(plugin.version())

    def test_path_and_version_for_known_plugin(self):
        plugin = Plugin(self.plugin_name)
        path = plugin.path()
        self.assertIsInstance(path, str)
        self.assertTrue(path.lower().endswith((".mll", ".py", ".so", ".bundle")))
        self.assertIsInstance(plugin.version(), str)

    def test_unload_load_and_ensure_loaded_round_trip(self):
        plugin = Plugin(self.plugin_name)
        self.assertTrue(plugin.is_loaded())

        result = plugin.unload()
        self.assertIs(result, plugin)
        self.assertFalse(plugin.is_loaded())

        result = plugin.ensure_loaded()
        self.assertIs(result, plugin)
        self.assertTrue(plugin.is_loaded())

        # 既にロード済みの状態で ensure_loaded を呼んでもエラーにならない。
        plugin.ensure_loaded()
        self.assertTrue(plugin.is_loaded())

    def test_equality_and_hash(self):
        self.assertEqual(Plugin(self.plugin_name), Plugin(self.plugin_name))
        self.assertNotEqual(Plugin(self.plugin_name), Plugin("otherPlugin"))
        self.assertEqual(hash(Plugin(self.plugin_name)), hash(Plugin(self.plugin_name)))
        self.assertNotEqual(Plugin(self.plugin_name), "not a plugin")


class PluginsTest(unittest.TestCase):
    """Plugins コレクションの重複除去と loaded() を検証する。"""

    def test_constructor_dedupes_by_name(self):
        collection = Plugins(["matrixNodes", "matrixNodes", Plugin("matrixNodes")])
        self.assertEqual(len(collection), 1)
        self.assertEqual([item.name() for item in collection], ["matrixNodes"])

    def test_loaded_includes_known_loaded_plugin(self):
        was_loaded = cmds.pluginInfo("matrixNodes", query=True, loaded=True)
        if not was_loaded:
            cmds.loadPlugin("matrixNodes")
        try:
            loaded = Plugins.loaded()
            self.assertIn(Plugin("matrixNodes"), list(loaded))
        finally:
            if not was_loaded:
                cmds.unloadPlugin("matrixNodes")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
