"""未保存タブの復元先(tabs.json)の決定を検証する。

復元先はmayaCodeEditor.mll(C++の ``mayaCodeEditor -sessionPath``)が決めるため、mayapyでプラグインをロードして確かめる。
Mayaの設定フォルダーは一時フォルダーへ隔離する。
"""
import os
from pathlib import Path
import tempfile
import unittest

# Maya初期化前に設定フォルダーを隔離する。ユーザーの設定・復元ファイルには触れない。
APP_DIR = tempfile.mkdtemp(prefix='mce_session_path_')
os.environ['MAYA_APP_DIR'] = APP_DIR
os.environ.pop('MCE_SESSION_FILE', None)
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
# 旧名(hedit、0.6.x まで)の保存先。初めてロードしたときに新しい保存先へ写すことを確かめる。
LEGACY = Path(cmds.internalVar(userPrefDir=True)) / 'hedit'
(LEGACY / 'tabs').mkdir(parents=True)
(LEGACY / 'tabs.json').write_text('{"tabs": []}', encoding='utf-8')
(LEGACY / 'tabs' / 'legacy.txt').write_text('print("legacy")', encoding='utf-8')
cmds.loadPlugin('mayaCodeEditor')


class SessionPathTests(unittest.TestCase):
    """``mayaCodeEditor -sessionPath`` が返す tabs.json の場所の検証。"""
    def test_default_location(self):
        """Mayaのユーザー設定フォルダー(バージョン別)の下のMayaCodeEditor/tabs.json。"""
        base = Path(cmds.internalVar(userPrefDir=True))
        self.assertEqual(Path(cmds.mayaCodeEditor(sessionPath=True)), base / 'MayaCodeEditor' / 'tabs.json')

    def test_legacy_folder_is_copied(self):
        """旧名の保存先(hedit)の中身を、新しい保存先へ写す。旧名の保存先は残す。"""
        folder = Path(cmds.mayaCodeEditor(sessionPath=True)).parent
        self.assertEqual((folder / 'tabs.json').read_text(encoding='utf-8'), '{"tabs": []}')
        self.assertEqual((folder / 'tabs' / 'legacy.txt').read_text(encoding='utf-8'), 'print("legacy")')
        self.assertTrue((LEGACY / 'tabs.json').exists())

    def test_environment_override(self):
        """隔離テスト用の環境変数があればその場所を使う。"""
        custom = str(Path(APP_DIR) / 'custom' / 'tabs.json')
        os.environ['MCE_SESSION_FILE'] = custom
        try:
            self.assertEqual(cmds.mayaCodeEditor(sessionPath=True), custom)
        finally:
            del os.environ['MCE_SESSION_FILE']


if __name__ == '__main__':
    unittest.main()
