"""hlib.environment.plugin の Plugin を検証するMaya内テスト。"""

import sys
import unittest
from unittest import mock

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.environment import Plugin
from hlib.utils import Version


class PluginTest(unittest.TestCase):
    """既存プラグイン matrixNodes を対象に基本操作を検証する。"""

    pluginName = "matrixNodes"

    def setUp(self):
        self.was_loaded = cmds.pluginInfo(self.pluginName, query=True, loaded=True)
        if not self.was_loaded:
            cmds.loadPlugin(self.pluginName)

    def tearDown(self):
        if self.was_loaded:
            if not cmds.pluginInfo(self.pluginName, query=True, loaded=True):
                cmds.loadPlugin(self.pluginName)
        else:
            if cmds.pluginInfo(self.pluginName, query=True, loaded=True):
                cmds.unloadPlugin(self.pluginName)

    def test_constructor_rejects_invalid_names(self):
        with self.assertRaises(ValueError):
            Plugin("")
        with self.assertRaises(ValueError):
            Plugin(123)

    def test_name_and_string_representations(self):
        plugin = Plugin(self.pluginName)
        self.assertEqual(plugin.name, self.pluginName)
        self.assertEqual(str(plugin), self.pluginName)
        self.assertIn(self.pluginName, repr(plugin))

    def test_is_registered_and_is_loaded_for_known_plugin(self):
        plugin = Plugin(self.pluginName)
        self.assertTrue(plugin.is_registered())
        self.assertTrue(plugin.isLoaded())

    def test_is_registered_and_is_loaded_for_unknown_plugin(self):
        plugin = Plugin("hlibDoesNotExistPlugin123")
        self.assertFalse(plugin.is_registered())
        self.assertFalse(plugin.isLoaded())
        self.assertIsNone(plugin.path())
        self.assertIsNone(plugin.version())

    def test_path_and_version_for_known_plugin(self):
        plugin = Plugin(self.pluginName)
        path = plugin.path()
        self.assertIsInstance(path, str)
        self.assertTrue(path.lower().endswith((".mll", ".py", ".so", ".bundle")))
        self.assertIsInstance(plugin.version(), Version)
        self.assertIsInstance(plugin.version_text(), str)

    def test_unload_load_and_ensure_loaded_round_trip(self):
        plugin = Plugin(self.pluginName)
        self.assertTrue(plugin.isLoaded())

        result = plugin.unload()
        self.assertIs(result, plugin)
        self.assertFalse(plugin.isLoaded())

        result = plugin.ensure_loaded()
        self.assertIs(result, plugin)
        self.assertTrue(plugin.isLoaded())

        # 既にロード済みの状態で ensure_loaded を呼んでもエラーにならない。
        plugin.ensure_loaded()
        self.assertTrue(plugin.isLoaded())

    def test_equality_and_hash(self):
        self.assertEqual(Plugin(self.pluginName), Plugin(self.pluginName))
        self.assertNotEqual(Plugin(self.pluginName), Plugin("otherPlugin"))
        self.assertEqual(hash(Plugin(self.pluginName)), hash(Plugin(self.pluginName)))
        self.assertNotEqual(Plugin(self.pluginName), "not a plugin")

    def test_load_rejects_silent_initialization_failure(self):
        """loadPluginが例外なしで終了しても未ロードなら失敗とする。"""
        plugin = Plugin(self.pluginName)
        with mock.patch.object(cmds, "loadPlugin", return_value=None), \
                mock.patch.object(Plugin, "isLoaded", return_value=False):
            with self.assertRaisesRegex(RuntimeError, self.pluginName):
                plugin.load(quiet=True)

    def test_load_accepts_none_when_already_loaded(self):
        """quiet呼出しの戻り値がNoneでも、ロード済みなら成功する。"""
        plugin = Plugin(self.pluginName)
        with mock.patch.object(cmds, "loadPlugin", return_value=None):
            self.assertIs(plugin.load(quiet=True), plugin)


class PluginListingTest(unittest.TestCase):
    """Plugin.loaded() を検証する。"""

    def test_loaded_includes_known_loaded_plugin(self):
        was_loaded = cmds.pluginInfo("matrixNodes", query=True, loaded=True)
        if not was_loaded:
            cmds.loadPlugin("matrixNodes")
        try:
            loaded = Plugin.loaded()
            self.assertIsInstance(loaded, list)
            self.assertTrue(all(isinstance(item, Plugin) for item in loaded))
            self.assertIn(Plugin("matrixNodes"), loaded)
        finally:
            if not was_loaded:
                cmds.unloadPlugin("matrixNodes")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
