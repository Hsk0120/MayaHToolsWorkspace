"""設定を切り替え、実入力・補完候補・保存結果を検証する。"""
def check(window, directory, QtCore, QtGui, QtWidgets, QtTest):
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
        from hedit.bridge import session_path
        from pathlib import Path
        settings = QtCore.QSettings(str(Path(session_path()).with_name('preferences.ini')), QtCore.QSettings.IniFormat)
        assert str(settings.value('finalNewline')).lower() == 'true'
    finally:
        for key, state in original.items():
            actions[key].setChecked(state)
        code.setProperty('path', old_path)
        code.document().setModified(False)
