"""VS Code に合わせて足した機能(0.4.0)を、専用の Maya GUI の中で実際に操作して確かめ、画面を撮る。

確かめるもの: 保存前との差分の印・問題の波線と F8・同じ名前の強調・折りたたみ・見出しの固定表示・
記号へ移動・アウトライン・定義へ移動(別のファイル)・定義をその場で見る・保存前との差分の画面・
ファイル名で開く・引数のヒント・補完の一覧の種類と説明。
引数のヒントと補完は、テスト用の Maya がキーボードのフォーカスを得られたときだけ確かめる
(得られなければ結果の ``skipped`` に記録する)。
"""
import json
from pathlib import Path
import sys
import traceback

SAMPLE = '''"""Rig helper sample."""
import maya.cmds as cmds
import hedit_definition_probe


class ChainBuilder(object):
    """Build a joint chain."""

    def __init__(self, prefix, count=3):
        self.prefix = prefix
        self.count = count
        self.joints = []

    def build(self, radius=1.0):
        """Create joints along X.

        Args:
            radius (float): Joint radius.
        """
        cmds.select(clear=True)
        for index in range(self.count):
            name = "{}_{:02d}_jnt".format(self.prefix, index)
            joint = cmds.joint(name=name, position=(index * 2, 0, 0), radius=radius)
            self.joints.append(joint)
        return self.joints

    def orient(self, axis="xyz"):
        for joint in self.joints:
            cmds.joint(joint, edit=True, orientJoint=axis)


def build_chain(prefix="spine"):
    builder = ChainBuilder(prefix)
    joints = builder.build()
    builder.orient()
    hedit_definition_probe.make_probe()
    print(undefined_name)
    return joints
'''

PROBE = '''"""Definition probe."""


def make_probe(size=1):
    """Make a probe."""
    return size
'''


