"""ログ追記中の範囲保持、コピー、スクロール、読み取り専用を検証する。"""
def check(output, QtCore, QtGui, QtWidgets, QtTest):
    """出力欄の選択・コピー・追記中の保持・読み取り専用・スクロール追従を確かめる。

    Returns:
        bool: クリップボードを使ったコピーまで確かめた場合True。Windowsのクリップボードが
            ほかのアプリに占有されて読み書きできない場合は、コピーの確認だけ飛ばしてFalse。
    """
    from maya.api import OpenMaya as om
    clipboard = QtWidgets.QApplication.clipboard()
    saved = QtCore.QMimeData()
    for fmt in clipboard.mimeData().formats():
        saved.setData(fmt, clipboard.mimeData().data(fmt))
    # Windowsのクリップボードは全体で共有。ほかのアプリが開いたままだと読み書きできない(heditとは無関係)。
    clipboard.setText('hedit_clipboard_probe')
    clipboard_usable = clipboard.text() == 'hedit_clipboard_probe'

    def assert_clipboard(expected):
        if clipboard_usable:
            assert clipboard.text() == expected, (clipboard.text(), expected)
    def wait():
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(80, loop.quit)
        (loop.exec if hasattr(loop, 'exec') else loop.exec_)()
    try:
        output.setPlainText('コピー対象 日本語\nsecond line')
        output.setFocus()
        output.moveCursor(QtGui.QTextCursor.Start)
        output.moveCursor(QtGui.QTextCursor.Down)
        QtTest.QTest.mouseDClick(output.viewport(), QtCore.Qt.LeftButton, pos=output.cursorRect().center())
        assert output.textCursor().selectedText() == 'second'
        output.moveCursor(QtGui.QTextCursor.Start)
        QtTest.QTest.keyClick(output, QtCore.Qt.Key_End, QtCore.Qt.ShiftModifier)
        assert output.textCursor().selectedText() == 'コピー対象 日本語'
        QtTest.QTest.keyClick(output, QtCore.Qt.Key_C, QtCore.Qt.ControlModifier)
        assert_clipboard('コピー対象 日本語')
        QtTest.QTest.keyClick(output, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
        before = output.textCursor().selectedText()
        om.MGlobal.displayInfo('selection_new_log')
        wait()
        assert output.textCursor().selectedText() == before
        QtTest.QTest.keyClick(output, QtCore.Qt.Key_C, QtCore.Qt.ControlModifier)
        assert_clipboard(before.replace('\u2029', '\n'))
        text = output.toPlainText()
        QtTest.QTest.keyClicks(output, 'cannot_edit')
        assert output.toPlainText() == text
        output.setPlainText('\n'.join('line %s' % i for i in range(150)))
        output.verticalScrollBar().setValue(0)
        om.MGlobal.displayInfo('scroll_preserved')
        wait()
        assert output.verticalScrollBar().value() == 0
        output.moveCursor(QtGui.QTextCursor.End)
        output.verticalScrollBar().setValue(output.verticalScrollBar().maximum())
        om.MGlobal.displayInfo('follow_tail')
        wait()
        assert output.verticalScrollBar().value() == output.verticalScrollBar().maximum()
    finally:
        clipboard.setMimeData(saved)
        output.clear()
    return clipboard_usable
