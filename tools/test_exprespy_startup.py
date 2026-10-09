"""Mayaを起動せず、exprespyの起動予約と失敗後の再試行を検証する。"""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
STARTUP = ROOT / "maya/inhouse/MayaExprespy/exprespyStartup.py"


class ExprespyStartupTest(unittest.TestCase):
    """ユーザー設定に触れず、Mayaのロード入口だけを差し替えて検証する。"""

    def setUp(self):
        self.cmds = mock.Mock()
        self.cmds.about.return_value = False
        self.cmds.pluginInfo.return_value = []
        self.utils = mock.Mock()
        maya = types.ModuleType("maya")
        maya.cmds = self.cmds
        maya.utils = self.utils
        spec = importlib.util.spec_from_file_location("_exprespy_startup_test", STARTUP)
        self.startup = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {"maya": maya}):
            spec.loader.exec_module(self.startup)

    def callback(self):
        """最後に予約した処理を返す。"""
        return self.utils.executeDeferred.call_args[0][0]

    def test_batch_does_not_schedule(self):
        self.cmds.about.return_value = True
        self.startup.initialize()
        self.utils.executeDeferred.assert_not_called()
        self.cmds.loadPlugin.assert_not_called()
        self.assertFalse(self.startup._scheduled)

    def test_pending_registration_is_shared_and_can_schedule_again(self):
        self.startup.initialize()
        self.startup.initialize()
        self.utils.executeDeferred.assert_called_once()
        self.assertTrue(self.startup._scheduled)
        self.callback()()
        self.cmds.loadPlugin.assert_called_once_with("exprespy", quiet=True)
        self.assertFalse(self.startup._scheduled)
        self.startup.initialize()
        self.assertEqual(self.utils.executeDeferred.call_count, 2)

    def test_loaded_plugin_is_skipped_then_can_load_after_unload(self):
        self.cmds.pluginInfo.return_value = ["exprespy", "otherPlugin"]
        self.startup.initialize()
        self.callback()()
        self.cmds.loadPlugin.assert_not_called()
        self.assertFalse(self.startup._scheduled)
        self.cmds.pluginInfo.return_value = None
        self.startup.initialize()
        self.callback()()
        self.cmds.loadPlugin.assert_called_once_with("exprespy", quiet=True)

    def test_failed_load_warns_and_can_retry(self):
        self.cmds.loadPlugin.side_effect = [RuntimeError("load rejected"), None]
        self.startup.initialize()
        self.callback()()
        self.cmds.warning.assert_called_once()
        self.assertIn("load rejected", self.cmds.warning.call_args[0][0])
        self.assertFalse(self.startup._scheduled)
        self.startup.initialize()
        self.callback()()
        self.assertEqual(self.cmds.loadPlugin.call_count, 2)
        self.assertEqual(self.cmds.warning.call_count, 1)

    def test_failed_schedule_warns_and_can_retry(self):
        self.utils.executeDeferred.side_effect = [RuntimeError("queue unavailable"), None]
        self.startup.initialize()
        self.assertFalse(self.startup._scheduled)
        self.cmds.warning.assert_called_once()
        self.assertIn("queue unavailable", self.cmds.warning.call_args[0][0])
        self.startup.initialize()
        self.assertTrue(self.startup._scheduled)
        self.callback()()
        self.cmds.loadPlugin.assert_called_once_with("exprespy", quiet=True)

    def test_queued_callback_checks_batch_again(self):
        self.startup.initialize()
        self.cmds.about.return_value = True
        self.callback()()
        self.cmds.pluginInfo.assert_not_called()
        self.cmds.loadPlugin.assert_not_called()
        self.assertFalse(self.startup._scheduled)


if __name__ == "__main__":
    unittest.main()
