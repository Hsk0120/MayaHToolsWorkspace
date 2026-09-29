"""未保存タブの復元先(tabs.json)の決定を検証する。

復元先はhedit.mll(C++の ``hedit -sessionPath``)が決めるため、mayapyでプラグインをロードして確かめる。
Mayaの設定フォルダーは一時フォルダーへ隔離する。
"""
import os
from pathlib import Path
import tempfile
import unittest

# Maya初期化前に設定フォルダーを隔離する。ユーザーの設定・復元ファイルには触れない。
APP_DIR = tempfile.mkdtemp(prefix='hedit_session_path_')
os.environ['MAYA_APP_DIR'] = APP_DIR
os.environ.pop('HEDIT_SESSION_FILE', None)
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
cmds.loadPlugin('hedit')


class SessionPathTests(unittest.TestCase):
    """``hedit -sessionPath`` が返す tabs.json の場所の検証。"""
    def test_default_location(self):
        """Mayaのユーザー設定フォルダー(バージョン別)の下のhedit/tabs.json。"""
        base = Path(cmds.internalVar(userPrefDir=True))
        self.assertEqual(Path(cmds.hedit(sessionPath=True)), base / 'hedit' / 'tabs.json')

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
