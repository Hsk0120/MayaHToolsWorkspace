"""検索バー(入力中の絞り込み・検索条件・選択範囲内で検索・AB・不正な正規表現の吹き出し)、
一括置換のUndo、文字サイズの変更をMaya GUI内で検証する。"""
def check(window, QtCore, QtGui, QtWidgets, QtTest):
    """``gui_smoke.py`` から呼ばれ、開いている編集画面で検証する。失敗は ``AssertionError``。

    Args:
        window (QMainWindow): hedit の編集画面。
        QtCore, QtGui, QtWidgets, QtTest: Maya の PySide(2 / 6)のモジュール。
    """
    code = window.findChild(QtWidgets.QTabWidget).currentWidget()
    field = window.findChild(QtWidgets.QLineEdit, 'findText')
    replacement = window.findChild(QtWidgets.QLineEdit, 'replaceText')
    case = window.findChild(QtWidgets.QAbstractButton, 'searchCase')
    word = window.findChild(QtWidgets.QAbstractButton, 'searchWord')
    regex = window.findChild(QtWidgets.QAbstractButton, 'searchRegex')
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
    replace_all = window.findChild(QtWidgets.QAbstractButton, 'replaceAll')
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
    # 選択範囲内で検索: オンにした時点の選択の中だけを数え、置換する。選択が無ければオンにならない。
    in_selection = window.findChild(QtWidgets.QAbstractButton, 'findInSelection')
    count = window.findChild(QtWidgets.QLabel, 'searchCount')
    code.setPlainText('cat cat cat cat')
    code.moveCursor(QtGui.QTextCursor.Start)
    in_selection.setChecked(True)
    assert not in_selection.isChecked()
    cursor = code.textCursor()
    cursor.setPosition(4)
    cursor.setPosition(11, QtGui.QTextCursor.KeepAnchor)
    code.setTextCursor(cursor)
    field.setText('cat')
    in_selection.setChecked(True)
    assert count.text() == '? of 2', count.text()
    replacement.setText('dog')
    replace_all.click()
    assert code.toPlainText() == 'cat dog dog cat', code.toPlainText()
    code.undo()
    in_selection.setChecked(False)
    # 大文字小文字を保つ置換(AB)。
    preserve = window.findChild(QtWidgets.QAbstractButton, 'preserveCase')
    code.setPlainText('Cat CAT cat')
    preserve.setChecked(True)
    replace_all.click()
    assert code.toPlainText() == 'Dog DOG dog', code.toPlainText()
    code.undo()
    preserve.setChecked(False)
    # 不正な正規表現は、検索欄の下に理由の吹き出しを出す。
    regex.setChecked(True)
    field.setText('(')
    next_match.trigger()
    bubble = window.findChild(QtWidgets.QLabel, 'findError')
    assert bubble.isVisible() and bubble.text().startswith('Invalid regular expression'), bubble.text()
    assert count.text() == 'No results'
    field.setText('cat')
    next_match.trigger()
    assert not bubble.isVisible()
    regex.setChecked(False)
    code.setFocus()
    QtTest.QTest.keyClick(code, QtCore.Qt.Key_0, QtCore.Qt.ControlModifier)
    QtTest.QTest.keyClick(code, QtCore.Qt.Key_Equal, QtCore.Qt.ControlModifier)
    assert 'font-size:15px' in window.styleSheet()
    QtTest.QTest.keyClick(code, QtCore.Qt.Key_Minus, QtCore.Qt.ControlModifier)
    assert 'font-size:14px' in window.styleSheet()
    code.document().setModified(False)
