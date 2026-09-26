"""検索条件・一括置換のUndo・倍率変更をMaya GUI内で検証する。"""
def check(window, QtCore, QtGui, QtWidgets, QtTest):
    code = window.findChild(QtWidgets.QTabWidget).currentWidget()
    field = window.findChild(QtWidgets.QLineEdit, 'findText')
    replacement = window.findChild(QtWidgets.QLineEdit, 'replaceText')
    case = window.findChild(QtWidgets.QCheckBox, 'searchCase')
    word = window.findChild(QtWidgets.QCheckBox, 'searchWord')
    regex = window.findChild(QtWidgets.QCheckBox, 'searchRegex')
    action_type = getattr(QtWidgets, 'QAction', None) or QtGui.QAction
    actions = window.findChildren(action_type)
    # Enterを押さず、最初のhから検索し、入力を伸ばしても次の一致へ飛ばない。
    code.setPlainText('hlib first\nhlib second')
    code.moveCursor(QtGui.QTextCursor.Start)
    next(a for a in actions if a.text() == 'Find…').trigger()
    field.clear(); field.setFocus()
    for prefix, letter in zip(('h','hl','hli','hlib'), 'hlib'):
        QtTest.QTest.keyClicks(field,letter)
        assert code.textCursor().selectedText() == prefix
        assert code.textCursor().selectionStart() == 0
        assert window.findChild(QtWidgets.QLabel,'searchCount').text() == '1 of 2'
        assert field.hasFocus()
    QtTest.QTest.keyClick(field,QtCore.Qt.Key_Return)
    assert code.textCursor().selectionStart() == 11
    field.selectAll(); QtTest.QTest.keyClick(field,QtCore.Qt.Key_Backspace)
    assert not code.textCursor().hasSelection()
    assert not window.findChild(QtWidgets.QLabel,'searchCount').text()
    QtTest.QTest.keyClicks(field,'not_found')
    assert window.findChild(QtWidgets.QLabel,'searchCount').text() == 'No results'
    field.clear()
    next_match = next(a for a in actions if a.text() == 'Find next')
    replace_all = window.findChild(QtWidgets.QPushButton, 'replaceAll')
    sample = 'cat Cat scatter cat42 cat'
    code.setPlainText(sample)
    field.setText('cat')
    case.setChecked(True)
    word.setChecked(True)
    code.moveCursor(QtGui.QTextCursor.Start)
    next_match.trigger()
    assert code.textCursor().selectionStart() == 0
    next_match.trigger()
    assert code.textCursor().selectionStart() == sample.rindex('cat')
    next_match.trigger()
    assert code.textCursor().selectionStart() == 0
    case.setChecked(False)
    next_match.trigger()
    assert code.textCursor().selectedText() == 'Cat'
    regex.setChecked(True)
    word.setChecked(False)
    field.setText(r'cat\d+')
    next_match.trigger()
    assert code.textCursor().selectedText() == 'cat42'
    replacement.setText('日本語')
    replace_all.click()
    assert code.toPlainText() == sample.replace('cat42', '日本語')
    code.undo()
    assert code.toPlainText() == sample
    for invalid in ('[', '(?=cat)'):
        field.setText(invalid)
        replace_all.click()
        assert code.toPlainText() == sample
    regex.setChecked(False)
    field.setText('cat')
    replacement.setText('catcat')
    replace_all.click()
    assert code.toPlainText() == 'catcat catcat scatcatter catcat42 catcat'
    code.undo()
    assert code.toPlainText() == sample
    code.setFocus()
    QtTest.QTest.keyClick(code, QtCore.Qt.Key_0, QtCore.Qt.ControlModifier)
    QtTest.QTest.keyClick(code, QtCore.Qt.Key_Equal, QtCore.Qt.ControlModifier)
    assert 'font-size:15px' in window.styleSheet()
    QtTest.QTest.keyClick(code, QtCore.Qt.Key_Minus, QtCore.Qt.ControlModifier)
    assert 'font-size:14px' in window.styleSheet()
    code.document().setModified(False)
