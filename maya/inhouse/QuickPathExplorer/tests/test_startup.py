"""Maya不要で起動ブートストラップと年別module設定の契約を確認する。"""

from pathlib import Path
import runpy
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


class StartupTest(unittest.TestCase):
    """起動順序、既存ロード、バッチ、失敗時の境界を確認する。"""

    def setUp(self):
        """Mayaの副作用を持たない代替コマンドを用意する。"""
        self.maya = ModuleType("maya")
        self.maya.cmds = Mock()
        self.maya.utils = Mock()
        self.maya.cmds.about.return_value = False
        self.loaded = []
        self.maya.cmds.pluginInfo.side_effect = lambda **kwargs: self.loaded
        self.maya.cmds.loadPlugin.side_effect = self.loaded.append

    def load(self):
        """実際の起動スクリプトを代替Mayaで実行する。"""
        with patch.dict(sys.modules, {"maya": self.maya}):
            return runpy.run_path(str(ROOT / "scripts/userSetup.py"))

    def test_deferred_gui_load(self):
        """import中にロードせず、遅延コールバックからロードする。"""
        self.load()
        self.maya.cmds.loadPlugin.assert_not_called()
        callback = self.maya.utils.executeDeferred.call_args[0][0]
        callback()
        self.maya.cmds.loadPlugin.assert_called_once_with("quickPathExplorer")

    def test_batch_skipped(self):
        """バッチ起動にはGUI用ロードを予約しない。"""
        self.maya.cmds.about.return_value = True
        self.load()
        self.maya.utils.executeDeferred.assert_not_called()
        self.maya.cmds.loadPlugin.assert_not_called()

    def test_already_loaded(self):
        """標準autoload済みのプラグインを再ロードしない。"""
        self.loaded.append("quickPathExplorer")
        self.load()["_load_qpe"]()
        self.maya.cmds.loadPlugin.assert_not_called()

    def test_repeated_startup(self):
        """複数回予約されても最初の1回だけロードする。"""
        first = self.load()["_load_qpe"]
        second = self.load()["_load_qpe"]
        first()
        second()
        self.maya.cmds.loadPlugin.assert_called_once()

    def test_failure_warns(self):
        """Security拒否等を隠さず、起動全体へ例外を伝播しない。"""
        self.maya.cmds.loadPlugin.side_effect = RuntimeError("load refused")
        self.load()["_load_qpe"]()
        self.maya.cmds.warning.assert_called_once_with("QuickPathExplorer startup: load refused")

    def test_empty_plugin_list(self):
        """Mayaが空リストの代わりにNoneを返してもロードできる。"""
        self.maya.cmds.pluginInfo.side_effect = None
        self.maya.cmds.pluginInfo.return_value = None
        self.load()["_load_qpe"]()
        self.maya.cmds.loadPlugin.assert_called_once()

    def test_module_year_paths(self):
        """単独配布とワークスペースの全対応年に起動パスを登録する。"""
        paths = [ROOT / "QuickPathExplorer.mod"]
        workspace = ROOT.parents[2] / "maya/modules/QuickPathExplorer.mod"
        if workspace.is_file():
            paths.append(workspace)
        for path in paths:
            blocks = path.read_text(encoding="utf-8").strip().split("\n\n")
            self.assertEqual(len(blocks), 6)
            for year, block in zip(range(2022, 2028), blocks):
                self.assertIn("MAYAVERSION:{} ".format(year), block)
                self.assertIn("MAYA_PLUG_IN_PATH +:= release/plug-ins/windows/{}".format(year), block)
                self.assertIn("PYTHONPATH +:= scripts", block)


if __name__ == "__main__":
    unittest.main()
