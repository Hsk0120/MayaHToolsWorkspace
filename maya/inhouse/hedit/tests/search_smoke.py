"""検索バー(入力中の絞り込み・検索条件・選択範囲内で検索・AB・不正な正規表現の吹き出し)、
一括置換のUndo、文字サイズの変更をMaya GUI内で検証する。"""

#: 正規表現を使わない検索と、正規表現の検索を突き合わせる本文。大文字小文字の特殊な対応(K と KELVIN SIGN、
#: s と LONG S、トルコ語の I)・サロゲートの対(絵文字・数学用の英字)・結合文字・漢字を含む。
PARITY_TEXT = ('Kelvin: K k K; long s: ſ s S; turkish: İ i I ı; sharp: ß ẞ ss; '
               'sigma: Σ σ ς; emoji: \U0001F600x a\U0001F600; math: \U0001D400bc bc; '
               'combining: éx _x x_ 9x x9 x; cjk: 漢字x x漢字; mark: àb b')

#: 突き合わせる検索語。
PARITY_NEEDLES = ('k', 'K', 's', 'S', 'i', 'I', 'x', 'ss', 'bc', 'b', 'a', '_x', 'x9', 'σ', '\U0001F600', 'e')


def _total(count):
    """str: 件数の表示(``2 of 5``)から全体の件数の部分(``of 5``)を取り出す。一致なしは ``No results``。"""
    text = count.text()
    return text[text.index('of'):] if 'of' in text else text


def check_plain_matches_regex(window, code, field, case, word, regex, count, next_match, QtCore, QtGui):
    """正規表現を使わない検索(速い方法)の結果が、同じ検索語を正規表現で探した結果と同じか確かめる。

    大文字小文字の区別・単語単位の全ての組み合わせで、件数と最初の一致の位置を比べる。

    Args:
        window (QMainWindow): hedit の編集画面。
        code (QPlainTextEdit): 検索するコード欄。
        field (QLineEdit): 検索語の入力欄。
        case, word, regex (QAbstractButton): 大文字小文字・単語単位・正規表現の切り替え。
        count (QLabel): 件数の表示。
        next_match (QAction): 次の一致へ(F3)。
        QtCore, QtGui: Maya の PySide のモジュール。
    """
    code.setPlainText(PARITY_TEXT)
    for match_case in (False, True):
        for whole_word in (False, True):
            case.setChecked(match_case)
            word.setChecked(whole_word)
            for needle in PARITY_NEEDLES:
                found = []
                for use_regex in (False, True):
                    regex.setChecked(use_regex)
                    field.setText(QtCore.QRegularExpression.escape(needle) if use_regex else needle)
                    code.moveCursor(QtGui.QTextCursor.Start)
                    next_match.trigger()
                    cursor = code.textCursor()
                    found.append((_total(count), cursor.selectionStart(), cursor.selectedText()))
                assert found[0] == found[1], (needle, match_case, whole_word, found)
    case.setChecked(False)
    word.setChecked(False)
    regex.setChecked(False)


def check_large_document(window, code, field, count, next_match, QtCore, QtGui, QtTest):
    """大きな本文(20万文字超)では、入力が止まってから検索し、Enter はその検索を済ませてから次へ移る。

    Args:
        window (QMainWindow): hedit の編集画面。
        code (QPlainTextEdit): 検索するコード欄。
        field (QLineEdit): 検索語の入力欄。
        count (QLabel): 件数の表示。
        next_match (QAction): 次の一致へ(F3)。
        QtCore, QtGui, QtTest: Maya の PySide のモジュール。
    """
    line = 'value = compute(alpha, beta)  # comment\n'
    text = line * 6000 + 'needle_unique = 1\n' + line * 10
    code.setPlainText(text)
    code.moveCursor(QtGui.QTextCursor.Start)
    field.clear()
    field.setFocus()
    QtTest.QTest.keyClicks(field, 'needle_uniq')
    # 入力の直後はまだ検索していない(打鍵のたびに全文を探さない)。待つと件数が出る。
    # PySide2 の QTest には qWait が無いので、イベントループを回して待つ。
    for _ in range(100):
        if count.text() == '1 of 1':
            break
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(10, loop.quit)
        (loop.exec if hasattr(loop, 'exec') else loop.exec_)()
    assert count.text() == '1 of 1', count.text()
    assert code.textCursor().selectedText() == 'needle_uniq'
    # 入力の直後に Enter を押しても、待っていた検索を済ませてから次の一致へ移る(待たない場合と同じ結果)。
    field.clear()
    code.moveCursor(QtGui.QTextCursor.Start)
    QtTest.QTest.keyClicks(field, 'beta')
    QtTest.QTest.keyClick(field, QtCore.Qt.Key_Return)
    assert code.textCursor().selectionStart() == text.index('beta', text.index('beta') + 1), code.textCursor().selectionStart()
    assert count.text() == '2 of 6010', count.text()
    field.clear()
    code.setPlainText('')  # 後の検証を大きな本文で遅くしない。


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
    check_plain_matches_regex(window, code, field, case, word, regex, count, next_match, QtCore, QtGui)
    check_large_document(window, code, field, count, next_match, QtCore, QtGui, QtTest)
    code.setFocus()
    QtTest.QTest.keyClick(code, QtCore.Qt.Key_0, QtCore.Qt.ControlModifier)
    QtTest.QTest.keyClick(code, QtCore.Qt.Key_Equal, QtCore.Qt.ControlModifier)
    assert 'font-size:15px' in window.styleSheet()
    QtTest.QTest.keyClick(code, QtCore.Qt.Key_Minus, QtCore.Qt.ControlModifier)
    assert 'font-size:14px' in window.styleSheet()
    code.document().setModified(False)