def main(output_dir, finished):
    """GUIランナー(``tools/run_hlib_gui_versions.py``)が、専用の Maya GUI の中で呼ぶ入口。

    Args:
        output_dir (str): 結果の ``result.json`` と画像の出力先。
        finished (callable): 終了時に結果の辞書を渡して呼ぶ関数(Maya の終了はランナーが行う)。
    """
    from maya import cmds
    try:
        from PySide6 import QtCore, QtGui, QtWidgets, QtTest
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets, QtTest
    directory = Path(output_dir)
    result = {'status': 'error', 'checks': [], 'skipped': []}

    def wait(ms):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, loop.quit)
        (loop.exec if hasattr(loop, 'exec') else loop.exec_)()

    try:
        cmds.loadPlugin('hedit', quiet=True)
        import hedit
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import hedit_host
        hedit.show()
        window = hedit_host.editor()
        window.resize(1300, 900)
        action_type = getattr(QtWidgets, 'QAction', None) or QtGui.QAction

        def action(name):
            return next(a for a in window.findChildren(action_type) if a.text() == name or a.objectName() == name)

        def editor():
            return window.findChild(QtWidgets.QTabWidget).currentWidget()

        def save(name):
            window.grab().save(str(directory / name))

        def focus():
            # テスト用の Maya はすぐには前面に出られないことがある(Windows の前面化の制限)。
            for _ in range(50):
                window.activateWindow()
                editor().setFocus()
                wait(100)
                if editor().hasFocus():
                    return True
            return False

        # 定義へ移動の先(まだ import していない .py)。
        probe_folder = directory / 'probe'
        probe_folder.mkdir(exist_ok=True)
        (probe_folder / 'hedit_definition_probe.py').write_text(PROBE, encoding='utf-8')
        sys.path.insert(0, str(probe_folder))

        static = action('option_staticAnalysis')
        if not static.isChecked():
            static.trigger()
        action('New Python tab').trigger()
        code = editor()
        # 保存先を持つタブは、Save でダイアログを出さずに保存する(保存した内容が差分の基準になる)。
        path = directory / 'rig_sample.py'
        code.setPlainText(SAMPLE)
        code.setProperty('path', str(path))
        action('Save').trigger()
        assert path.read_text(encoding='utf-8') == SAMPLE

        # 1. 変更して、差分の印・問題の波線・同じ名前の強調・見出しの固定表示を出す。
        text = SAMPLE.replace('self.count = count\n', 'self.count = count * 2\n')
        text = text.replace('    return joints\n', '    print(joints)\n    return joints\n')
        cursor = code.textCursor()
        cursor.select(QtGui.QTextCursor.Document)
        cursor.insertText(text)
        wait(1500)  # 構文チェック(0.8秒)と差分(0.3秒)。
        lines = text.split('\n')
        joint_line = next(i for i, line in enumerate(lines) if 'joint = cmds.joint' in line)
        cursor = code.textCursor()
        cursor.setPosition(code.document().findBlockByNumber(joint_line).position() + 13)
        code.setTextCursor(cursor)
        wait(400)
        code.verticalScrollBar().setValue(joint_line - 3)
        wait(300)
        sticky = code.findChild(QtWidgets.QWidget, 'stickyScroll')
        assert sticky is not None and sticky.isVisible(), 'sticky scroll not shown'
        problems = window.findChild(QtWidgets.QListWidget, 'analysisProblems')
        texts = [problems.item(i).text() for i in range(problems.count())]
        assert any('undefined_name' in item for item in texts), texts
        save('1-overview.png')
        result['checks'].append('diff_markers_problems_word_highlight_sticky')

        # 2. F8: 次の問題へ移り、行の下に説明を出す。
        code.verticalScrollBar().setValue(0)
        action('Next problem').trigger()
        wait(300)
        assert 'undefined_name' in code.textCursor().block().text()
        hover = code.findChild(QtWidgets.QFrame, 'problemPopup')
        assert hover is not None and hover.isVisible(), 'problem popup not shown'
        hover.grab().save(str(directory / '2-next-problem.png'))
        save('2-next-problem-window.png')
        hover.hide()
        result['checks'].append('next_problem_inline')

        # 3. 折りたたみ: def orient を畳む。
        orient_line = next(i for i, line in enumerate(lines) if 'def orient' in line)
        cursor.setPosition(code.document().findBlockByNumber(orient_line).position() + 8)
        code.setTextCursor(cursor)
        action('Fold').trigger()
        wait(200)
        assert not code.document().findBlockByNumber(orient_line + 1).isVisible()
        code.verticalScrollBar().setValue(max(0, orient_line - 10))
        wait(200)
        save('3-folded.png')
        action('Unfold all').trigger()
        result['checks'].append('folding')

        # 4. 定義をその場で見る(Alt+F12)と、定義へ移動(F12)。
        call_line = next(i for i, line in enumerate(lines) if 'joints = builder.build()' in line)
        cursor.setPosition(code.document().findBlockByNumber(call_line).position() + len('    joints = builder.bu'))
        code.setTextCursor(cursor)
        action('Peek definition').trigger()
        wait(300)
        peek = code.findChild(QtWidgets.QFrame, 'peekDefinition')
        assert peek is not None and peek.isVisible(), 'peek not shown'
        peek.grab().save(str(directory / '4-peek.png'))
        save('4-peek-window.png')
        peek.hide()
        action('Go to definition').trigger()
        wait(200)
        assert 'def build' in code.textCursor().block().text(), code.textCursor().block().text()
        probe_line = next(i for i, line in enumerate(lines) if 'make_probe' in line)
        cursor.setPosition(code.document().findBlockByNumber(probe_line).position() + len('    hedit_definition_probe.make_pr'))
        code.setTextCursor(cursor)
        action('Go to definition').trigger()
        wait(300)
        opened = editor()
        assert opened is not code and opened.property('path').endswith('hedit_definition_probe.py'), opened.property('path')
        assert 'def make_probe' in opened.textCursor().block().text()
        assert 'hedit_definition_probe' not in sys.modules  # 実行・importはしない。
        save('4-definition-other-file.png')
        window.findChild(QtWidgets.QTabWidget).setCurrentWidget(code)
        result['checks'].append('peek_and_go_to_definition')

        # 5. 記号へ移動(Ctrl+Shift+O)。
        action('goToSymbol').trigger()
        wait(200)
        pick = window.findChild(QtWidgets.QFrame, 'quickPick')
        assert pick is not None and pick.isVisible()
        listing = pick.findChild(QtWidgets.QListWidget, 'quickPickList')
        labels = [listing.item(i).text() for i in range(listing.count())]
        assert any(label.startswith('ChainBuilder') for label in labels), labels
        pick.findChild(QtWidgets.QLineEdit, 'quickPickInput').setText('orient')
        wait(100)
        save('5-go-to-symbol.png')
        QtTest.QTest.keyClick(pick.findChild(QtWidgets.QLineEdit, 'quickPickInput'), QtCore.Qt.Key_Return)
        wait(100)
        assert 'def orient' in code.textCursor().block().text()
        result['checks'].append('go_to_symbol')

        # 6. アウトライン。
        action('toggleOutline').trigger()
        wait(300)
        tree = window.findChild(QtWidgets.QTreeWidget, 'outline')
        assert tree is not None and tree.topLevelItemCount() >= 2
        save('6-outline.png')
        action('toggleOutline').trigger()
        result['checks'].append('outline')

        # 見出しの固定表示は、画面の外の見出しの行も文字を描く(レイアウトされていない行でも描ける)。
        code.verticalScrollBar().setValue(0)
        wait(100)
        code.verticalScrollBar().setValue(joint_line - 3)
        wait(300)
        assert sticky.isVisible()
        image = sticky.grab().toImage()
        colors = {image.pixel(x, image.height() // 4) for x in range(min(500, image.width()))}
        assert len(colors) > 3, 'sticky scroll text not drawn: %d colors' % len(colors)
        result['checks'].append('sticky_text_drawn')

        # 7. 保存前との差分の画面(モーダルなので、表示されてから撮って閉じる)。
        shots = {}

        def grab_dialog():
            dialog = QtWidgets.QApplication.activeModalWidget()
            if dialog is None:
                QtCore.QTimer.singleShot(100, grab_dialog)
                return
            shots['diff'] = dialog.findChild(QtWidgets.QPlainTextEdit, 'diffView').toPlainText()
            dialog.grab().save(str(directory / '7-compare-with-saved.png'))
            dialog.reject()

        QtCore.QTimer.singleShot(200, grab_dialog)
        action('compareWithSavedAction').trigger()
        assert '+        self.count = count * 2' in shots.get('diff', ''), shots
        result['checks'].append('compare_with_saved')

        # 8. ファイル名で開く(Ctrl+P): 保存したファイルが最近開いたものに出る。
        action('quickOpen').trigger()
        wait(200)
        labels = [listing.item(i).text() for i in range(listing.count())]
        assert any(label.startswith('rig_sample.py') for label in labels), labels
        save('8-quick-open.png')
        QtTest.QTest.keyClick(pick.findChild(QtWidgets.QLineEdit, 'quickPickInput'), QtCore.Qt.Key_Escape)
        result['checks'].append('quick_open_recent')

        # 9. 引数のヒントと補完(キーボードのフォーカスが必要)。
        if focus():
            code.moveCursor(QtGui.QTextCursor.End)
            QtTest.QTest.keyClicks(code, 'builder.build(')
            wait(500)
            help_popup = code.findChild(QtWidgets.QFrame, 'signatureHelp')
            assert help_popup is not None and help_popup.isVisible(), 'signature help not shown'
            help_popup.grab().save(str(directory / '9-signature-help.png'))
            save('9-signature-help-window.png')
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Escape)
            assert not help_popup.isVisible(), 'Esc did not close the signature help'
            # 閉じ括弧は自動で入った ) を上書きする。改行は keyClicks に含めない(QtTest が改行文字を扱えず異常終了する)。
            QtTest.QTest.keyClicks(code, ')')
            assert code.textCursor().block().text().endswith('builder.build()'), code.textCursor().block().text()
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Return)
            QtTest.QTest.keyClicks(code, 'builder.')
            wait(300)
            QtTest.QTest.keyClick(code, QtCore.Qt.Key_Space, QtCore.Qt.ControlModifier)
            wait(600)
            completer = code.findChild(QtWidgets.QCompleter)
            if completer.popup().isVisible():
                completer.popup().grab().save(str(directory / '9-completion.png'))
                detail = code.findChild(QtWidgets.QFrame, 'completionDetail')
                if detail is not None and detail.isVisible():
                    detail.grab().save(str(directory / '9-completion-detail.png'))
                    result['checks'].append('completion_detail')
                completer.popup().hide()
            result['checks'].append('signature_help')
        else:
            result['skipped'].append('signature_help_and_completion (no keyboard focus)')

        # 10. ホバー: Maya の Help → Popup Help がオフでも(Maya が Qt のツールチップを止めても)、マウスを止めると出る。
        popup_mode = cmds.help(query=True, popupMode=True)
        cmds.help(popupMode=False)
        try:
            code.setPlainText('import json\njson.dumps({})')
            wait(200)
            cursor = code.textCursor()
            cursor.setPosition(len('import json\njson.dum'))
            point = code.cursorRect(cursor).center()
            window.activateWindow()
            QtTest.QTest.mouseMove(code.viewport(), point + QtCore.QPoint(40, 0))
            wait(100)
            QtTest.QTest.mouseMove(code.viewport(), point)
            wait(1500)
            hover = code.findChild(QtWidgets.QFrame, 'hoverPopup')
            if QtWidgets.QApplication.activeWindow() is None:
                result['skipped'].append('hover_without_popup_help (window not active)')
            else:
                assert hover is not None and hover.isVisible(), 'hover not shown with Popup Help off'
                hover.grab().save(str(directory / '10-hover.png'))
                hover.hide()
                result['checks'].append('hover_without_popup_help')
        finally:
            cmds.help(popupMode=popup_mode)

        for tab in window.findChildren(QtWidgets.QPlainTextEdit, 'codeEditor'):
            tab.document().setModified(False)
        if static.isChecked():
            static.trigger()
        result['status'] = 'passed'
    except Exception:
        result['error'] = traceback.format_exc()
    (directory / 'result.json').write_text(json.dumps(result), encoding='utf-8')
    finished(result)
