"""Maya GUI内で実キーイベント・編集Undo・検索置換を検証する。"""
def check(window, QtCore, QtGui, QtWidgets, QtTest):
    tabs = window.findChild(QtWidgets.QTabWidget)
    code = tabs.currentWidget()
    ctrl, shift, alt = QtCore.Qt.ControlModifier, QtCore.Qt.ShiftModifier, QtCore.Qt.AltModifier

    def reset(text, position=0, end=None):
        code.setPlainText(text)
        cursor = code.textCursor()
        cursor.setPosition(position)
        if end is not None:
            cursor.setPosition(end, QtGui.QTextCursor.KeepAnchor)
        code.setTextCursor(cursor)
        code.setFocus()

    def key(key, mods=QtCore.Qt.NoModifier, target=None):
        QtTest.QTest.keyClick(target or code, key, mods)
        QtWidgets.QApplication.processEvents()

    reset('one\ntwo\n', 0, 8)
    key(QtCore.Qt.Key_Slash, ctrl)
    assert code.toPlainText() == '# one\n# two\n', code.toPlainText()
    key(QtCore.Qt.Key_Z, ctrl)
    assert code.toPlainText() == 'one\ntwo\n'
    key(QtCore.Qt.Key_Z, ctrl | shift)
    assert code.toPlainText() == '# one\n# two\n'
    code.selectAll()
    key(QtCore.Qt.Key_Slash, ctrl)
    assert code.toPlainText() == 'one\ntwo\n'
    reset('one\ntwo', 0, 4)  # 選択末尾が次の行の先頭の場合はその行を含めない。
    key(QtCore.Qt.Key_Tab)
    assert code.toPlainText() == '    one\ntwo'
    key(QtCore.Qt.Key_Backtab, shift)
    assert code.toPlainText() == 'one\ntwo'
    key(QtCore.Qt.Key_BracketRight, ctrl)
    key(QtCore.Qt.Key_BracketLeft, ctrl)
    assert code.toPlainText() == 'one\ntwo'
    reset('a\nb\nc', 2)
    key(QtCore.Qt.Key_Down, alt)
    assert code.toPlainText() == 'a\nc\nb'
    key(QtCore.Qt.Key_Up, alt)
    assert code.toPlainText() == 'a\nb\nc'
    reset('a\nb\nc', 0, 4)
    key(QtCore.Qt.Key_Down, alt | shift)
    assert code.toPlainText() == 'a\nb\na\nb\nc'
    key(QtCore.Qt.Key_Z, ctrl)
    assert code.toPlainText() == 'a\nb\nc'
    reset('a\nb\nc', 4)
    key(QtCore.Qt.Key_K, ctrl | shift)
    assert code.toPlainText() == 'a\nb'
    key(QtCore.Qt.Key_Z, ctrl)
    assert code.toPlainText() == 'a\nb\nc'
    reset('a\nb', 0)
    key(QtCore.Qt.Key_L, ctrl)
    assert code.textCursor().selectedText().replace('\u2029', '\n') == 'a\n'
    key(QtCore.Qt.Key_L, ctrl)
    assert code.textCursor().selectedText().replace('\u2029', '\n') == 'a\nb'
    clipboard = QtWidgets.QApplication.clipboard()
    old_clipboard = QtCore.QMimeData()
    for fmt in clipboard.mimeData().formats():
        old_clipboard.setData(fmt, clipboard.mimeData().data(fmt))
    try:
        reset('first\nlast', 6)
        key(QtCore.Qt.Key_C, ctrl)
        assert clipboard.text() == 'last\n'
        key(QtCore.Qt.Key_X, ctrl)
        assert code.toPlainText() == 'first'
        key(QtCore.Qt.Key_Z, ctrl)
        assert code.toPlainText() == 'first\nlast'
    finally:
        clipboard.setMimeData(old_clipboard)
    key(QtCore.Qt.Key_Z, alt)
    assert code.lineWrapMode() == QtWidgets.QPlainTextEdit.WidgetWidth
    key(QtCore.Qt.Key_Z, alt)
    assert code.lineWrapMode() == QtWidgets.QPlainTextEdit.NoWrap
    reset('apple apple')
    key(QtCore.Qt.Key_F, ctrl)
    field = window.findChild(QtWidgets.QLineEdit, 'findText')
    assert field.isVisible() and field.hasFocus()
    field.setText('apple')
    key(QtCore.Qt.Key_Return, target=field)
    assert code.textCursor().selectionStart() == 0
    key(QtCore.Qt.Key_F3, target=field)
    assert code.textCursor().selectionStart() == 6
    key(QtCore.Qt.Key_F3, shift, field)
    assert code.textCursor().selectionStart() == 0
    key(QtCore.Qt.Key_Escape, target=field)
    assert code.hasFocus()
    key(QtCore.Qt.Key_H, ctrl)
    replacement = window.findChild(QtWidgets.QLineEdit, 'replaceText')
    assert replacement.isVisible()
    replacement.setText('pear')
    window.findChild(QtWidgets.QPushButton, 'replaceAll').click()
    assert code.toPlainText() == 'pear pear'
    code.setFocus()
    key(QtCore.Qt.Key_Z, ctrl)
    assert code.toPlainText() == 'apple apple'
    field.setFocus()
    key(QtCore.Qt.Key_Escape, target=field)
    code.document().setModified(False)
    old_count = tabs.count()
    key(QtCore.Qt.Key_N, ctrl)
    assert tabs.count() == old_count + 1
    new_code = tabs.currentWidget()
    new_code.setFocus()
    key(QtCore.Qt.Key_Tab, ctrl | shift, new_code)
    assert tabs.currentWidget() == code
    key(QtCore.Qt.Key_Tab, ctrl)
    assert tabs.currentWidget() == new_code
    key(QtCore.Qt.Key_W, ctrl, new_code)
    assert tabs.count() == old_count and tabs.currentWidget() == code
    code.document().setModified(False)
