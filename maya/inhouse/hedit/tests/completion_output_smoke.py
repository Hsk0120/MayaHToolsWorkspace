"""補完確定後のEnterと、表示前のMaya履歴を実キーで検証する。"""
import json
from pathlib import Path
import sys
import time
import traceback


def main(output_dir, finished):
    from maya import cmds, OpenMaya, mel
    try:
        from PySide6 import QtCore, QtGui, QtWidgets, QtTest
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets, QtTest
    def wait(ms):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, loop.quit)
        (loop.exec if hasattr(loop, 'exec') else loop.exec_)()
    result = {'status': 'error', 'checks': []}
    directory = Path(output_dir)
    try:
        OpenMaya.MGlobal.displayInfo('history_before_hedit_probe')
        # hedit.*はhedit.mllに同梱されており、プラグインのロードでimportできるようになる。
        cmds.loadPlugin('hedit', quiet=True)
        import hedit
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import hedit_host
        hedit.show()
        window = hedit_host.editor()
        output = window.findChild(QtWidgets.QPlainTextEdit, 'output')
        code = window.findChild(QtWidgets.QPlainTextEdit, 'codeEditor')
        wait(100)
        assert output.toPlainText().count('history_before_hedit_probe') == 1
        OpenMaya.MGlobal.executeCommand('about -version;', True, False)
        wait(100)
        assert '// Result: {}'.format(cmds.about(version=True)) in output.toPlainText()
        result['checks'].append('history_before_open_once_and_result_format')
        # 実際のhlibソースを候補に含める。補完によるimportはしない。
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        completer = code.findChild(QtWidgets.QCompleter)

        def names():
            model = completer.completionModel()
            return [model.index(row, 0).data() for row in range(model.rowCount())]

        def show_popup(timeout=10.0):
            # テスト用のMayaは前面にいないことがあり、Windowsは前面でないアプリのポップアップを
            # すぐ閉じる。また前面化は非同期で、直後のキーはフォーカスが無く補完されない。
            # 前面化を待ってからCtrl+Spaceを送り、表示されるまでやり直す(実際の操作では起きない)。
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                window.activateWindow(); code.setFocus()
                wait(100)
                if not code.hasFocus():
                    continue
                QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier)
                wait(200)
                if completer.popup().isVisible() and completer.completionCount():
                    return True
            return False

        window.activateWindow(); code.setFocus()
        code.setPlainText('import hlib'); code.moveCursor(QtGui.QTextCursor.End)
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier)
        wait(250)
        # 最初のCtrl+Spaceだけで、未読込のパッケージ(hlib)が候補に入る。sys.pathの走査は
        # C++のスレッドで編集画面の作成時に始めている(ポップアップの表示有無とは別に確かめる)。
        assert 'hlib' in names(), names()
        result['checks'].append('first_ctrl_space_lists_unloaded_package')
        assert show_popup(), 'No completion popup'
        model = completer.completionModel()
        row = next(i for i in range(model.rowCount()) if model.index(i, 0).data() == 'hlib')
        completer.popup().setCurrentIndex(model.index(row, 0))
        QtTest.QTest.keyClick(completer.popup(), QtCore.Qt.Key_Return)
        wait(250)
        assert code.toPlainText() == 'import hlib'
        assert not completer.popup().isVisible(), 'Popup reopened after acceptance'
        code.setFocus(); QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
        wait(200)
        assert code.toPlainText() == 'import hlib\n', repr(code.toPlainText())
        assert not completer.popup().isVisible()
        result['checks'].append('accept_hlib_then_enter_newline')
        # 確定後も次の入力と手動補完は使用できる。
        code.setPlainText('import maya.cmds as cmds\ncmds.')
        code.moveCursor(QtGui.QTextCursor.End)
        assert show_popup(), 'No completion popup after accepting a candidate'
        completer.popup().hide()
        result['checks'].append('subsequent_completion_still_available')
        window.grab().save(str(directory / 'completion-output.png'))
        code.document().setModified(False)
        window.close(); cmds.unloadPlugin('hedit')
        result['status'] = 'passed'
    except Exception:
        result['error'] = traceback.format_exc()
    (directory / 'result.json').write_text(json.dumps(result), encoding='utf-8')
    finished(result)
