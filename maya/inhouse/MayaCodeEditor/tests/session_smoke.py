"""別Mayaプロセス間で未保存タブが復元されることを確認する。"""
import json
import os
from pathlib import Path
import traceback
import zlib


def main(output_dir, finished):
    """GUIランナー(``maya/inhouse/mlib/__tests__/runGui.py``)が、専用の Maya GUI の中で呼ぶ入口。

    Args:
        output_dir (str): 結果の ``result.json`` と画像の出力先。
        finished (callable): 終了時に結果の辞書を渡して呼ぶ関数(Maya の終了はランナーが行う)。
    """
    from maya import cmds
    # maya_code_editor.*はmayaCodeEditor.mllに同梱されており、プラグインのロードでimportできるようになる。
    cmds.loadPlugin('mayaCodeEditor', quiet=True)
    import maya_code_editor
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
    result = {'status': 'error', 'checks': []}
    path = Path(os.environ['MCE_SESSION_FILE'])
    original = path.with_name('original.py')
    text = '# 未保存の日本語\nprint("recovered")\n'
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import gui_host
        maya_code_editor.show()
        window = gui_host.editor()
        tabs = window.findChild(QtWidgets.QTabWidget)
        if os.environ['MCE_SESSION_STAGE'] == 'write':
            original.write_text('original = True\n', encoding='utf-8')
            code = tabs.currentWidget()
            code.setPlainText(text)
            code.setProperty('path', str(original))
            code.document().setModified(True)
            cursor = code.textCursor()
            cursor.setPosition(2)
            cursor.setPosition(7, QtGui.QTextCursor.KeepAnchor)
            code.setTextCursor(cursor)
            next(a for a in window.findChildren(QtWidgets.QAction if hasattr(QtWidgets, 'QAction') else QtGui.QAction) if a.text() == 'New Python tab').trigger()
            tabs.currentWidget().setPlainText('unsaved_second = 42')
            tabs.currentWidget().document().setModified(True)
            tabs.setCurrentIndex(0)
        else:
            assert tabs.count() == 2
            assert tabs.currentIndex() == 0
            code = tabs.widget(0)
            assert code.toPlainText() == text
            assert code.property('path') == str(original)
            assert code.document().isModified()
            assert (code.textCursor().anchor(), code.textCursor().position()) == (2, 7)
            # 選んでいないタブは、初めて選ぶまで本文を文書へ入れない。見出しの未保存の印は読み込む前から出る。
            second = tabs.widget(1)
            assert second.property('textPending') is True
            assert second.document().isModified() and tabs.tabText(1).endswith('●'), tabs.tabText(1)
            tabs.setCurrentIndex(1)
            assert not second.property('textPending')
            assert second.toPlainText() == 'unsaved_second = 42'
            assert second.document().isModified()
            tabs.setCurrentIndex(0)
            result['checks'].append('restored_tabs_text_paths_selection_active_modified')
            result['checks'].append('inactive_tab_loaded_on_first_selection')

        # 本文は同期保存される。カーソルとタブ順の遅延保存はイベントループで待つ。
        # 待機は壁時計ではなくイベントループが回った回数(200ms×25回)で数える。Maya 2024では
        # 起動直後にArnold(mtoa)の遅延登録がGUIスレッドを約5秒止めるため、壁時計だと停止中に
        # 期限が切れ、停止明けに自動保存のタイマーより先にこの確認が走って誤って失敗する。
        remaining = [25]

        def saved():
            # 世代の確定後にだけ親世代から進む。最新の先端を調べる。
            try:
                recovery = Path(str(path) + '.recovery')
                entries = {p.stem: json.loads(p.read_text(encoding='utf-8'))
                           for p in (recovery / 'snapshots').glob('*.json')}
                parents = {parent for entry in entries.values() for parent in entry['parents']}
                heads = [entry for key, entry in entries.items() if key not in parents]
                if len(heads) != 1:
                    return None
                data = heads[0]
                saved_tabs = data.get('tabs', [])
                if len(saved_tabs) != 2 or data['active'] != 0:
                    return None
                first = saved_tabs[0]
                if (first['anchor'], first['position']) != (2, 7):
                    return None
                compressed = (recovery / 'bodies' / (data['bodies'][first['id']] + '.qz')).read_bytes()
                body = zlib.decompress(compressed[4:]).decode('utf-8')
            except (OSError, ValueError, KeyError, zlib.error):
                return None
            return data if body == text else None

        def verify():
            if saved() is None and remaining[0] > 0:
                remaining[0] -= 1
                QtCore.QTimer.singleShot(200, verify)
                return
            try:
                data = saved()
                assert data is not None, 'Tabs were not autosaved: {}'.format(path)
                assert original.read_text(encoding='utf-8') == 'original = True\n'
                result['checks'].append('autosaved_without_overwriting_original')
                # 未保存のまま解除しても保存ダイアログで停止しない。
                cmds.unloadPlugin('mayaCodeEditor')
                result['checks'].append('unload_preserved_unsaved_tabs')
                result['status'] = 'passed'
            except Exception:
                result['error'] = traceback.format_exc()
            Path(output_dir, 'result.json').write_text(json.dumps(result), encoding='utf-8')
            finished(result)
        QtCore.QTimer.singleShot(200, verify)
    except Exception:
        result['error'] = traceback.format_exc()
        Path(output_dir, 'result.json').write_text(json.dumps(result), encoding='utf-8')
        finished(result)
