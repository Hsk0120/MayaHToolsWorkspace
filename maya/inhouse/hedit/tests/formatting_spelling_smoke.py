"""Output改行・表示設定・Windows辞書の波線を専用GUIで検証する。"""
import json
from pathlib import Path
import sys
import traceback
import time


def main(output_dir, finished):
    from maya import cmds, OpenMaya
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        Action = QtGui.QAction
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
        Action = QtWidgets.QAction
    def wait(ms=700):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, loop.quit)
        (loop.exec if hasattr(loop, 'exec') else loop.exec_)()
    result = {'status': 'error', 'checks': []}
    directory = Path(output_dir)
    try:
        sys.stdout.write('startup_crlf_A\r\nstartup_crlf_B\r\n')
        print('startup_optimization', 'on')
        print('startup_line_A')
        print('startup_line_B')
        import hedit
        host = hedit.show(); window = host.editor
        output = window.findChild(QtWidgets.QPlainTextEdit, 'output')
        code = window.findChild(QtWidgets.QPlainTextEdit, 'codeEditor')
        wait()
        (directory / 'initial-output.txt').write_text(output.toPlainText(), encoding='utf-8')
        assert 'startup_optimization on\nstartup_line_A\nstartup_line_B\n' in output.toPlainText(), repr(output.toPlainText())
        assert 'startup_crlf_A\nstartup_crlf_B\n' in output.toPlainText(), repr(output.toPlainText())
        assert '?' not in host.windowTitle() and '?' not in window.windowTitle()
        assert output.lineWrapMode() == QtWidgets.QPlainTextEdit.NoWrap
        assert output.font().pixelSize() == code.font().pixelSize()-2
        output.verticalScrollBar().setValue(0)
        window.grab().save(str(directory / 'initial-output.png'))
        actions = window.findChildren(Action)
        next(a for a in actions if a.text() == 'Clear output').trigger()
        print('PLUGIN_ENABLE_CACHING optimization', 'on')
        sys.stdout.write('split_'); sys.stdout.write('stream'); sys.stdout.write('\n')
        print('blank_before\n\nblank_after')
        wait(120)
        text = output.toPlainText()
        assert 'PLUGIN_ENABLE_CACHING optimization on\n' in text, repr(text)
        assert 'split_stream\n' in text, repr(text)
        assert 'blank_before\n\nblank_after' in text, repr(text)
        result['checks'].append('crlf_fragments_intentional_blank_lines_font_title_nowrap')
        toggle = next(a for a in actions if a.objectName() == 'option_spellCheck')
        assert toggle.isChecked(), 'Spell check should default to ON'
        code.setPlainText('# This commment contains misspelled wrds.\ncorrectVariable = "hello world"\nhlib.node("maya")\nmispelledValue = 1\n')
        code.setFocus(); wait()
        assert code.property('spellCheckAvailable'), 'English Windows dictionary unavailable'
        words = [s.cursor.selectedText() for s in code.extraSelections()
                 if s.format.underlineStyle() == QtGui.QTextCharFormat.WaveUnderline]
        assert 'commment' in words and 'mispelled' in words, words
        assert 'hlib' not in words and 'hello' not in words and 'correct' not in words, words
        result['spell_ms'] = code.property('spellCheckMilliseconds')
        toggle.setChecked(False)
        assert not any(s.format.underlineStyle() == QtGui.QTextCharFormat.WaveUnderline for s in code.extraSelections())
        old = code.property('spellCheckMilliseconds'); code.insertPlainText(' # anotherr'); wait()
        assert code.property('spellCheckMilliseconds') == old
        toggle.setChecked(True); wait()
        assert any(s.format.underlineStyle() == QtGui.QTextCharFormat.WaveUnderline for s in code.extraSelections())
        result['checks'].append('spell_default_on_camelcase_wave_off_on')
        window.grab().save(str(directory / 'output-spelling.png'))
        # 遅いパス走査を注入しても、GUIのイベント処理が止まらないことを確認する。
        from hedit import bridge
        from hedit.completion import Index
        saved_index = bridge._index
        slow = Index([], async_scan=True)
        def slow_scan(paths, modules):
            time.sleep(.8)
        slow._scan_top = slow_scan
        bridge._index = slow
        beats = []
        timer = QtCore.QTimer(); timer.setInterval(20)
        timer.timeout.connect(lambda: beats.append(time.perf_counter()))
        toggle.setChecked(False)
        try:
            code.setPlainText('import ma'); code.moveCursor(QtGui.QTextCursor.End)
            code.setFocus(); timer.start()
            QtCore.QTimer.singleShot(100, lambda: bridge.complete('import ma'))
            wait(1300)
            assert slow.scan_thread is not None, 'Import completion not requested'
            assert len(beats)>20, len(beats)
            gaps = [b-a for a,b in zip(beats,beats[1:])]
            result['gui_max_timer_gap_ms'] = round(max(gaps)*1000, 2)
            assert max(gaps)<.3, gaps
            result['checks'].append('slow_import_scan_keeps_gui_responsive')
        finally:
            timer.stop(); bridge._index = saved_index
        code.document().setModified(False); window.close(); cmds.unloadPlugin('hedit')
        result['status'] = 'passed'
    except Exception:
        result['error'] = traceback.format_exc()
    (directory / 'result.json').write_text(json.dumps(result), encoding='utf-8')
    finished(result)
