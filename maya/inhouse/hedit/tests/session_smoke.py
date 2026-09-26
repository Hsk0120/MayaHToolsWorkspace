"""別Mayaプロセス間で未保存タブが復元されることを確認する。"""
import json
import os
from pathlib import Path
import traceback


def main(output_dir, finished):
    from maya import cmds
    import hedit
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
    result = {'status': 'error', 'checks': []}
    path = Path(os.environ['HEDIT_SESSION_FILE'])
    original = path.with_name('original.py')
    text = '# 未保存の日本語\nprint("recovered")\n'
    try:
        host = hedit.show()
        window = host.editor
        tabs = window.findChild(QtWidgets.QTabWidget)
        if os.environ['HEDIT_SESSION_STAGE'] == 'write':
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
            assert tabs.widget(1).toPlainText() == 'unsaved_second = 42'
            assert tabs.widget(1).document().isModified()
            result['checks'].append('restored_tabs_text_paths_selection_active_modified')

        def verify():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                assert len(data['tabs']) == 2 and data['tabs'][0]['text'] == text
                assert original.read_text(encoding='utf-8') == 'original = True\n'
                result['checks'].append('autosaved_without_overwriting_original')
                # 未保存のまま解除しても保存ダイアログで停止しない。
                cmds.unloadPlugin('hedit')
                result['checks'].append('unload_preserved_unsaved_tabs')
                result['status'] = 'passed'
            except Exception:
                result['error'] = traceback.format_exc()
            Path(output_dir, 'result.json').write_text(json.dumps(result), encoding='utf-8')
            finished(result)
        QtCore.QTimer.singleShot(1600, verify)
    except Exception:
        result['error'] = traceback.format_exc()
        Path(output_dir, 'result.json').write_text(json.dumps(result), encoding='utf-8')
        finished(result)
