"""hrig の起動処理(Bifrost 3.0.0 以降の確認とロード)を検証するMaya内テスト。

確認とロードの本体は hlib.general.PluginPackage(test_plugin_requirements.py が詳細を検証する)。
ここでは Bifrost 用の設定と起動のタイミングを確認する。
"""
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

import maya.cmds as cmds

MODULE_PATH = Path(__file__).resolve().parents[2] / "hrig" / "startup" / "hrig_bifrost_startup.py"


def load_module():
    spec = importlib.util.spec_from_file_location("hrig_bifrost_startup_under_test", str(MODULE_PATH))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clean_environment():
    env = dict(os.environ)
    env.pop("HRIG_BIFROST_MIN_VERSION", None)
    env.pop("HRIG_SKIP_BIFROST", None)
    return mock.patch.dict(os.environ, env, clear=True)


class ConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()
        env = clean_environment()
        env.start()
        self.addCleanup(env.stop)

    def test_package_definition(self):
        package = self.mod.package()
        self.assertEqual(package.name(), "Bifrost")
        self.assertEqual([p.name() for p in package.plugins()], ["mayaVnnPlugin", "bifrostGraph", "flowWedging"])
        self.assertEqual(str(package.module()), "Bifrost")
        self.assertEqual(package.minimum_version().parts, (3, 0, 0))
        self.assertEqual(package.minimum_maya(), 2025)

    def test_minimum_version_env_override(self):
        with mock.patch.dict(os.environ, {"HRIG_BIFROST_MIN_VERSION": "99.1"}):
            self.assertEqual(self.mod.package().minimum_version().parts, (99, 1))
        with mock.patch.dict(os.environ, {"HRIG_BIFROST_MIN_VERSION": "bad"}):
            self.assertEqual(self.mod.package().minimum_version().parts, (3, 0, 0))

    def test_run_delegates_to_the_package(self):
        with mock.patch("hlib.general.PluginPackage.ensure_loaded", return_value="missing") as ensure:
            self.assertEqual(self.mod.run(dialog=False), "missing")
        ensure.assert_called_once_with(dialog=False)


class InitializeTest(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()
        env = clean_environment()
        env.start()
        self.addCleanup(env.stop)

    def test_batch_session_does_nothing(self):
        with mock.patch.object(self.mod.maya_utils, "executeDeferred") as deferred:
            self.mod.initialize()
        deferred.assert_not_called()
        self.assertFalse(self.mod._scheduled)

    def test_skip_environment_variable(self):
        gui = mock.Mock()
        gui.about.return_value = False
        with mock.patch.object(self.mod, "cmds", gui), \
                mock.patch.dict(os.environ, {"HRIG_SKIP_BIFROST": "1"}), \
                mock.patch.object(self.mod.maya_utils, "executeDeferred") as deferred:
            self.mod.initialize()
        deferred.assert_not_called()

    def test_gui_session_schedules_once(self):
        gui = mock.Mock()
        gui.about.return_value = False
        with mock.patch.object(self.mod, "cmds", gui), \
                mock.patch.object(self.mod.maya_utils, "executeDeferred") as deferred:
            self.mod.initialize()
            self.mod.initialize()
        self.assertEqual(deferred.call_count, 1)


class InstalledBifrostTest(unittest.TestCase):
    """実際に導入されている Bifrost での確認(Maya 2025以降で 3.0.0 以降が導入済みの場合)。"""

    def setUp(self):
        self.mod = load_module()
        env = clean_environment()
        env.start()
        self.addCleanup(env.stop)
        year = int(str(cmds.about(version=True)).split(".")[0])
        if year < 2025 or not self.mod.package().is_installed():
            self.skipTest("Maya 2025以降でBifrost 3.0.0以降が導入された環境でのみ実行する")

    def test_run_loads_all_plugins(self):
        shown = []
        self.assertEqual(self.mod.run(dialog=shown.append), "loaded")
        self.assertEqual(shown, [])
        for name in self.mod.PLUGINS:
            self.assertTrue(cmds.pluginInfo(name, query=True, loaded=True), name)

    def test_run_reports_missing_when_minimum_is_too_high(self):
        shown = []
        with mock.patch.dict(os.environ, {"HRIG_BIFROST_MIN_VERSION": "99.0.0"}):
            self.assertEqual(self.mod.run(dialog=shown.append), "missing")
        self.assertEqual(len(shown), 1)
        self.assertIn("99.0.0", shown[0])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
