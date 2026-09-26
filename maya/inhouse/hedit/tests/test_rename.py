"""名称変更で未保存タブや設定を失わないことを検証する。"""
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from hedit import bridge

class RenameTests(unittest.TestCase):
    def test_copy_legacy_without_overwriting_current(self):
        """旧ファイルを残し、新しい設定がある場合はそちらを優先する。"""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            legacy = base / 'heditor'; legacy.mkdir()
            for name in ('tabs.json', 'ui.json', 'preferences.ini'):
                (legacy / name).write_text('unsaved data', encoding='utf-8')
            maya = types.ModuleType('maya')
            maya.cmds = types.SimpleNamespace(internalVar=lambda **kwargs: directory)
            with mock.patch.dict(sys.modules, {'maya': maya}), mock.patch.dict(os.environ, {}, clear=True):
                target = Path(bridge.session_path())
                self.assertEqual(target, base / 'hedit' / 'tabs.json')
                for name in ('tabs.json', 'ui.json', 'preferences.ini'):
                    self.assertEqual((target.parent / name).read_text(), 'unsaved data')
                    self.assertTrue((legacy / name).exists())
                target.write_text('new data')
                bridge.session_path()
                self.assertEqual(target.read_text(), 'new data')

if __name__ == '__main__':
    unittest.main()
