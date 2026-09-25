"""run_hlib_gui_versionsの専用Mayaに渡すGUIスイート。"""
import json
from pathlib import Path
import traceback
import time


def main(output_dir, finished):
    from maya import cmds, mel
    try:
        from PySide6 import QtCore, QtGui, QtWidgets, QtTest
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets, QtTest
    directory = Path(output_dir)
    result = {'status': 'error', 'checks': []}
    try:
        import heditor
        heditor.show()
        window = next(w for w in QtWidgets.QApplication.topLevelWidgets() if w.objectName() == 'HEditor')
        assert window.isVisible()
        result['checks'].append('window_visible')
        code = window.findChild(QtWidgets.QPlainTextEdit, 'codeEditor')
        code.setPlainText('import maya.cmds as cmds\nprint(cmds.about(version=True))')
        # Qt6でQActionはQtGuiへ移動しているため、ツールバー上から取得する。
        toolbar = window.findChild(QtWidgets.QToolBar)
        next(action for action in toolbar.actions() if action.text() == 'Run all').trigger()
        assert str(cmds.about(version=True)) in window.findChild(QtWidgets.QPlainTextEdit, 'output').toPlainText()
        result['checks'].append('execute_in_maya')
        # 実際の標準Script Editorの入力欄と出力欄で双方向を確認する。
        mel.eval('ScriptEditor;')
        reporters = cmds.lsUI(type='cmdScrollFieldReporter') or []
        executers = [name for name in (cmds.lsUI(type='cmdScrollFieldExecuter') or [])
                     if cmds.cmdScrollFieldExecuter(name, query=True, sourceType=True) == 'python']
        assert reporters and executers, 'Native Script Editor controls missing'
        native = executers[0]
        assert cmds.cmdScrollFieldExecuter(native, query=True, sourceType=True) == 'python'
        output = window.findChild(QtWidgets.QPlainTextEdit, 'output')
        run_all = next(action for action in toolbar.actions() if action.text() == 'Run all')
        code.setPlainText('heditor_shared_value = 2718\nprint("HEditor" + "_outgoing_日本語")')
        run_all.trigger()
        QtTest.QTest.qWait(80)
        native_text = '\n'.join(cmds.cmdScrollFieldReporter(name, query=True, text=True) for name in reporters)
        assert 'HEditor_outgoing_日本語' in native_text, repr(native_text)
        assert output.toPlainText().splitlines().count('HEditor_outgoing_日本語') == 1, output.toPlainText()
        result['checks'].append('heditor_to_native_once')
        cmds.cmdScrollFieldExecuter(native, edit=True, text='print("Native" + "_incoming", heditor_shared_value)')
        assert 'Native' in cmds.cmdScrollFieldExecuter(native, query=True, text=True)
        def after_native():
            nonlocal code
            try:
                QtTest.QTest.qWait(80)
                assert output.toPlainText().splitlines().count('Native_incoming 2718') == 1, (output.toPlainText(), [cmds.cmdScrollFieldReporter(n, query=True, text=True) for n in reporters])
                result['checks'].append('native_to_heditor_once_shared_namespace')
                cmds.warning('HEditor_native_warning')
                code.setPlainText('raise ValueError("HEditor_shared_error")')
                run_all.trigger()
                QtTest.QTest.qWait(80)
                assert 'HEditor_native_warning' in output.toPlainText()
                assert 'ValueError' in output.toPlainText() and 'HEditor_shared_error' in output.toPlainText()
                assert any('HEditor_shared_error' in cmds.cmdScrollFieldReporter(name, query=True, text=True) for name in reporters)
                result['checks'].append('shared_warning_and_error')
                assert window.grab().save(str(directory / 'shared-output.png'))
                # 後続の選択実行テストは履歴から切り離す。
                output.clear()
                code.document().setModified(False)

                # 新しいタブで実際にキー入力し、Ctrl+Spaceなしの自動補完を確認する。
                next(a for a in window.findChildren(QtGui.QAction if hasattr(QtGui, 'QAction') else QtWidgets.QAction)
                     if a.text() == 'New Python tab').trigger()
                code = window.findChild(QtWidgets.QTabWidget).currentWidget()
                code.setPlainText('import maya.cmds as cmds\n')
                cursor = code.textCursor()
                cursor.movePosition(QtGui.QTextCursor.End)
                code.setTextCursor(cursor)
                window.activateWindow()
                code.setFocus()
                QtTest.QTest.keyClicks(code, 'cmds.')
                deadline = time.monotonic() + 20

                def finish():
                    try:
                        code.document().setModified(False)
                        assert window.close()
                        cmds.unloadPlugin('HEditor')
                        result['checks'].append('close_and_unload')
                    except Exception:
                        result['status'] = 'error'
                        result['error'] = traceback.format_exc()
                    (directory / 'result.json').write_text(json.dumps(result), encoding='utf-8')
                    finished(result)

                def complete():
                    try:
                        completer = code.findChild(QtWidgets.QCompleter)
                        if completer.popup().isVisible() and completer.completionCount():
                            model = completer.completionModel()
                            rows = [row for row in range(model.rowCount()) if model.index(row, 0).data() == 'createNode']
                            assert model.rowCount() > 0, 'No dot completion candidates'
                            result['checks'].append('completion_visible')
                            assert window.grab().save(str(directory / 'heditor-gui.png'))
                            assert completer.popup().grab().save(str(directory / 'completion.png'))
                            chosen = model.index(0, 0).data()
                            completer.popup().setCurrentIndex(model.index(0, 0))
                            event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Return, QtCore.Qt.NoModifier)
                            QtWidgets.QApplication.sendEvent(completer.popup(), event)
                            assert code.toPlainText().endswith('cmds.' + chosen), code.toPlainText()
                            result['checks'].append('completion_enter_insertion')
                            # 選択実行では未選択の例外を実行しないことも確認。
                            code.setPlainText('print("selection_passed")\nraise RuntimeError("must not run")')
                            cursor = code.textCursor()
                            cursor.movePosition(QtGui.QTextCursor.Start)
                            cursor.movePosition(QtGui.QTextCursor.EndOfBlock, QtGui.QTextCursor.KeepAnchor)
                            code.setTextCursor(cursor)
                            next(a for a in toolbar.actions() if 'Run selection' in a.text()).trigger()
                            text = window.findChild(QtWidgets.QPlainTextEdit, 'output').toPlainText()
                            assert 'selection_passed' in text and 'RuntimeError' not in text, text
                            result['checks'].append('selection_execution')
                            result['status'] = 'passed'
                            finish()
                            return
                        if time.monotonic() >= deadline:
                            raise RuntimeError('GUI completion did not become visible within 20 seconds')
                        QtCore.QTimer.singleShot(200, complete)
                    except Exception:
                        result['error'] = traceback.format_exc()
                        finish()
                QtCore.QTimer.singleShot(500, complete)
            except Exception:
                result['error'] = traceback.format_exc()
                (directory / 'result.json').write_text(json.dumps(result), encoding='utf-8')
                finished(result)
        def run_native():
            cmds.setFocus(native)
            mel.eval('evalDeferred "cmdScrollFieldExecuter -e -execute ' + native + '";')
            cmds.evalDeferred(after_native, lowestPriority=True)
        QtCore.QTimer.singleShot(500, run_native)
    except Exception:
        result['error'] = traceback.format_exc()
        (directory / 'result.json').write_text(json.dumps(result), encoding='utf-8')
        finished(result)
