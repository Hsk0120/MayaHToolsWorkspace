"""設定を切り替え、実入力・補完候補・保存結果を検証する。"""
def check(window, directory, QtCore, QtGui, QtWidgets, QtTest):
    """``gui_smoke.py`` から呼ばれ、開いている編集画面で検証する。失敗は ``AssertionError``。

    Args:
        window (QMainWindow): hedit の編集画面。
        directory (Path): 一時ファイルを置くフォルダー。
        QtCore, QtGui, QtWidgets, QtTest: Maya の PySide(2 / 6)のモジュール。
    """
    action_type = getattr(QtWidgets, 'QAction', None) or QtGui.QAction
    actions = {a.objectName()[7:]: a for a in window.findChildren(action_type) if a.objectName().startswith('option_')}
    assert len(actions) == 13
    original = {key: a.isChecked() for key, a in actions.items()}
    code = window.findChild(QtWidgets.QTabWidget).currentWidget()
    old_path = code.property('path')
    def enter(text):
        code.setPlainText(text)
        code.moveCursor(QtGui.QTextCursor.End)
        code.setFocus()
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
    def candidates(text):
        code.setPlainText(text)
        code.moveCursor(QtGui.QTextCursor.End)
        code.setFocus()
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier)
        completer = code.findChild(QtWidgets.QCompleter)
        result = [completer.model().index(i, 0).data() for i in range(completer.model().rowCount())]
        completer.popup().hide()
        return result
    try:
        from hedit import analysis
        real_analyze = analysis.analyze
        calls = []
        def counted(source):
            calls.append(source)
            return real_analyze(source)
        def wait():
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(1000, loop.quit)
            (loop.exec if hasattr(loop, 'exec') else loop.exec_)()
        analysis.analyze = counted
        try:
            actions['staticAnalysis'].setChecked(True)
            code.setPlainText('# 日本語\nif True\n    pass')
            wait()
            problems = window.findChild(QtWidgets.QListWidget, 'analysisProblems')
            assert problems.isVisible() and problems.item(0).data(QtCore.Qt.UserRole) == 2
            QtTest.QTest.mouseClick(problems.viewport(), QtCore.Qt.LeftButton, pos=problems.visualItemRect(problems.item(0)).center())
            assert code.textCursor().blockNumber() == 1
            code.setPlainText('value = 1')
            wait()
            assert 'No syntax problems' in problems.item(0).text()
            actions['staticAnalysis'].setChecked(False)
            previous_calls = len(calls)
            code.setPlainText('if ???')
            wait()
            assert len(calls) == previous_calls and not problems.isVisible()
            actions['staticAnalysis'].setChecked(True)
            actions['staticAnalysis'].setChecked(False)
            wait()
            assert len(calls) == previous_calls
        finally:
            analysis.analyze = real_analyze
        actions['smartIndent'].setChecked(False)
        enter('if True:')
        assert code.toPlainText() == 'if True:\n'
        actions['smartIndent'].setChecked(True)
        enter('if True:')
        assert code.toPlainText() == 'if True:\n    '
        QtTest.QTest.keyClick(code, QtCore.Qt.Key_Backspace)
        assert code.toPlainText() == 'if True:\n'
        actions['whitespace'].setChecked(True)
        assert code.document().defaultTextOption().flags() & QtGui.QTextOption.ShowTabsAndSpaces
        actions['includeKeywords'].setChecked(False)
        assert 'return' not in candidates('ret')
        actions['includeKeywords'].setChecked(True)
        assert 'return' in candidates('ret')
        actions['includeBuiltins'].setChecked(False)
        assert 'print' not in candidates('pri')
        actions['includeBuiltins'].setChecked(True)
        assert 'print' in candidates('pri')
        actions['completeLetters'].setChecked(False)
        actions['completeDot'].setChecked(False)
        code.setPlainText('import maya.cmds as cmds\ncmds.')
        code.moveCursor(QtGui.QTextCursor.End)
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(250, loop.quit)
        (loop.exec if hasattr(loop, 'exec') else loop.exec_)()
        assert not code.findChild(QtWidgets.QCompleter).popup().isVisible()
        assert 'ls' in candidates('import maya.cmds as cmds\ncmds.l')
        actions['trimWhitespace'].setChecked(True)
        actions['finalNewline'].setChecked(True)
        path = directory / 'formatted.py'
        code.setProperty('path', str(path))
        code.setPlainText('a = 1  \n# comment\t')
        next(a for a in window.findChildren(action_type) if a.text() == 'Save').trigger()
        assert path.read_text(encoding='utf-8') == 'a = 1\n# comment\n'
        assert code.toPlainText() == 'a = 1\n# comment\n'
        code.undo()
        assert code.toPlainText() == 'a = 1  \n# comment\t'
        from maya import cmds
        from pathlib import Path
        settings = QtCore.QSettings(str(Path(cmds.hedit(sessionPath=True)).with_name('preferences.ini')), QtCore.QSettings.IniFormat)
        assert str(settings.value('finalNewline')).lower() == 'true'

        # Edit > Preferences > Reset to defaults…: 確認でキャンセルすれば何も変えず、
        # Resetなら13項目と文字サイズを初期値へ戻し、preferences.iniから値を消す。
        defaults = {'completeLetters': True, 'completeDot': True, 'includeKeywords': True, 'includeBuiltins': True,
                    'staticAnalysis': False, 'outputLineNumbers': False, 'outputWrap': False, 'spellCheck': True,
                    'smartIndent': True, 'backspaceIndent': True, 'whitespace': False,
                    'trimWhitespace': False, 'finalNewline': False}
        assert set(defaults) == set(actions)
        reset = next(a for a in window.findChildren(action_type) if a.objectName() == 'resetPreferences')

        def answer_dialog(button):
            """確認ダイアログが開いたら指定のボタンを押す(ダイアログはexecで待つため、タイマーで操作する)。"""
            def press():
                dialog = QtWidgets.QApplication.activeModalWidget()
                if isinstance(dialog, QtWidgets.QMessageBox):
                    dialog.button(button).click()
                else:
                    QtCore.QTimer.singleShot(50, press)
            QtCore.QTimer.singleShot(0, press)

        for key, value in defaults.items():
            actions[key].setChecked(not value)
        zoom_in = next(a for a in window.findChildren(action_type) if a.objectName() == 'zoomIn')
        zoom_in.trigger()
        zoom_in.trigger()
        zoomed_style = window.styleSheet()
        answer_dialog(QtWidgets.QMessageBox.Cancel)
        reset.trigger()
        assert all(actions[key].isChecked() == (not value) for key, value in defaults.items())
        assert window.styleSheet() == zoomed_style
        answer_dialog(QtWidgets.QMessageBox.Reset)
        reset.trigger()
        assert {key: a.isChecked() for key, a in actions.items()} == defaults
        assert not (code.document().defaultTextOption().flags() & QtGui.QTextOption.ShowTabsAndSpaces)
        assert window.findChild(QtWidgets.QPlainTextEdit, 'output').lineWrapMode() == QtWidgets.QPlainTextEdit.NoWrap
        settings.sync()
        assert not any(settings.contains(key) for key in list(defaults) + ['fontPixels']), settings.allKeys()
        # 文字サイズは、View > Reset zoomと同じ大きさ(標準14px)に戻っている。
        reset_style = window.styleSheet()
        assert reset_style != zoomed_style
        next(a for a in window.findChildren(action_type) if a.objectName() == 'zoomReset').trigger()
        assert window.styleSheet() == reset_style
        # 確認ダイアログ(モーダル)を閉じた後、テスト用のMayaが前面でないとWindowsが別のウィンドウを
        # 前面に戻すことがある。後続のテストがキー入力できるよう、hedit を前面に戻しておく。
        window.window().activateWindow()
        code.setFocus()
        wait()
    finally:
        for key, state in original.items():
            actions[key].setChecked(state)
        code.setProperty('path', old_path)
        code.document().setModified(False)
