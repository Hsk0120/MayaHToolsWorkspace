"""名称変更で未保存タブや設定を失わないことを検証する。

タブ復元先の決定と旧保存先からのコピーはhedit.mll(C++の ``hedit -sessionPath``)が行うため、
mayapyでプラグインをロードして確かめる。Mayaの設定フォルダーは一時フォルダーへ隔離する。
"""
import os
from pathlib import Path
import tempfile
import unittest

# Maya初期化前に設定フォルダーを隔離する。ユーザーの設定・復元ファイルには触れない。
APP_DIR = tempfile.mkdtemp(prefix='hedit_rename_')
os.environ['MAYA_APP_DIR'] = APP_DIR
os.environ.pop('HEDIT_SESSION_FILE', None)
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
cmds.loadPlugin('hedit')

NAMES = ('tabs.json', 'ui.json', 'preferences.ini')


class RenameTests(unittest.TestCase):
    def test_copy_legacy_without_overwriting_current(self):
        """旧ファイルを残し、新しい設定がある場合はそちらを優先する。"""
        base = Path(cmds.internalVar(userPrefDir=True))
        legacy = base / 'heditor'
        legacy.mkdir(parents=True, exist_ok=True)
        for name in NAMES:
            (legacy / name).write_text('unsaved data', encoding='utf-8')
        target = Path(cmds.hedit(sessionPath=True))
        self.assertEqual(target, base / 'hedit' / 'tabs.json')
        for name in NAMES:
            self.assertEqual((target.parent / name).read_text(encoding='utf-8'), 'unsaved data')
            self.assertTrue((legacy / name).exists())
        target.write_text('new data', encoding='utf-8')
        cmds.hedit(sessionPath=True)
        self.assertEqual(target.read_text(encoding='utf-8'), 'new data')

    def test_environment_override(self):
        """隔離テスト用の環境変数があればその場所を使う。"""
        custom = str(Path(APP_DIR) / 'custom' / 'tabs.json')
        os.environ['HEDIT_SESSION_FILE'] = custom
        try:
            self.assertEqual(cmds.hedit(sessionPath=True), custom)
        finally:
            del os.environ['HEDIT_SESSION_FILE']


if __name__ == '__main__':
    unittest.main()
