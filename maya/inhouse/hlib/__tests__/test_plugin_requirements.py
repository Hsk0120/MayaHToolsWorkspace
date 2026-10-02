"""hlib.environment の版比較・Module・PluginPackage と hlib.requirePlugins を検証するMaya内テスト。"""

import sys
import unittest
from unittest import mock

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.environment import LOAD_FAILED
from hlib.environment import LOADED
from hlib.environment import MISSING
from hlib.environment import OUTDATED
from hlib.environment import SKIPPED
from hlib.environment import Module
from hlib.environment import Plugin
from hlib.environment import PluginPackage
from hlib.utils import Version
import hlib.environment.pluginPackage as package_module


class PluginVersionTest(unittest.TestCase):
    plugin_name = "matrixNodes"

    def setUp(self):
        self.was_loaded = cmds.pluginInfo(self.plugin_name, query=True, loaded=True)
        if not self.was_loaded:
            cmds.loadPlugin(self.plugin_name)

    def tearDown(self):
        if not self.was_loaded and cmds.pluginInfo(self.plugin_name, query=True, loaded=True):
            cmds.unloadPlugin(self.plugin_name)

    def test_version_parts_match_version_string(self):
        plugin = Plugin(self.plugin_name)
        self.assertEqual(plugin.version().parts, Version.parse(plugin.version_text()).parts)

    def test_is_version_at_least(self):
        plugin = Plugin(self.plugin_name)
        self.assertTrue(plugin.is_version_at_least("0"))
        self.assertFalse(plugin.is_version_at_least("999999"))
        with self.assertRaises(ValueError):
            plugin.is_version_at_least("bad")

    def test_unknown_plugin_has_no_version(self):
        plugin = Plugin("hlibDoesNotExistPlugin123")
        self.assertIsNone(plugin.version())
        self.assertFalse(plugin.is_version_at_least("0"))


class ModuleTest(unittest.TestCase):
    def test_constructor_rejects_invalid_names(self):
        for bad in ("", None, 3):
            with self.assertRaises(ValueError):
                Module(bad)

    def test_unknown_module(self):
        module = Module("hlibDoesNotExistModule123")
        self.assertFalse(module.is_registered())
        self.assertIsNone(module.version())
        self.assertIsNone(module.path())
        self.assertFalse(module.is_version_at_least("0"))

    def test_registered_module_matches_moduleInfo(self):
        modules = cmds.moduleInfo(listModules=True) or []
        if not modules:
            self.skipTest("登録済みモジュールが無い")
        name = modules[0]
        module = Module(name)
        self.assertTrue(module.is_registered())
        self.assertEqual(module.version_text(), cmds.moduleInfo(version=True, moduleName=name) or None)
        self.assertEqual(module.version(), Version.parse(module.version_text()))
        self.assertEqual(module.path(), cmds.moduleInfo(path=True, moduleName=name) or None)

    def test_equality_hash_and_repr(self):
        # 他のテストが hlib.reload() を呼んでも古いクラスを掴まないよう、都度 hlib.environment から取得する。
        module_class = hlib.environment.Module
        self.assertEqual(module_class("a"), module_class("a"))
        self.assertNotEqual(module_class("a"), module_class("b"))
        self.assertNotEqual(module_class("a"), "a")
        self.assertEqual(len({module_class("a"), module_class("a")}), 1)
        self.assertEqual(str(module_class("a")), "a")
        self.assertIn("a", repr(module_class("a")))


class FakeCmds(object):
    """cmds のうち PluginPackage が使う関数だけを持つ代役。"""

    def __init__(self, year="2027", batch=False):
        self.year = year
        self.batch = batch
        self.warnings = []
        self.dialogs = []

    def about(self, version=False, batch=False):
        return self.year if version else self.batch

    def warning(self, text):
        self.warnings.append(text)

    def confirmDialog(self, **kwargs):
        self.dialogs.append(kwargs)


