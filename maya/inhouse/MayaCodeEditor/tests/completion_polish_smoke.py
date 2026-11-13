"""専用Mayaで補完履歴・IME境界・連続入力・多数タブを検証する。OS入力とは区別する。"""
import json
from pathlib import Path
import sys
import time
import traceback


def main(output_dir, finished):
    """Qtの入力イベントと本文を照合する。

    Args:
        output_dir (Path): 専用の証拠保存先。
        finished (callable): 終了通知。
    """
    from maya import cmds
    try:
        from PySide6 import QtCore, QtGui, QtWidgets, QtTest
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets, QtTest
    sys.path.insert(0, str(Path(__file__).parent))
    import gui_host
    out = Path(output_dir)
    result = {'status': 'error', 'checks': [], 'input_kind': 'Qt QTest and QInputMethodEvent, not OS IME'}

    def wait(ms):
        """ホストのイベントループへ制御を返す。"""
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, loop.quit)
        (loop.exec if hasattr(loop, 'exec') else loop.exec_)()

    def check(name, condition, detail=None):
        """失敗も含めて記録する。"""
        result['checks'].append({'name': name, 'passed': bool(condition), 'detail': detail})
        if not condition:
            raise AssertionError((name, detail))

    try:
        cmds.loadPlugin('mayaCodeEditor', quiet=True)
        cmds.mayaCodeEditor(show=True)
        window = gui_host.editor()
        tabs = window.findChild(QtWidgets.QTabWidget)
        code = tabs.currentWidget()
        window.resize(1100, 750)
        wait(5000)
        QtWidgets.QApplication.setActiveWindow(window.window())
        code.setFocus()

        def candidates(source, target):
            """候補が到着するまで待つが、候補の選択は変更しない。"""
            popup = code.findChild(QtWidgets.QCompleter)
            popup.popup().hide()
            code.setPlainText(source)
            code.moveCursor(QtGui.QTextCursor.End)
            QtWidgets.QApplication.setActiveWindow(window.window())
            code.setFocus()
            wait(300)
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier)
            until = time.monotonic() + 8
            while time.monotonic() < until:
                wait(100)
                model = popup.completionModel()
                names = [model.index(i, 0).data() for i in range(model.rowCount())]
                if popup.popup().isVisible() and target in names:
                    return popup, names
            window.grab().save(str(out / 'candidate-failure.png'))
            raise AssertionError(('candidate timeout', target, names, code.hasFocus(), code.property('language'), status.text(), code.toPlainText()))

        status = window.findChild(QtWidgets.QLabel, 'completionStatus')
        check('built_in_completion_ready', status is not None and status.text() == 'Completion: ready (in Maya)', status.text() if status else None)
        check('no_language_server_process', not window.findChildren(QtCore.QProcess))
        action_class = getattr(QtGui, 'QAction', None) or QtWidgets.QAction
        labels = [action.text() for action in window.findChildren(action_class)]
        check('no_server_only_menu', not any(label in labels for label in ('Find references', 'Rename symbol…', 'Code actions…', 'Suggest auto imports', 'Type-aware colors', 'Type and argument hints')))
        for source in ("x = next(iter(['hello']))\nx.upp", "from typing import Literal\nx: Literal['hello']\nx.upp"):
            popup, _ = candidates(source, 'upper')
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Escape)
        timings = []
        source = '# local performance\n' + 'value = 1\n' * 5000 + "name = 'hello'\nname.upp"
        for _ in range(10):
            started = time.perf_counter()
            response = json.loads(cmds.mayaCodeEditorTest(complete=source))
            timings.append((time.perf_counter() - started) * 1000)
        check('large_document_local_candidates', 'upper' in [item['name'] for item in response['items']])
        result['completion_5000_lines_ms'] = timings

        popup, names = candidates("value = 'x'\nvalue.st", 'strip')
        popup.popup().setCurrentIndex(popup.completionModel().index(names.index('strip'), 0))
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
        check('accept_without_newline', code.toPlainText() == "value = 'x'\nvalue.strip")
        # 別タブでも同じprefixの確定履歴を使う。
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_N, QtCore.Qt.ControlModifier)
        wait(100)
        code = tabs.currentWidget()
        popup, names = candidates("value = 'y'\nvalue.st", 'strip')
        check('history_across_tabs', popup.popup().currentIndex().data() == 'strip', popup.popup().currentIndex().data())
        window.grab().save(str(out / 'history.png'))
        popup.popup().hide()
        code.setPlainText('name = ')
        code.moveCursor(QtGui.QTextCursor.End)
        preedit = QtGui.QInputMethodEvent('にほん', [])
        QtWidgets.QApplication.sendEvent(code, preedit)
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier)
        wait(500)
        check('ime_preedit_no_popup', not popup.popup().isVisible())
        check('ime_preedit_not_committed', code.toPlainText() == 'name = ', code.toPlainText())
        commit = QtGui.QInputMethodEvent()
        commit.setCommitString('日本語')
        QtWidgets.QApplication.sendEvent(code, commit)
        check('ime_commit_preserved', code.toPlainText() == 'name = 日本語', code.toPlainText())
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)
        check('ime_single_undo', code.toPlainText() == 'name = ', code.toPlainText())
        for index in range(10):
            popup.popup().hide()
            code.setPlainText("value = 'hello'\nvalue.")
            code.moveCursor(QtGui.QTextCursor.End)
            code.setFocus()
            QtTest.QTest.keyClicks(code, 'upper', QtCore.Qt.NoModifier, 0)
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Escape)
            wait(150)
            check('rapid_input_%02d' % index, code.toPlainText() == "value = 'hello'\nvalue.upper" and not popup.popup().isVisible(),
                  {'text': code.toPlainText(), 'popup': popup.popup().isVisible()})
        # 30タブを作成して本文を保持したまま移動する。専用prefsにだけ保存される。
        expected = {}
        for index in range(30):
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_N, QtCore.Qt.ControlModifier)
            wait(15)
            code = tabs.currentWidget()
            source = '# dedicated tab %d\n' % index + 'value = 1\n' * 2000
            code.setPlainText(source)
            expected[tabs.currentIndex()] = source
        started = time.monotonic()
        for index, source in expected.items():
            tabs.setCurrentIndex(index)
            wait(15)
            check('tab_preservation_%02d' % index, tabs.currentWidget().toPlainText() == source)
        result['tab_switch_seconds'] = time.monotonic() - started
        code = tabs.currentWidget()
        popup, names = candidates('# large script\n' + 'value = 1\n' * 5000 + "name = 'hello'\nname.upp", 'upper')
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Tab)
        check('large_document_accept', code.toPlainText().endswith('name.upper'))
        window.grab().save(str(out / 'large-document.png'))
        result['status'] = 'passed'
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    finished(result)
