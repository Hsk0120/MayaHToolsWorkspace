"""Finder寄りの選択・メニュー・スクロールを専用GUIで検証して録画する。"""
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpe_ui_maya import pause, waitFor, selectFile
from qpe_ui_navigation import columns, click
from qpeQt import QtCore, QtGui, QtWidgets, QtTest


def main(output_dir, finished=None):
    """専用フォルダーで入力とメニュー取消を検証する。

    Args:
        output_dir (Path): 証跡先。
        finished (callable | None): 専用Maya終了通知。

    Returns:
        dict: 判定結果。
    """
    folder = Path(output_dir).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(folder / 'settings.json')
    root = folder / 'Project'
    deep = root / 'Assets/Characters/Hero/Rig/Work/Version/Review/Publish'
    deep.mkdir(parents=True)
    (root / 'VeryLongFolderName_ForReadableFinderColumns').mkdir()
    for i in range(100):
        (root / ('Folder_%03d' % i)).mkdir()
        (root / ('note_%03d.txt' % i)).write_text('Preview file %03d' % i, encoding='utf-8')
    if finished:
        import qpeHost
        from maya import cmds
        widget = qpeHost.show(str(root))
        cmds.workspaceControl(qpeHost.CONTROL, edit=True, resizeWidth=1280, resizeHeight=940)
    else:
        from quickPathExplorer import Explorer
        widget = Explorer()
        widget.show()
        widget.navigate(str(root))
    caption = QtWidgets.QLabel(widget)
    caption.setStyleSheet('background:#17363b;color:#d5ffff;padding:10px;font-size:16px;')
    widget.layout().insertWidget(0, caption)
    checks, frames, errors = [], [], []
    recording = bool(os.environ.get('QPE_FFMPEG'))
    stage = 'setup'
    frames_dir = folder / 'frames'
    frames_dir.mkdir(exist_ok=True)

    def grab():
        """所有するメニューも含めて実描画を取得する。

        Returns:
            QPixmap: キャプチャ。
        """
        pixmap = widget.grab()
        painter = QtGui.QPainter(pixmap)
        for window in QtWidgets.QApplication.topLevelWidgets():
            owner = window.parentWidget()
            while owner is not None and owner is not widget:
                owner = owner.parentWidget()
            if owner is widget and window.isVisible() and window is not widget:
                painter.drawPixmap(widget.mapFromGlobal(window.mapToGlobal(QtCore.QPoint())), window.grab())
        painter.end()
        return pixmap

    def capture():
        """録画フレームを保存する。"""
        grab().save(str(frames_dir / ('%05d.png' % len(frames))))
        frames.append({'frame': len(frames), 'stage': stage})

    timer = QtCore.QTimer(widget)
    timer.setInterval(100)
    timer.timeout.connect(capture)

    def step(title):
        """次の操作の目的を表示する。

        Args:
            title (str): 字幕。
        """
        nonlocal stage
        stage = title
        caption.setText('QuickPathExplorer | ' + title)
        pause(1200 if recording else 70)

    def screenshot(name):
        """確認用静止画を保存する。

        Args:
            name (str): ファイル名。
        """
        pause(600 if recording else 80)
        grab().save(str(folder / name))

    def menuAt(view, point, verify):
        """実コンテキストイベントでメニューを出し、Escで閉じる。

        Args:
            view (QAbstractItemView): 一覧。
            point (QPoint): viewport内の位置。
            verify (callable): メニュー表示中の検証。
        """
        def check():
            """ネストしたメニューループ内で検証する。"""
            menu = QtWidgets.QApplication.activePopupWidget()
            try:
                assert isinstance(menu, QtWidgets.QMenu)
                verify(menu)
                grab().save(str(folder / '01-context-selection.png'))
            except Exception:
                errors.append(traceback.format_exc())
            finally:
                if menu:
                    QtTest.QTest.keyClick(menu, QtCore.Qt.Key_Escape)
        QtCore.QTimer.singleShot(1000 if recording else 100, check)
        event = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, point, view.viewport().mapToGlobal(point))
        QtWidgets.QApplication.sendEvent(view.viewport(), event)
        assert not errors, errors

    def wheel(view, pixel, angle=QtCore.QPoint(), modifiers=QtCore.Qt.NoModifier):
        """マウスまたは精密スクロール入力を送る。

        Args:
            view (QAbstractItemView): 対象。
            pixel (QPoint): ピクセル差分。
            angle (QPoint): ホイール差分。
            modifiers (Qt.KeyboardModifiers): 修飾キー。
        """
        point = view.viewport().rect().center()
        event = QtGui.QWheelEvent(QtCore.QPointF(point), QtCore.QPointF(view.viewport().mapToGlobal(point)),
            pixel, angle, QtCore.Qt.NoButton, modifiers, QtCore.Qt.ScrollUpdate, False)
        QtWidgets.QApplication.sendEvent(view.viewport(), event)

    try:
        pause(250)
        widget.setBrowseRoot(str(root))
        widget.window().activateWindow()
        widget.window().raise_()
        if recording:
            timer.start()
        step('01  右クリックしても元の選択とプレビューを保持')
        selectFile(widget, root / 'note_000.txt')
        waitFor(lambda: widget.previewText.toPlainText() == 'Preview file 000')
        original = widget.selectedPath()
        target = widget.fileProxy.mapFromSource(widget.fileModel.index(str(root / 'note_001.txt')))
        point = widget.files.visualRect(target).center()
        QtTest.QTest.mousePress(widget.files.viewport(), QtCore.Qt.RightButton, QtCore.Qt.NoModifier, point)
        QtTest.QTest.mouseRelease(widget.files.viewport(), QtCore.Qt.RightButton, QtCore.Qt.NoModifier, point)
        assert widget.selectedPath() == original
        def verify(menu):
            """選択と右クリック対象が別であることを確認する。

            Args:
                menu (QMenu): 表示中メニュー。
            """
            assert widget.selectedPath() == original
            assert widget.previewText.toPlainText() == 'Preview file 000'
            assert widget.files.viewport().findChild(QtWidgets.QFrame, 'contextTargetOutline').isVisible()
        menuAt(widget.files, point, verify)
        assert widget.selectedPath() == original
        checks.append('right press/context/Escape preserve selection and preview, target outlined')

        step('02  メニューの操作対象と複数選択を確認')
        received = []
        def receive(action):
            """ホストへ渡す対象を検査する。

            Args:
                action (str): 操作。
            """
            received.append((action, widget.operationPaths()))
        widget.actionRequested.connect(receive)
        menu = widget.createFileMenu([str(root / 'note_001.txt')])
        # Openはホストで実行せずCopy Pathで固定対象を検証する。
        next(a for a in menu.actions() if a.text() == 'Copy Path').trigger()
        assert QtWidgets.QApplication.clipboard().text() == str(root / 'note_001.txt')
        widget.requestFiles('test-target', [str(root / 'note_001.txt')])
        assert received[-1][1] == [str(root / 'note_001.txt')]
        menu.deleteLater()
        QtTest.QTest.mouseClick(widget.files.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.ControlModifier, point)
        assert len(widget.selectedPaths()) == 2
        widget.files.setFocus()
        QtTest.QTest.keyClick(widget.files, QtCore.Qt.Key_Return)
        assert widget._inlineRename is None
        pause(700 if recording else 20)
        menu = widget.createFileMenu()
        assert not next(a for a in menu.actions() if a.text() == 'Open').isEnabled()
        menu.deleteLater()
        blank = widget.createFileMenu([])
        assert not any(a.text() in ('Open', 'Rename…', 'Import', 'Reference') for a in blank.actions())
        blank.deleteLater()
        blank = widget.createFolderMenu(str(root), background=True)
        assert not any(a.text() == 'Rename…' for a in blank.actions())
        blank.deleteLater()
        checks.append('explicit targets, Ctrl multi selection and background menus')

        step('03  縦スクロールは対象の列だけ — 選択を変えない')
        view = columns(widget)[0]
        selected = widget.selectedPaths()
        wheel(view, QtCore.QPoint(0, -120))
        pause(650 if recording else 20)
        assert view.verticalScrollBar().value() == 120
        assert widget.selectedPaths() == selected
        assert widget.files.verticalScrollBar().value() == 0
        view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
        before = widget.columns.horizontalScrollBar().value()
        wheel(view, QtCore.QPoint(0, -120))
        assert widget.columns.horizontalScrollBar().value() == before
        wheel(widget.files, QtCore.QPoint(), QtCore.QPoint(0, -120))
        assert widget.files.verticalScrollBar().value() > 0
        checks.append('pixel wheel, notch wheel and end stop do not alter selection or adjacent columns')

        step('04  名前に合わせる列幅と境界ドラッグ')
        widget.navigate(str(deep))
        widget.columns.setWidthMode('names')
        widget.columns.horizontalScrollBar().setValue(0)
        pause(120)
        view = columns(widget)[0]
        expected = widget.columns.contentWidth(view.rootIndex())
        assert view.width() == expected, (view.width(), expected)
        point = QtCore.QPoint(view.viewport().width() - 2, 80)
        QtTest.QTest.mousePress(view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, point)
        assert widget.interaction.drag is not None
        QtTest.QTest.mouseMove(view.viewport(), point + QtCore.QPoint(75, 0))
        pause(80)
        QtTest.QTest.mouseRelease(view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, point + QtCore.QPoint(75, 0))
        assert view.width() > expected, (view.width(), expected, widget.columns._manualWidths, widget.interaction.drag)
        pause(650 if recording else 20)
        point = QtCore.QPoint(view.viewport().width() - 2, 80)
        QtTest.QTest.mouseDClick(view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, point)
        assert view.width() == expected
        screenshot('02-name-widths.png')
        checks.append('content widths, boundary drag and double click reset')
        widget.files.setFocus()
        widget.interaction.updateFocus()
        assert all(v.property('qpeSelectionColor') == '#50565b' for v in columns(widget))
        checks.append('ancestor highlights are muted when the file pane has focus')

        step('05  横に戻した位置を読込完了で引き戻さない')
        widget.resize(820, 790)
        pause(100)
        bar = widget.columns.horizontalScrollBar()
        assert bar.maximum() > 0
        bar.setValue(bar.maximum())
        view = columns(widget)[-1]
        wheel(view, QtCore.QPoint(120, 0))
        assert bar.value() < bar.maximum()
        position = bar.value()
        widget.columns.folderLoaded(str(deep))
        pause(100)
        assert bar.value() == position
        checks.append('horizontal wheel and async completion preserve manual position')

        step('06  Returnで改名・Spaceでプレビュー・Escで戻る')
        widget.navigate(str(root))
        pause(100)
        assert len(columns(widget)) == 1, [widget.folderModel.filePath(v.rootIndex()) for v in columns(widget)]
        checks.append('return to scope root removes stale descendant columns')
        selectFile(widget, root / 'note_000.txt')
        widget.files.setFocus()
        pause(80)
        QtTest.QTest.keyClick(widget.files, QtCore.Qt.Key_Return)
        assert widget._inlineRename.isVisible()
        assert widget._inlineRename.selectedText() == 'note_000'
        QtTest.QTest.keyClick(widget._inlineRename, QtCore.Qt.Key_Escape)
        widget.files.setFocus()
        waitFor(lambda: widget.previewText.toPlainText() == 'Preview file 000')
        QtTest.QTest.keyClick(widget.files, QtCore.Qt.Key_Space)
        assert widget._quickLook.isVisible()
        screenshot('03-quick-look.png')
        QtTest.QTest.keyClick(widget._quickLook, QtCore.Qt.Key_Escape)
        assert not widget._quickLook.isVisible()
        assert (root / 'note_000.txt').exists()
        checks.append('Return rename, Escape cancel and Space Quick Look')
        if finished:
            step('07  複数Import／Reference — 対象確認とキャンセル')
            sources = []
            for suffix in ('A', 'B'):
                cmds.file(new=True, force=True)
                cmds.polyCube(name='finder_' + suffix)
                path = str(root / ('source_' + suffix + '.ma'))
                cmds.file(path, exportSelected=True, type='mayaAscii', force=True)
                sources.append(path)
            cmds.file(new=True, force=True)
            def answer(button):
                """実確認ダイアログに回答する。

                Args:
                    button (QMessageBox.StandardButton): 押すボタン。
                """
                def respond():
                    """モーダル画面の対象一覧を確認して回答する。"""
                    dialog = QtWidgets.QApplication.activeModalWidget()
                    if not isinstance(dialog, QtWidgets.QMessageBox):
                        errors.append('missing batch confirmation')
                        return
                    if not all(path in dialog.text() for path in sources):
                        errors.append('batch targets not visible')
                    dialog.button(button).click()
                QtCore.QTimer.singleShot(500 if recording else 80, respond)
            answer(QtWidgets.QMessageBox.Cancel)
            widget.requestFiles('import', sources)
            assert not cmds.objExists('finder_A')
            answer(QtWidgets.QMessageBox.Ok)
            widget.requestFiles('import', sources)
            assert cmds.objExists('finder_A') and cmds.objExists('finder_B')
            cmds.file(new=True, force=True)
            answer(QtWidgets.QMessageBox.Ok)
            widget.requestFiles('reference', sources)
            refs = [value for value in cmds.ls(type='reference') if value != 'sharedReferenceNode']
            assert len(refs) == 2, refs
            assert not errors, errors
            checks.append('actual batch Import/Reference and confirmation Cancel in isolated Maya')
        widget.columns.setWidthMode('fit')
        widget.resize(1240, 790)
        screenshot('04-final.png')
        result = {'status': 'passed', 'checks': checks}
    except Exception:
        result = {'status': 'error', 'stage': stage, 'checks': checks, 'error': traceback.format_exc()}
        grab().save(str(folder / 'failure.png'))
    timer.stop()
    if recording and frames:
        video = folder / 'QuickPathExplorer-Finder-review.mp4'
        with (folder / 'encode.log').open('w') as log:
            subprocess.run([os.environ['QPE_FFMPEG'], '-y', '-framerate', '10', '-i', str(frames_dir / '%05d.png'),
                '-vf', 'scale=1280:940:force_original_aspect_ratio=decrease,pad=1280:940:(ow-iw)/2:(oh-ih)/2,setsar=1',
                '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(video)],
                stdout=log, stderr=subprocess.STDOUT, check=True)
        result.update(video=str(video), frames=len(frames), seconds=len(frames) / 10)
        (folder / 'frames.json').write_text(json.dumps(frames, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(Path(sys.argv[1]))
    sys.exit(0 if result['status'] == 'passed' else 1)