class PluginPackageFlowTest(unittest.TestCase):
    """導入状況ごとの動作(Maya のバージョンやインストール状況に依存しない)。"""

    def setUp(self):
        self.fake = FakeCmds("2027")
        self.shown = []
        patcher = mock.patch.object(package_module, "cmds", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        warning_patcher = mock.patch.object(package_module.logger, "warning", self.fake.warning)
        warning_patcher.start()
        self.addCleanup(warning_patcher.stop)

    def make(self, **kwargs):
        options = dict(plugins=("pluginA", "pluginB"), module="ModuleX", version_plugin="pluginA",
                       minimum_version="3.0.0", minimum_maya=2025)
        options.update(kwargs)
        return PluginPackage("ProductX", **options)

    def run_flow(self, package, installed, loaded_version=None, failed=()):
        with mock.patch.object(PluginPackage, "installed_version", return_value=Version.parse(installed)), \
                mock.patch.object(PluginPackage, "loaded_version", return_value=Version.parse(loaded_version)), \
                mock.patch.object(PluginPackage, "load_plugins", return_value=list(failed)) as loader:
            result = package.try_load(dialog=self.shown.append)
        return result, loader

    def test_constructor_validation(self):
        for bad in ("", None):
            with self.assertRaises(ValueError):
                PluginPackage(bad, plugins=("a",))
        with self.assertRaises(ValueError):
            PluginPackage("x")
        with self.assertRaises(ValueError):
            PluginPackage("x", plugins=("a",), minimum_version="bad")
        with self.assertRaises(ValueError):
            Plugin(3)

    def test_accessors_and_defaults(self):
        package = self.make()
        self.assertEqual(package.name, "ProductX")
        self.assertEqual([p.name for p in package.plugins], ["pluginA", "pluginB"])
        self.assertEqual(str(package.module), "ModuleX")
        self.assertEqual(package.minimum_version, Version((3, 0, 0)))
        self.assertEqual(package.minimum_maya, 2025)
        self.assertIn("ProductX", repr(package))
        default = PluginPackage("y", plugins=("first", "second"))
        self.assertIsNone(default.module)
        self.assertIsNone(default.minimum_version)
        self.assertIsNone(default.minimum_maya)

    def test_old_maya_is_skipped(self):
        self.fake.year = "2024"
        result, loader = self.run_flow(self.make(), (3, 0, 0, 0))
        self.assertEqual(result, SKIPPED)
        loader.assert_not_called()
        self.assertEqual(self.shown, [])

    def test_supported_version_loads_without_dialog(self):
        result, loader = self.run_flow(self.make(), (3, 0, 0, 0), loaded_version=(3, 0, 0, 0))
        self.assertEqual(result, LOADED)
        loader.assert_called_once_with()
        self.assertEqual(self.shown, [])
        self.assertEqual(self.fake.warnings, [])

    def test_newer_version_is_accepted(self):
        result, _ = self.run_flow(self.make(), (3, 1, 0, 8), loaded_version=(3, 1, 0, 8))
        self.assertEqual(result, LOADED)

    def test_missing_shows_dialog_and_does_not_load(self):
        result, loader = self.run_flow(self.make(), None)
        self.assertEqual(result, MISSING)
        loader.assert_not_called()
        self.assertEqual(len(self.shown), 1)
        for text in ("ProductX 3.0.0", "インストール", "2027", "なし"):
            self.assertIn(text, self.shown[0])
        self.assertEqual(len(self.fake.warnings), 1)

    def test_old_version_is_missing(self):
        result, loader = self.run_flow(self.make(), (2, 15, 0, 0))
        self.assertEqual(result, MISSING)
        loader.assert_not_called()
        self.assertIn("2.15.0.0", self.shown[0])

    def test_already_loaded_old_plugin_is_reported(self):
        result, _ = self.run_flow(self.make(), (3, 0, 0, 0), loaded_version=(2, 15, 0, 0))
        self.assertEqual(result, OUTDATED)
        self.assertEqual(len(self.shown), 1)

    def test_load_failure_is_reported_without_dialog(self):
        result, _ = self.run_flow(self.make(), (3, 0, 0, 0), failed=["pluginB"])
        self.assertEqual(result, LOAD_FAILED)
        self.assertEqual(self.shown, [])

    def test_no_minimum_version_only_needs_installation(self):
        package = self.make(minimum_version=None)
        result, loader = self.run_flow(package, (1, 0))
        self.assertEqual(result, LOADED)
        loader.assert_called_once_with()

    def test_dialog_options(self):
        package = self.make()
        with mock.patch.object(PluginPackage, "installed_version", return_value=None):
            self.assertEqual(package.try_load(dialog=False, warn=False), MISSING)
            self.assertEqual(self.fake.dialogs, [])
            self.assertEqual(self.fake.warnings, [])
            self.assertEqual(package.try_load(), MISSING)
        self.assertEqual(len(self.fake.dialogs), 1)
        self.assertIn("ProductX", self.fake.dialogs[0]["title"])
        self.assertEqual(self.fake.dialogs[0]["icon"], "warning")

    def test_dialog_is_skipped_in_batch(self):
        self.fake.batch = True
        package = self.make()
        with mock.patch.object(PluginPackage, "installed_version", return_value=None):
            self.assertEqual(package.try_load(), MISSING)
        self.assertEqual(self.fake.dialogs, [])

    def test_custom_install_hint(self):
        package = self.make(install_hint="社内サーバーから入手してください。")
        self.assertIn("社内サーバー", package.message())


class PluginPackageRealTest(unittest.TestCase):
    """実際の Maya に対する確認。"""

    def test_unknown_package_is_not_installed(self):
        package = PluginPackage("Unknown", plugins=("hlibDoesNotExistPlugin123",),
                                module="hlibDoesNotExistModule123", minimum_version="1.0")
        self.assertIsNone(package.installed_version())
        self.assertIsNone(package.loaded_version())
        self.assertFalse(package.is_installed())
        shown = []
        self.assertEqual(package.try_load(dialog=shown.append), MISSING)
        self.assertEqual(len(shown), 1)

    def test_standard_plugin_package_loads(self):
        name = "matrixNodes"
        was_loaded = cmds.pluginInfo(name, query=True, loaded=True)
        try:
            package = PluginPackage("Matrix nodes", plugins=(name,))
            self.assertEqual(package.try_load(dialog=False), LOADED)
            self.assertTrue(package.is_installed())
            self.assertTrue(cmds.pluginInfo(name, query=True, loaded=True))
            self.assertEqual(package.loaded_version(), Plugin(name).version())
        finally:
            if not was_loaded and cmds.pluginInfo(name, query=True, loaded=True):
                cmds.unloadPlugin(name)

    def test_unknown_package_without_minimum_version_is_missing_after_load_fails(self):
        package = PluginPackage("Unknown", plugins=("hlibDoesNotExistPlugin123",))
        shown = []
        self.assertEqual(package.try_load(dialog=shown.append), MISSING)
        self.assertEqual(len(shown), 1)

    def test_installed_version_falls_back_to_plugin_version(self):
        package = PluginPackage("Matrix nodes", plugins=("matrixNodes",), module="hlibDoesNotExistModule123")
        self.assertEqual(package.installed_version(), Plugin("matrixNodes").version())


class RequirePluginsCommandTest(unittest.TestCase):
    def test_exposed_at_top_level(self):
        self.assertIs(hlib.requirePlugins, hlib.cmds.requirePlugins)

    def test_missing_product_reports_through_dialog_callback(self):
        shown = []
        result = hlib.requirePlugins(("hlibDoesNotExistPlugin123",), minimum_version="1.0",
                                     module="hlibDoesNotExistModule123", name="Unknown",
                                     dialog=shown.append)
        self.assertEqual(result, "missing")
        self.assertEqual(len(shown), 1)
        self.assertIn("Unknown 1.0", shown[0])

    def test_single_string_plugin_and_default_name(self):
        shown = []
        result = hlib.requirePlugins("hlibDoesNotExistPlugin123", minimum_version=(1, 0), dialog=shown.append)
        self.assertEqual(result, "missing")
        self.assertIn("hlibDoesNotExistPlugin123", shown[0])

    def test_old_maya_is_skipped(self):
        year = int(str(cmds.about(version=True)).split(".")[0])
        self.assertEqual(hlib.requirePlugins("hlibDoesNotExistPlugin123", minimum_maya=year + 1,
                                             dialog=False), "skipped")

    def test_input_validation(self):
        with self.assertRaises(ValueError):
            hlib.requirePlugins(())
        with self.assertRaises(ValueError):
            hlib.requirePlugins("a", minimum_version="bad")

    def test_loads_a_standard_plugin(self):
        name = "matrixNodes"
        was_loaded = cmds.pluginInfo(name, query=True, loaded=True)
        try:
            self.assertEqual(hlib.requirePlugins(name, dialog=False), "loaded")
            self.assertTrue(cmds.pluginInfo(name, query=True, loaded=True))
        finally:
            if not was_loaded and cmds.pluginInfo(name, query=True, loaded=True):
                cmds.unloadPlugin(name)


class BifrostTest(unittest.TestCase):
    """実際に導入されている Bifrost での確認(Maya 2025以降で 3.0.0 以降が導入済みの場合)。"""

    def setUp(self):
        year = int(str(cmds.about(version=True)).split(".")[0])
        self.package = PluginPackage("Bifrost", plugins=("mayaVnnPlugin", "bifrostGraph", "flowWedging"),
                                     module="Bifrost", version_plugin="bifrostGraph",
                                     minimum_version="3.0.0", minimum_maya=2025)
        if year < 2025 or not self.package.is_installed():
            self.skipTest("Maya 2025以降でBifrost 3.0.0以降が導入された環境でのみ実行する")

    def test_try_load(self):
        shown = []
        self.assertEqual(self.package.try_load(dialog=shown.append), LOADED)
        self.assertEqual(shown, [])
        for plugin in self.package.plugins:
            self.assertTrue(plugin.is_loaded(), plugin.name)
        self.assertTrue(self.package.loaded_version().is_at_least("3.0.0"))

    def test_too_new_version_is_reported_missing(self):
        package = PluginPackage("Bifrost", plugins=("bifrostGraph",), module="Bifrost", minimum_version="99.0")
        shown = []
        self.assertEqual(package.try_load(dialog=shown.append), MISSING)
        self.assertIn("99.0", shown[0])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
