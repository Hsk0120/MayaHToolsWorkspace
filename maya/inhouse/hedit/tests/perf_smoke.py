"""編集画面の操作にかかる時間を Maya GUI の中で測る(計測用。速さの合否は判定しない)。

``run_gui.py --suite perf_smoke.py`` で実行し、結果は出力先の ``result.json`` の ``timings`` に入る。
測るもの:

* Window メニューの組み立て(``buildViewMenu``)とプラグインのロード
* 編集画面を開く時間(タブ1つ・2,000行のタブ30個の復元)と、表示までの時間
* 復元していないタブへの切り替え・新しいタブ・文字サイズの変更
* カーソルを動かしているだけの5秒間の tabs.json の書き込み回数と、本文の変更から自動保存までの時間
* 約1MBの本文での検索バーの1文字ごとの時間(入力の処理と、件数が出るまで)
* ファイル名で開く(Ctrl+P)の一覧の作成(Explorer のフォルダーに多数のファイルがある場合)

C++ 側の計測値(動的プロパティ)があれば、それも記録する。機能の確認として、復元したタブの本文・
未保存の印・検索の件数・保存の内容が正しいことは確かめる(失敗は ``AssertionError``)。
"""
import json
import os
from pathlib import Path
import sys
import time
import traceback

#: 復元するタブの数と、1タブの行数。
TAB_COUNT = 30
LINES_PER_TAB = 2000
#: 検索に使う本文の大きさ(文字数の目安)。
SEARCH_DOCUMENT_SIZE = 1000000


def _python_source(lines, seed):
    """計測用の Python の本文を作る。

    Args:
        lines (int): 行数の目安。
        seed (int): 関数名に入れる番号(タブごとに本文を変える)。

    Returns:
        str: 本文。
    """
    block = (
        'def function_{0}_{1}(value, *args, **kwargs):\n'
        '    """Docstring for function {1}."""\n'
        '    result = cmds.ls(selection=True)  # comment {1}\n'
        '    for item in range({1}):\n'
        '        print("item", item, \'text {1}\')\n'
        '    return result\n'
        '\n')
    parts = []
    count = 0
    index = 0
    while count < lines:
        parts.append(block.format(seed, index))
        count += 7
        index += 1
    return ''.join(parts)


