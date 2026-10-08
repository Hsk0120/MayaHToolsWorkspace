"""補完確定後のEnterと、表示前のMaya履歴を実キーで検証する。"""
import json
from pathlib import Path
import sys
import time
import traceback


def main(output_dir, finished):
    """GUIランナー(``tools/run_hlib_gui_versions.py``)が、専用の Maya GUI の中で呼ぶ入口。

    Args:
        output_dir (str): 結果の ``result.json`` と画像の出力先。
        finished (callable): 終了時に結果の辞書を渡して呼ぶ関数(Maya の終了はランナーが行う)。
    """
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
        # 編集画面を隠している間の出力は出力欄へ描かずに貯め、表示したときにまとめて出す
        # (出力が無い間・隠している間は、出力欄の処理が動かない)。
        window.hide()
        wait(50)
        print('hidden_output_probe')
        wait(200)
        assert 'hidden_output_probe' not in output.toPlainText(), 'Output was drawn while hidden'
        window.show()
        wait(200)
        output = hedit_host.editor().findChild(QtWidgets.QPlainTextEdit, 'output')
        assert output.toPlainText().count('hidden_output_probe') == 1, output.toPlainText()[-400:]
        result['checks'].append('hidden_output_shown_on_show')
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

        code.setPlainText('import hlib'); code.moveCursor(QtGui.QTextCursor.End)
        # テスト用のMayaはすぐには前面に出られないことがある(Windowsの前面化の制限)。フォーカスが来るまで待つ。
        for attempt in range(100):
            window.activateWindow(); window.raise_(); code.setFocus()
            wait(100)
            if code.hasFocus():
                break
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier)
        wait(250)
        # 最初のCtrl+Spaceだけで、未読込のパッケージ(hlib)が候補に入る。sys.pathの走査は
        # C++のスレッドで編集画面の作成時に始めている(ポップアップの表示有無とは別に確かめる)。
        assert 'hlib' in names(), (names(), 'code_has_focus=%s' % code.hasFocus())
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
        # 一覧が開いたまま、Enterがコード欄へ直接届いた場合(Mayaのドックの中で起きる)も、ここで確定して
        # 親(Mayaのウィンドウ)へ回さない。アウトライナでノードを選択していても、フォーカスはコード欄に残る。
        probe = cmds.createNode('transform', name='hedit_focus_probe')
        outliner_window = cmds.window(title='hedit outliner probe')
        cmds.frameLayout(labelVisible=False)
        cmds.outlinerEditor()
        cmds.showWindow(outliner_window)
        cmds.select(probe)
        wait(200)
        code.setPlainText('import hlib\nhlib.'); code.moveCursor(QtGui.QTextCursor.End)
        assert show_popup(), 'No completion popup for hlib.'
        first = completer.popup().currentIndex().data()
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
        wait(250)
        assert code.toPlainText() == 'import hlib\nhlib.' + first, repr(code.toPlainText())
        assert code.hasFocus(), 'Focus left the code editor after accepting a completion'
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
        wait(200)
        assert code.toPlainText() == 'import hlib\nhlib.' + first + '\n', repr(code.toPlainText())
        cmds.deleteUI(outliner_window)
        cmds.delete(probe)
        result['checks'].append('enter_on_code_accepts_without_leaving_editor')
        # 確定後も次の入力と手動補完は使用できる。
        code.setPlainText('import maya.cmds as cmds\ncmds.')
        code.moveCursor(QtGui.QTextCursor.End)
        assert show_popup(), 'No completion popup after accepting a candidate'
        result['checks'].append('subsequent_completion_still_available')
        # 入力を続けても一覧は閉じず(ちらつかず)、入力した名前で絞り込まれる。名前の外(``(``)へ出たら閉じる。

        class HideCounter(QtCore.QObject):
            """一覧が隠れた回数を数えるイベントフィルター。"""
            count = 0

            def eventFilter(self, watched, event):
                if event.type() == QtCore.QEvent.Hide:
                    HideCounter.count += 1
                return False

        counter = HideCounter()
        completer.popup().installEventFilter(counter)
        for character in 'ls':
            QtTest.QTest.keyClick(code, character)
            wait(60)
        wait(500)  # 名前を伸ばした後の問い合わせ直し(0.25秒後)も済ませる。
        completer.popup().removeEventFilter(counter)
        assert completer.popup().isVisible() and HideCounter.count == 0, (HideCounter.count, code.toPlainText())
        assert 'ls' in names() and all(name.startswith('ls') for name in names()), names()
        QtTest.QTest.keyClick(code, '(')
        wait(100)
        assert not completer.popup().isVisible(), 'Popup stayed open after leaving the name'
        result['checks'].append('popup_stays_open_and_filters_while_typing')
        completer.popup().hide()
        window.grab().save(str(directory / 'completion-output.png'))
        code.document().setModified(False)
        window.close(); cmds.unloadPlugin('hedit')
        result['status'] = 'passed'
    except Exception:
        result['error'] = traceback.format_exc()
    (directory / 'result.json').write_text(json.dumps(result), encoding='utf-8')
    finished(result)
