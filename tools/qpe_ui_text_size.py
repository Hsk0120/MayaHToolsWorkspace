"""文字サイズUI・キー入力の1回処理・ホストとの入力境界を検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback

from qpe_ui_maya import pause, waitFor
from qpeQt import QAction, QtCore, QtGui, QtWidgets, QtTest


def main(output_dir, finished=None):
    """専用データを使い、Qtキー配送とMaya内の表示を確認する。"""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    root = out / 'Folders'
    (root / 'Child').mkdir(parents=True, exist_ok=True)
    (root / 'notes.txt').write_text('Text size test', encoding='utf8')
    app = QtWidgets.QApplication.instance()
    original_font = QtGui.QFont(app.font())
    checks = []
    recorder = None
    e = None
    outside = None
    try:
        if finished:
            import qpeHost
            e = qpeHost.show(str(root))
        else:
            from quickPathExplorer import Explorer
            e = Explorer(dpi_scale=1.25)
            e.show()
            e.navigate(str(root))
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 1)
        a = e.appearance
        if os.environ.get('QPE_FFMPEG'):
            from qpe_record_full import Recorder
            recorder = Recorder(e, out)

        def stage(code, description):
            """Qt操作による実画面をスクリーンショットと任意の動画へ残す。"""
            pause(120)
            if recorder:
                recorder.step(code, description)
                recorder.hold()
            e.grab().save(str(out / (code + '.png')))

        a.show()
        assert a.fontSpin.isVisible()
        a.presetCombo.setCurrentIndex(a.presetCombo.findText('Very Small'))
        a.presetCombo.activated.emit(a.presetCombo.currentIndex())
        assert (a.fontSize, a.uiPercent) == (10, 100)
        assert a.fontSpin.value() == 10
        assert e.files.font().pixelSize() == round(10 * a.dpiScale)
        from qpeSettings import readSettings
        assert readSettings()[a.key]['fontSize'] == 10
        a.dialog.hide()
        a.show()
        assert a.presetCombo.currentText() == 'Very Small'
        a.dialog.grab().save(str(out / 'settings-very-small.png'))
        stage('00-very-small', 'Qt test: Very Small preset / 10 px before host DPI')
        checks.append('Very Small selects 10px at 100% UI, persists and reopens with matching preset')
        assert a.presetCombo.findText('Smaller') >= 0
        a.presetCombo.setCurrentIndex(a.presetCombo.findText('Smaller'))
        a.presetCombo.activated.emit(a.presetCombo.currentIndex())
        assert (a.fontSize, a.uiPercent) == (11, 100)
        assert e.files.font().pixelSize() == round(11 * a.dpiScale)
        a.dialog.grab().save(str(out / 'settings-smaller.png'))
        stage('01-smaller', 'Qt test: Smaller preset / visible font size')
        a.fontSpin.setValue(10)
        assert a.fontSize == 10 and a.presetCombo.currentText() == 'Very Small'
        a.setPreset(0)
        assert a.fontSpin.value() == 12 and a.presetCombo.currentText() == 'Standard'
        a.dialog.hide()
        checks.append('Smaller preset, visible numeric control, live render and reset synchronization')

        def focus(view):
            """ホスト内でも対象一覧を前面化し、フォーカス取得を確認する。"""
            e.window().raise_()
            e.window().activateWindow()
            QtWidgets.QApplication.setActiveWindow(e.window())
            view.setFocus()
            waitFor(lambda: app.focusWidget() is view)

        host_calls = []
        for sequence in ('Ctrl+-', 'Ctrl++', 'Ctrl+=', 'Ctrl+0'):
            action = QAction(e.window())
            action.setShortcut(QtGui.QKeySequence(sequence))
            action.setShortcutContext(QtCore.Qt.WindowShortcut)
            action.triggered.connect(lambda checked=False, key=sequence: host_calls.append(key))
            e.window().addAction(action)
        focus(e.files)
        ctrl = QtCore.Qt.ControlModifier
        for key, mods, expected in [(QtCore.Qt.Key_Minus, ctrl, 11),
                                    (QtCore.Qt.Key_Plus, ctrl, 12),
                                    (QtCore.Qt.Key_Equal, ctrl, 13),
                                    (QtCore.Qt.Key_Plus, ctrl | QtCore.Qt.ShiftModifier, 14),
                                    (QtCore.Qt.Key_Minus, ctrl | QtCore.Qt.KeypadModifier, 13),
                                    (QtCore.Qt.Key_Plus, ctrl | QtCore.Qt.KeypadModifier, 14),
                                    (QtCore.Qt.Key_0, ctrl, 12)]:
            QtTest.QTest.keyClick(e.files, key, mods)
            assert a.fontSize == expected, (key, mods, a.fontSize, expected)
        assert not host_calls, host_calls
        checks.append('Ctrl minus/plus/equal, shifted plus, numpad and reset each run once before host shortcuts')
        stage('02-shortcuts', 'Qt test: Ctrl +/- and Ctrl 0')
        a.show()
        a.dialog.hide()
        focus(e.files)
        a.apply(11, 125)
        QtTest.QTest.keyClick(e.files, QtCore.Qt.Key_Minus, ctrl)
        assert (a.fontSize, a.uiPercent, a.fontSpin.value(), a.scaleSpin.value()) == (10, 125, 10, 125)
        QtTest.QTest.keyClick(e.files, QtCore.Qt.Key_Minus, ctrl)
        assert a.fontSize == 10
        a.apply(24, 125)
        QtTest.QTest.keyClick(e.files, QtCore.Qt.Key_Plus, ctrl)
        assert a.fontSize == 24
        QtTest.QTest.keyClick(e.files, QtCore.Qt.Key_0, ctrl)
        assert (a.fontSize, a.uiPercent) == (12, 125)
        a.apply(12, 100)
        checks.append('10/24 bounds; shortcuts preserve UI scale and synchronize hidden dialog controls')

        for view in (e.address, e.search):
            focus(view)
            before = a.fontSize
            QtTest.QTest.keyClick(view, QtCore.Qt.Key_Minus, ctrl)
            assert a.fontSize == before
            event = QtGui.QInputMethodEvent('あ', [])
            app.sendEvent(view, event)
            QtTest.QTest.keyClick(view, QtCore.Qt.Key_Plus, ctrl)
            assert a.fontSize == before
            app.sendEvent(view, QtGui.QInputMethodEvent('', []))
        outside = QtWidgets.QLineEdit()
        outside.show()
        outside.activateWindow()
        app.setActiveWindow(outside)
        outside.setFocus()
        waitFor(lambda: app.focusWidget() is outside)
        QtTest.QTest.keyClick(outside, QtCore.Qt.Key_Minus, ctrl)
        assert a.fontSize == 12
        outside.close()
        checks.append('address/search/preedit event and external Qt input never change QPE font')
        e.setSidebarVisible(True)
        pause(100)
        for view in (e.places, e.folderTabs.bar):
            focus(view)
            QtTest.QTest.keyClick(view, QtCore.Qt.Key_Minus, ctrl)
            assert a.fontSize == 11
            QtTest.QTest.keyClick(view, QtCore.Qt.Key_0, ctrl)
        e.navigate(str(root / 'Child'))
        pause(300)
        views = [v for v in e.columns.findChildren(QtWidgets.QListView) if v.isVisible()]
        assert views
        focus(views[-1])
        QtTest.QTest.keyClick(views[-1], QtCore.Qt.Key_Minus, ctrl)
        assert a.fontSize == 11
        stage('03-columns', 'Qt test: folder column / smaller text')
        e.navigate(str(root))
        for mode in (1, 2):
            e.organizer.workspace.mode.setCurrentIndex(mode)
            view = e.organizer.workspace.grid if mode == 1 else e.organizer.workspace.tree
            pause(150)
            a.apply(12, 100)
            focus(view)
            QtTest.QTest.keyClick(view, QtCore.Qt.Key_Minus, ctrl)
            assert a.fontSize == 11
        e.organizer.workspace.mode.setCurrentIndex(0)
        checks.append('sidebar, tabs, dynamic folder columns, grid and tree accept local zoom')
        from qpeSettings import readSettings
        assert readSettings()[a.key]['fontSize'] == 11
        assert app.font() == original_font
        a.show()
        assert a.fontSpin.value() == 11 and a.presetCombo.currentText() == 'Smaller'
        a.dialog.grab().save(str(out / 'settings-final.png'))
        stage('04-saved', 'Qt test: settings saved, host font unchanged')
        checks.append('settings persisted and dialog reopened consistently; application font unchanged')
        result = dict(status='passed', checks=checks, evidence='Qt program input; IME preedit simulated, not physical IME typing')
        if recorder:
            result['video'] = recorder.finish()
    except Exception:
        if recorder:
            recorder.timer.stop()
        result = dict(status='error', checks=checks, error=traceback.format_exc())
    finally:
        if outside:
            outside.close()
        if e:
            if e.appearance.dialog:
                e.appearance.dialog.hide()
            e.close()
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    sys.exit(0 if main(sys.argv[1])['status'] == 'passed' else 1)