def _write_session(path, texts, folders, active=0):
    """tabs.json(version 2)と tabs/<id>.txt を書く。

    Args:
        path (Path): tabs.json のパス。
        texts (list[str]): タブごとの本文。
        folders (list[str]): Explorer のルートフォルダー。
        active (int): 選択していたタブの番号。

    Returns:
        list[str]: タブの識別子。
    """
    directory = path.parent / 'tabs'
    directory.mkdir(parents=True, exist_ok=True)
    for old in directory.glob('*.txt'):
        old.unlink()
    tabs = []
    for index, text in enumerate(texts):
        tab_id = 'perf{:04d}'.format(index)
        # Path.write_textのnewline引数はPython 3.10以降(Maya 2022・2023では使えない)なので、openで書く。
        with open(str(directory / (tab_id + '.txt')), 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
        tabs.append({'id': tab_id, 'path': '', 'language': 'python', 'modified': True,
                     'position': 10 + index, 'anchor': 10 + index})
    data = {'version': 2, 'active': active, 'tabs': tabs, 'folders': folders, 'explorerVisible': False}
    path.write_text(json.dumps(data), encoding='utf-8')
    return [tab['id'] for tab in tabs]


def _picker_folder():
    """ファイル名で開くの計測に使うフォルダー。

    Returns:
        str: 環境変数 ``HEDIT_PERF_FOLDER`` があればそれ。無ければ Maya に同梱の Python の Lib フォルダー
        (数千の .py と __pycache__ を含む)。フォルダー名は Maya の版で違う(2022 は ``Python37/Lib``\ 、
        2023 以降は ``Python/Lib``\ )ので、動いている Python の標準ライブラリ(``os`` モジュール)の場所から求める。
    """
    folder = os.environ.get('HEDIT_PERF_FOLDER')
    if folder:
        return folder
    return str(Path(os.__file__).resolve().parent)


def main(output_dir, finished):
    """GUIランナー(``tools/run_hlib_gui_versions.py``)が、専用の Maya GUI の中で呼ぶ入口。

    Args:
        output_dir (str): 結果の ``result.json`` の出力先。
        finished (callable): 終了時に結果の辞書を渡して呼ぶ関数(Maya の終了はランナーが行う)。
    """
    result = {'status': 'error', 'checks': [], 'timings': {}}
    try:
        _measure(result, output_dir)
        result['status'] = 'passed'
    except Exception:
        result['error'] = traceback.format_exc()
    Path(output_dir, 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    finished(result)


def _measure(result, output_dir):
    """計測の本体。結果は ``result['timings']`` と ``result['checks']`` に足す。

    Args:
        result (dict): 結果の辞書。
        output_dir (str): 画像の出力先(検索バーと影の見た目を版の間で見比べる)。
    """
    from maya import cmds
    try:
        from PySide6 import QtCore, QtGui, QtWidgets, QtTest
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets, QtTest
    timings = result['timings']
    action_type = getattr(QtWidgets, 'QAction', None) or QtGui.QAction

    def milliseconds(function):
        """関数を呼び、かかった時間を返す。"""
        start = time.perf_counter()
        function()
        return round((time.perf_counter() - start) * 1000.0, 2)

    def wait(ms):
        """イベントループを回しながら待つ。"""
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, loop.quit)
        (loop.exec if hasattr(loop, 'exec') else loop.exec_)()

    def wait_until(condition, limit_ms=10000, step_ms=5):
        """条件が満たされるまでイベントループを回す。

        Returns:
            float | None: 満たされるまでのミリ秒。期限切れなら None。
        """
        start = time.perf_counter()
        while (time.perf_counter() - start) * 1000.0 < limit_ms:
            if condition():
                return round((time.perf_counter() - start) * 1000.0, 2)
            wait(step_ms)
        return None

    def cpp_timings(widget, names):
        """C++ 側の計測値(部品の動的プロパティ)を記録する。無い版では記録しない。"""
        values = {}
        for name in names:
            value = widget.property(name)
            if value is not None:
                values[name] = value
        return values

    # ---- Window メニューとプラグインのロード ----
    # ロード前後の Window メニューの項目数(Maya は初めて開くまで組み立てを遅らせるが、hedit はロード時に組み立てる)。
    timings['window_menu_items_before_load'] = cmds.menu('MayaWindow|mainWindowMenu', query=True, numberOfItems=True)
    timings['load_plugin_ms'] = milliseconds(lambda: cmds.loadPlugin('hedit', quiet=True))
    timings['window_menu_items_after_load'] = cmds.menu('MayaWindow|mainWindowMenu', query=True, numberOfItems=True)
    import hedit
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import hedit_host as host
    session = Path(cmds.hedit(sessionPath=True))
    session.parent.mkdir(parents=True, exist_ok=True)

    # ---- 1回目(何も保存されていない状態。ようこそのタブ)----
    timings['open_cold_welcome_ms'] = milliseconds(lambda: cmds.heditTest(editor=True))
    timings['show_cold_ms'] = milliseconds(lambda: (hedit.show(), wait(0)))
    window = host.editor()
    timings['cpp_cold'] = cpp_timings(window, ['openMilliseconds'])
    tabs = window.findChild(QtWidgets.QTabWidget)
    assert tabs.count() == 1 and 'import maya.cmds' in tabs.currentWidget().toPlainText()
    result['checks'].append('welcome_tab_without_session')
    wait(500)
    timings['unload_plugin_welcome_ms'] = milliseconds(lambda: cmds.unloadPlugin('hedit'))

    # ---- タブ1つ(保存済み)----
    _write_session(session, [_python_source(LINES_PER_TAB, 0)], [])
    cmds.loadPlugin('hedit', quiet=True)
    timings['open_1tab_ms'] = milliseconds(lambda: cmds.heditTest(editor=True))
    timings['show_1tab_ms'] = milliseconds(lambda: (hedit.show(), wait(0)))
    window = host.editor()
    timings['cpp_1tab'] = cpp_timings(window, ['openMilliseconds'])
    wait(500)
    cmds.unloadPlugin('hedit')

    # ---- 2,000行のタブ30個(Explorer に多数のファイルのフォルダー)----
    texts = [_python_source(LINES_PER_TAB, index) for index in range(TAB_COUNT)]
    folder = _picker_folder()
    ids = _write_session(session, texts, [folder], active=0)
    cmds.loadPlugin('hedit', quiet=True)
    timings['open_30tabs_ms'] = milliseconds(lambda: cmds.heditTest(editor=True))
    timings['show_30tabs_ms'] = milliseconds(lambda: (hedit.show(), wait(0)))
    window = host.editor()
    timings['cpp_30tabs'] = cpp_timings(window, ['openMilliseconds'])
    tabs = window.findChild(QtWidgets.QTabWidget)
    assert tabs.count() == TAB_COUNT and tabs.currentIndex() == 0
    assert tabs.currentWidget().toPlainText() == texts[0]
    # 選択していないタブも、見出しに未保存の印が付いている(本文を読み込む前でも)。
    assert all(tabs.tabText(index).endswith('●') for index in range(TAB_COUNT)), \
        [tabs.tabText(index) for index in range(TAB_COUNT)]
    result['checks'].append('restored_30_tabs_titles')
    wait(1000)

    # 復元していないタブへの切り替え(初めて選んだときに本文を読み込む)。
    timings['switch_to_restored_tab_ms'] = milliseconds(lambda: (tabs.setCurrentIndex(TAB_COUNT - 1), wait(0)))
    code = tabs.currentWidget()
    assert code.toPlainText() == texts[-1]
    cursor = code.textCursor()
    assert (cursor.anchor(), cursor.position()) == (10 + TAB_COUNT - 1, 10 + TAB_COUNT - 1)
    assert code.document().isModified()
    timings['switch_back_ms'] = milliseconds(lambda: (tabs.setCurrentIndex(0), wait(0)))
    result['checks'].append('lazy_tab_loaded_on_switch')

    # ---- カーソルを動かすだけの5秒間の tabs.json の書き込み ----
    wait(2500)  # 開いた直後の保存を済ませる。

    def stamp():
        try:
            info = os.stat(str(session))
            return (info.st_mtime_ns, info.st_ino, info.st_size)
        except OSError:
            return None

    code = tabs.currentWidget()
    code.setFocus()
    writes = [0]
    last = [stamp()]
    moves = [0]
    start = time.perf_counter()
    while time.perf_counter() - start < 5.0:
        cursor = code.textCursor()
        cursor.setPosition(20 + (moves[0] % 50) * 3)
        code.setTextCursor(cursor)
        moves[0] += 1
        for _ in range(4):
            wait(25)
            current = stamp()
            if current != last[0]:
                writes[0] += 1
                last[0] = current
    timings['cursor_only_tabs_json_writes_5s'] = writes[0]
    timings['cursor_only_moves'] = moves[0]
    timings['cpp_session'] = cpp_timings(window, ['sessionWrites', 'sessionTextWrites', 'sessionListings'])

    # 本文を変えたら、入力が止まってから約1.5秒で本文のファイルへ保存される(落ちても失わない)。
    before = stamp()
    code.textCursor().insertText('# edited\n')
    edited_text = code.toPlainText()
    text_file = session.parent / 'tabs' / (ids[0] + '.txt')
    latency = wait_until(lambda: text_file.read_text(encoding='utf-8') == edited_text, 10000, 20)
    timings['edit_to_text_file_ms'] = latency
    assert latency is not None, 'the edited text was not autosaved'
    assert stamp() != before
    result['checks'].append('edit_autosaved')

    # ---- 文字サイズの変更と新しいタブ ----
    actions = {action.objectName() or action.text(): action for action in window.findChildren(action_type)}
    timings['zoom_in_ms'] = milliseconds(lambda: (actions['zoomIn'].trigger(), wait(0)))
    timings['zoom_out_ms'] = milliseconds(lambda: (actions['zoomOut'].trigger(), wait(0)))
    timings['new_tab_ms'] = milliseconds(lambda: (actions['New Python tab'].trigger(), wait(0)))
    timings['new_tab_ms_2'] = milliseconds(lambda: (actions['New Python tab'].trigger(), wait(0)))
    # 内訳の確認: ウィンドウ全体のスタイルシートを当て直す時間と、スタイルシートが無い場合の新しいタブ。
    sheet = window.styleSheet()
    timings['restyle_window_ms'] = milliseconds(lambda: (window.setStyleSheet(sheet + ' '), wait(0)))
    window.setStyleSheet('')
    timings['new_tab_without_window_stylesheet_ms'] = milliseconds(
        lambda: (actions['New Python tab'].trigger(), wait(0)))
    window.setStyleSheet(sheet)
    wait(100)

    # ---- 約1MBの本文での検索 ----
    code = tabs.currentWidget()
    big = _python_source(SEARCH_DOCUMENT_SIZE // 40, 999)
    timings['search_document_chars'] = len(big)
    code.setPlainText(big)
    code.moveCursor(QtGui.QTextCursor.Start)
    wait(200)
    timings['open_find_ms'] = milliseconds(lambda: (actions['Find…'].trigger(), wait(0)))
    field = window.findChild(QtWidgets.QLineEdit, 'findText')
    count = window.findChild(QtWidgets.QLabel, 'searchCount')
    word = window.findChild(QtWidgets.QAbstractButton, 'searchWord')
    field.clear()
    field.setFocus()
    lower = big.lower()

    def expected_count(text):
        """検索語の件数の表示(大文字小文字を区別しない。10万件を超えると検索をやめて No results)。"""
        number = lower.count(text)
        return 'No results' if number > 100000 or number == 0 else 'of {}'.format(number)

    bar = window.findChild(QtWidgets.QWidget, 'findBar')

    def computations():
        """C++ 側で検索し直した回数(無い版では None)。"""
        return bar.property('searchComputations')

    def settled_after(before, expected, limit_ms=5000):
        """検索し直して(回数が増えて)件数が期待どおりになるまでのミリ秒。回数の無い版は件数だけで判断する。"""
        if before is None:
            return wait_until(lambda: count.text().endswith(expected), limit_ms, 2)
        return wait_until(lambda: (computations() or 0) > before and count.text().endswith(expected), limit_ms, 2)

    keystrokes = []
    word_text = 'result'
    for length in range(1, len(word_text) + 1):
        prefix = word_text[:length]
        before = computations()
        typed = milliseconds(lambda: QtTest.QTest.keyClicks(field, prefix[-1]))
        settled = settled_after(before if before is not None else None, expected_count(prefix))
        keystrokes.append({'text': prefix, 'keystroke_ms': typed, 'until_count_ms': settled, 'count': count.text(),
                           'search_ms': bar.property('searchMilliseconds')})
    timings['find_keystrokes'] = keystrokes
    total = lower.count(word_text)
    assert count.text().endswith('of {}'.format(total)), count.text()
    # F3(次の一致)を続けて押す。
    next_match = actions['Find next']
    timings['find_next_ms'] = [milliseconds(next_match.trigger) for _ in range(5)]
    # 単語単位を切り替え、件数を出し直す(大きな本文では少し待ってから数え直す)。
    before = computations()
    timings['find_whole_word_toggle_ms'] = milliseconds(lambda: (word.setChecked(True), wait(0)))
    timings['find_whole_word_until_count_ms'] = settled_after(before, 'of {}'.format(total))
    before = computations()
    word.setChecked(False)
    settled_after(before, 'of {}'.format(total))
    # 選択中の一致を1文字に置き換えたときの、件数と強調の出し直し(本文の変化から150ms待ってから行う)。
    assert code.textCursor().selectedText() == word_text
    before = computations()
    code.textCursor().insertText('x')
    timings['find_refresh_after_edit_ms'] = settled_after(before, 'of {}'.format(total - 1))
    timings['cpp_find'] = cpp_timings(window.findChild(QtWidgets.QWidget, 'findBar'),
                                      ['searchMilliseconds', 'searchComputations'])
    # 検索バーの描き直し(影の効果を含む)。入力欄のカーソルの点滅でも描き直される。
    find_bar = window.findChild(QtWidgets.QWidget, 'findBar')
    timings['find_bar_repaint_20_ms'] = milliseconds(lambda: [find_bar.repaint() for _ in range(20)])
    # 検索バーと周りの影を画像に残す(影の描き方を変えた前後で見比べる)。
    field.clearFocus()  # 入力欄のカーソルの点滅が画像に入らないようにする。
    wait(50)
    area = find_bar.geometry().adjusted(-20, -20, 20, 20)
    find_bar.parentWidget().grab(area).save(str(Path(output_dir, 'find_bar.png')))
    find_bar.hide()
    result['checks'].append('find_counts_on_large_document')

    # ---- ファイル名で開く(Ctrl+P)----
    picker_list = window.findChild(QtWidgets.QListWidget, 'quickPickList')

    def listed():
        """一覧にファイルが出たか(読み込み中の案内の行だけなら、まだ)。"""
        return picker_list.count() > 0 and bool(picker_list.item(0).flags() & QtCore.Qt.ItemIsEnabled)

    timings['quick_open_folder'] = folder
    timings['quick_open_trigger_ms'] = milliseconds(lambda: actions['quickOpen'].trigger())
    timings['quick_open_until_list_ms'] = wait_until(listed, 30000, 5)
    timings['quick_open_items_shown'] = picker_list.count()
    picker = window.findChild(QtWidgets.QFrame, 'quickPick')
    picker_input = window.findChild(QtWidgets.QLineEdit, 'quickPickInput')
    # 一覧の中身と順番が、以前の集め方(QDirIteratorで全て降りてから、隠しフォルダーと__pycache__を除く)と同じ。
    root = QtCore.QFileInfo(folder).canonicalFilePath()
    expected = []
    seen = set()
    iterator = QtCore.QDirIterator(root, ['*.py', '*.mel'], QtCore.QDir.Files, QtCore.QDirIterator.Subdirectories)
    while iterator.hasNext() and len(expected) < 5000:
        path = iterator.next()
        relative = QtCore.QDir(root).relativeFilePath(path)
        if relative.startswith('.') or '/.' in relative or '__pycache__' in relative:
            continue
        info = QtCore.QFileInfo(path)
        if info.absoluteFilePath().lower() in seen or not info.isFile():
            continue
        seen.add(info.absoluteFilePath().lower())
        expected.append(info)
    shown = [picker_list.item(row).text() for row in range(picker_list.count())]
    wanted = [info.fileName() + '    ' + info.absolutePath() for info in expected[:len(shown)]]
    assert shown == wanted, (shown[:5], wanted[:5])
    count_property = window.property('fileListCount')
    assert count_property is None or count_property == len(expected), (count_property, len(expected))
    timings['quick_open_expected_count'] = len(expected)
    result['checks'].append('quick_open_same_files_and_order')
    # 名前で絞り込める(一覧は別スレッドで集めても、絞り込みと確定は今までどおり)。
    QtTest.QTest.keyClicks(picker_input, '__init__')
    assert picker_list.count() > 0 and picker_list.item(0).text().startswith('__init__'), picker_list.item(0).text()
    QtTest.QTest.keyClick(picker_input, QtCore.Qt.Key_Escape)
    # 2回目(一覧を覚えていれば、集め直さずにすぐ出る)。
    timings['quick_open_again_trigger_ms'] = milliseconds(lambda: actions['quickOpen'].trigger())
    timings['quick_open_again_until_list_ms'] = wait_until(listed, 30000, 5)
    QtTest.QTest.keyClick(picker_input, QtCore.Qt.Key_Escape)
    assert not picker.isVisible()
    timings['cpp_quick_open'] = cpp_timings(window, ['fileListMilliseconds', 'fileListCount'])
    result['checks'].append('quick_open_lists_files')

    # 後片付け: 大きなタブを閉じても確認を出さないよう、未保存の印を消してからアンロードする。
    for index in range(tabs.count()):
        tabs.widget(index).document().setModified(False)
    timings['unload_plugin_30tabs_ms'] = milliseconds(lambda: cmds.unloadPlugin('hedit'))
    # Window メニューは、ロード中に組み立てなくても、初めて開いたときに組み立てられて項目が入る。
    timings['window_menu_items_end'] = cmds.menu('MayaWindow|mainWindowMenu', query=True, numberOfItems=True)
