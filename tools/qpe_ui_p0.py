"""Finder引継ぎP0の回帰を隔離GUIで検証し、未実施も明示する。"""
import json
import os
import platform
import subprocess
import sys
import traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpe_ui_maya import pause, waitFor, selectFile
from qpe_ui_navigation import columns, click, inspectFolder
from qpeQt import QtCore, QtGui, QtWidgets, QtTest


def main(output_dir, finished=None):
    """専用データ・実ウィジェットでケースごとの証跡を保存する。

    Args:
        output_dir (Path): 保存先。
        finished (callable | None): 専用Mayaランナーの完了通知。

    Returns:
        dict: 自動検証と実機未実施の区別を含む結果。
    """
    folder = Path(output_dir).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(folder / 'settings.json')
    root = folder / 'Fixture'
    root.mkdir()
    for name in ('A', 'B', 'Empty'):
        (root / name).mkdir()
    (root / 'A/Child-A.txt').write_text('A', encoding='utf-8')
    (root / 'B/Child-B.txt').write_text('B', encoding='utf-8')
    for i in range(65):
        (root / ('Item%02d' % i)).mkdir()
        (root / 'A' / ('Sub%02d' % i)).mkdir()
        (root / ('File%02d.txt' % i)).write_text('text-%02d' % i, encoding='utf-8')
    deep = root / 'A/Deep/Two/Three/Four/Five/Six'
    deep.mkdir(parents=True)
    (deep / 'note.txt').write_text('deep preview', encoding='utf-8')
    if finished:
        import qpeHost
        from maya import cmds
        widget = qpeHost.show(str(root))
        if os.environ.get('QPE_TEST_DOCK'):
            cmds.workspaceControl(qpeHost.CONTROL, edit=True, dockToMainWindow=['right', False])
    else:
        from quickPathExplorer import Explorer
        widget = Explorer()
        widget.show()
    widget.setBrowseRoot(str(root))
    widget.window().activateWindow()
    widget.raise_()
    pause(200)
    logs, cases = [], {}
    widget.traceSink = logs.append
    frames = []
    recording = bool(os.environ.get('QPE_FFMPEG'))
    caption = QtWidgets.QLabel('QuickPathExplorer | P0 acceptance', widget)
    caption.setStyleSheet('background:#17363b;color:white;padding:8px;font-size:16px;')
    widget.layout().insertWidget(0, caption)
    frames_dir = folder / 'frames'
    if recording:
        frames_dir.mkdir()
    def capture():
        """所有するポップアップを重ね、実描画を録画する。"""
        pixmap = widget.grab()
        painter = QtGui.QPainter(pixmap)
        popup = QtWidgets.QApplication.activePopupWidget()
        owner = popup.parentWidget() if popup is not None else None
        while owner is not None and owner is not widget:
            owner = owner.parentWidget()
        if popup is not None and owner is widget:
            painter.drawPixmap(widget.mapFromGlobal(popup.mapToGlobal(QtCore.QPoint())), popup.grab())
        painter.end()
        pixmap.save(str(frames_dir / ('%05d.png' % len(frames))))
        frames.append(caption.text())
    record_timer = QtCore.QTimer(widget)
    record_timer.setInterval(100)
    record_timer.timeout.connect(capture)
    if recording:
        record_timer.start()

    def check(case, callback, scope='自動・Qt実ウィジェット'):
        """失敗を記録して他ケースも実行する。

        Args:
            case (str): ケースID。
            callback (callable): 検証。
            scope (str): 確認範囲。
        """
        try:
            caption.setText('QuickPathExplorer | ' + case + ' | ' + (callback.__doc__ or '').split('\n')[0])
            pause(300 if recording else 1)
            callback()
            cases[case] = dict(status='passed', scope=scope)
        except Exception:
            cases[case] = dict(status='failed', scope=scope, error=traceback.format_exc())
        widget.grab().save(str(folder / (case + '.png')))

    def at01():
        """兄弟の切替で古い子一覧が残らない。"""
        click(widget, root / 'A')
        click(widget, root / 'B')
        widget.navigate(str(root))
        inspectFolder(widget, root)
        selectFile(widget, root / 'File00.txt')
        waitFor(lambda: widget.previewText.toPlainText() == 'text-00')
    check('AT01', at01)

    def menuTest(folder_item=False, multiple=False, background=False, execute=False, outside=False, unselected=False):
        """本番メニュー入口へイベントを送り、選択と固定対象を検証する。

        Args:
            folder_item (bool): フォルダーカラムか。
            multiple (bool): 複数選択か。
            background (bool): 空白か。
            execute (bool): 情報コマンドを実行するか。
            outside (bool): 別項目行をクリックして閉じるか。
            unselected (bool): 複数選択の外側を対象にするか。
        """
        widget.navigate(str(root / 'A') if folder_item else str(root))
        pause(100)
        if folder_item:
            view = next(v for v in columns(widget) if Path(widget.folderModel.filePath(v.rootIndex())) == root)
            index = widget.folderModel.index(str(root / 'B'))
        else:
            selectFile(widget, root / 'File00.txt')
            view = widget.files
            index = widget.fileProxy.mapFromSource(widget.fileModel.index(str(root / 'File01.txt')))
            if multiple:
                view.selectionModel().select(index, QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
                if unselected:
                    index = widget.fileProxy.mapFromSource(widget.fileModel.index(str(root / 'File02.txt')))
        old_paths = widget.selectedPaths()
        old_dir = widget.currentDirectory
        point = view.visualRect(index).center()
        old_preview = widget._previewSerial
        received, errors = [], []
        old_info = widget.showTargetInfo
        widget.showTargetInfo = lambda paths: received.extend(paths)
        def inspect():
            """メニューのネストしたイベントループ内で確認する。"""
            menu = QtWidgets.QApplication.activePopupWidget()
            try:
                assert menu is not None
                assert widget.selectedPaths() == old_paths
                assert widget.currentDirectory == old_dir
                assert widget._previewSerial == old_preview
                if recording:
                    capture()
                if not background:
                    outlines = view.viewport().findChildren(QtWidgets.QFrame, 'contextTargetOutline')
                    assert sum(outline.isVisible() for outline in outlines) == 1
                if execute:
                    next(a for a in menu.actions() if 'Information' in a.text()).trigger()
                if outside:
                    # Qtポップアップが受け取る、メニュー外の一覧行の座標。
                    outside_point = QtCore.QPoint(-25, -25)
                    QtTest.QTest.mouseClick(menu, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, outside_point)
                else:
                    QtTest.QTest.keyClick(menu, QtCore.Qt.Key_Escape)
            except Exception:
                errors.append(traceback.format_exc())
                if menu:
                    menu.close()
            if menu and menu.isVisible():
                menu.close()
        QtCore.QTimer.singleShot(600 if recording else 80, inspect)
        try:
            if background:
                menu = widget.createFileMenu([])
                widget._execContext(menu, view.viewport().mapToGlobal(QtCore.QPoint(180, 50)), view)
            else:
                event = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, point, view.viewport().mapToGlobal(point))
                QtWidgets.QApplication.sendEvent(view.viewport(), event)
        finally:
            widget.showTargetInfo = old_info
        assert not errors, errors
        assert widget.selectedPaths() == old_paths
        assert widget.currentDirectory == old_dir
        if execute:
            expected = [str(root)] if background else ([str(root / 'B')] if folder_item else old_paths if multiple else [str(root / 'File01.txt')])
            assert [Path(p) for p in received] == [Path(p) for p in expected], received
        if outside:
            QtTest.QTest.mouseClick(view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, point)
            assert Path(widget.selectedPath()) == root / 'File01.txt'
    check('AT02', lambda: menuTest(folder_item=True))
    check('AT03', lambda: menuTest(multiple=True, unselected=True))
    check('AT04', lambda: menuTest(folder_item=True, execute=True))
    check('AT05', lambda: menuTest(multiple=True, execute=True))
    check('AT06', lambda: menuTest(multiple=True, background=True, execute=True))
    check('AT07', lambda: menuTest(outside=True), 'Qtポップアップ外側座標と次クリック。OS配送は別途実機確認')

    def at08():
        """メニュー作成後に消失した対象を他項目へ転送しない。"""
        missing = root / 'missing.txt'
        missing.write_text('temporary', encoding='utf-8')
        menu = widget.createFileMenu([str(missing)])
        missing.unlink()
        received = []
        def receive(action):
            """誤配送を検出する。

            Args:
                action (str): 要求。
            """
            received.append(action)
        widget.actionRequested.connect(receive)
        next(a for a in menu.actions() if a.text() == 'Open').trigger()
        widget.actionRequested.disconnect(receive)
        assert not received
        assert 'missing' in widget.status.text()
        menu.deleteLater()
    check('AT08', at08)

    import quickPathExplorer as implementation
    original_job = implementation.PreviewJob
    from qpePreview import PreviewSignals
    pending = []
    class ControlledJob(QtCore.QRunnable):
        """本番要求入口を保ち、完了順だけをテストで制御する。"""
        def __init__(self, serial, path):
            """要求を保持する。

            Args:
                serial (int): 世代。
                path (str): 対象。
            """
            super().__init__()
            self.serial, self.path = serial, path
            self.signals = PreviewSignals()
            pending.append(self)
        def run(self):
            """ワーカは待たず終了し、GUIテスト側で結果を注入する。"""

    def select(number):
        """新しいプレビュー要求を取得する。

        Args:
            number (int): テスト項目番号。

        Returns:
            ControlledJob: 要求。
        """
        selectFile(widget, root / ('File%02d.txt' % number))
        return pending[-1]

    def complete(job, text):
        """本番シグナルを通して成功・失敗を配送する。

        Args:
            job (ControlledJob): 要求。
            text (str): TEXT接頭辞なら成功、その他は失敗等。
        """
        job.signals.ready.emit(job.serial, QtGui.QImage(), text)
        pause(5)

    implementation.PreviewJob = ControlledJob
    widget.navigate(str(root))
    def at09():
        """旧成功の遅延完了を排除する。"""
        a, b = select(0), select(1)
        QtCore.QTimer.singleShot(200, lambda: complete(b, 'TEXT\nnew-B'))
        QtCore.QTimer.singleShot(1500, lambda: complete(a, 'TEXT\nold-A'))
        pause(1600)
        assert widget.previewText.toPlainText() == 'new-B'
    check('AT09', at09, 'プレビューのみ。Qtディレクトリ列挙の順序注入は未実施')
    def at10():
        """同じパスでも前の世代は採用しない。"""
        a1, b, a2 = select(0), select(1), select(0)
        complete(a2, 'TEXT\nA2')
        complete(b, 'old-B-error')
        complete(a1, 'TEXT\nA1')
        assert widget.previewText.toPlainText() == 'A2'
    check('AT10', at10, 'プレビューのみ。Qtディレクトリ列挙の世代逆転は未実施')
    def at11():
        """古い失敗も最後の選択を上書きしない。"""
        d, e, f = select(3), select(4), select(5)
        complete(f, 'TEXT\nF')
        complete(e, 'old-E-error')
        complete(d, 'old-D-error')
        assert widget.previewText.toPlainText() == 'F'
    check('AT11', at11)
    def at12():
        """100回の選択と非表示後の配送を追跡する。"""
        jobs = []
        for i in range(100):
            jobs.append(select(i % 60))
            pause(50)
        start = len(logs)
        for job in reversed(jobs):
            complete(job, 'TEXT\nserial-%d' % job.serial)
        accepted = [row['serial'] for row in logs[start:] if row['operation'] == 'preview-result' and row['accepted']]
        assert accepted == [jobs[-1].serial], accepted
        assert widget.previewText.toPlainText() == 'serial-%d' % jobs[-1].serial
        delayed = select(61)
        widget.hide()
        before = widget.previewText.toPlainText()
        complete(delayed, 'TEXT\nafter-hide')
        assert widget.previewText.toPlainText() == before
        assert logs[-1]['accepted'] is False
        widget.show()
        # C++側QObject破棄後のシグナルも自動切断されることを確認。
        from quickPathExplorer import Explorer
        disposed = Explorer()
        disposed.show()
        disposed.navigate(str(root))
        selectFile(disposed, root / 'File00.txt')
        job = pending[-1]
        disposed.deleteLater()
        pause(30)
        complete(job, 'TEXT\nafter-delete')
    check('AT12', at12, 'プレビュー100回・hide/delete。ディレクトリ更新ログは未実施')
    implementation.PreviewJob = original_job
    try:
        from qpe_ui_directory import verify
        directory_result = verify(widget, root, pause)
        logs.extend(directory_result.pop('log'))
        for case in ('AT09', 'AT10', 'AT12'):
            if cases[case]['status'] == 'passed':
                cases[case]['scope'] = '一覧・プレビュー両方の逆順／同一パス別世代／終了失効。実行ログ照合'
    except Exception:
        for case in ('AT09', 'AT10', 'AT12'):
            cases[case] = dict(status='failed', scope='directory snapshots', error=traceback.format_exc())

    def wheel(view, dx, dy, notch=False):
        """ポインター下へ実Qtホイールイベントを配送する。

        Args:
            view (QAbstractItemView): 配送先。
            dx (int): 横成分。
            dy (int): 縦成分。
            notch (bool): angleDeltaか。
        """
        point = QtCore.QPoint(40, 40)
        delta = QtCore.QPoint(dx, dy)
        event = QtGui.QWheelEvent(QtCore.QPointF(point), QtCore.QPointF(view.viewport().mapToGlobal(point)),
            QtCore.QPoint() if notch else delta, delta if notch else QtCore.QPoint(),
            QtCore.Qt.NoButton, QtCore.Qt.NoModifier, QtCore.Qt.NoScrollPhase, False)
        QtWidgets.QApplication.sendEvent(view.viewport(), event)

    def at13():
        """縦位置はポインター下の列だけを変更する。"""
        widget.navigate(str(root / 'A'))
        inspectFolder(widget, root / 'A')
        waitFor(lambda: len(columns(widget)) >= 2 and columns(widget)[1].verticalScrollBar().maximum() > 100)
        parent, child = columns(widget)[:2]
        parent.verticalScrollBar().setValue(0)
        child.verticalScrollBar().setValue(0)
        widget.files.setFocus()
        wheel(child, 0, -100)
        assert child.verticalScrollBar().value() == 100
        assert parent.verticalScrollBar().value() == 0
        wheel(parent, 0, -80)
        assert child.verticalScrollBar().value() == 100
        assert parent.verticalScrollBar().value() == 80
    check('AT13', at13)
    def at14():
        """ホイールの境界余剰入力を消費する。"""
        parent, child = columns(widget)[:2]
        old = parent.verticalScrollBar().value()
        for end, delta in ((0, 120), (child.verticalScrollBar().maximum(), -120)):
            child.verticalScrollBar().setValue(end)
            for unused in range(5):
                wheel(child, 0, delta, notch=True)
            assert parent.verticalScrollBar().value() == old
            assert child.verticalScrollBar().value() == end
    check('AT14', at14, 'Qtホイール。物理ホイール／背後のMayaビューは未実施')
    def at15():
        """再描画は手動位置を戻さずキー移動では現在行を可視化する。"""
        view = columns(widget)[0]
        view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
        before = view.verticalScrollBar().value()
        view.viewport().update()
        widget.columns.refreshHints()
        pause(40)
        assert view.verticalScrollBar().value() == before
        view.setFocus()
        QtTest.QTest.keyClick(view, QtCore.Qt.Key_Down)
        pause(40)
        assert view.viewport().rect().intersects(view.visualRect(view.currentIndex()))
    check('AT15', at15)
    def at16():
        """祖先へ戻した横位置は非同期通知や再描画で動かない。"""
        widget.resize(850, widget.height())
        widget.navigate(str(deep))
        widget.columns.setWidthMode('names')
        for view in columns(widget):
            widget.columns.setManualWidth(view.rootIndex(), 220)
        pause(150)
        bar = widget.columns.horizontalScrollBar()
        assert bar.maximum() > 0
        bar.setValue(60)
        anchor = widget.columns.horizontalAnchor()
        implementation.PreviewJob = ControlledJob
        try:
            selectFile(widget, deep / 'note.txt')
        finally:
            implementation.PreviewJob = original_job
        delayed = pending[-1]
        for unused in range(10):
            widget.columns.folderLoaded(str(deep))
            widget.columns.viewport().update()
            if unused == 3:
                complete(delayed, 'TEXT\ndeep preview')
            if unused == 5:
                menu = widget.createFileMenu([])
                QtCore.QTimer.singleShot(30, menu.close)
                widget._execContext(menu, widget.files.mapToGlobal(QtCore.QPoint(80, 40)))
            pause(500)
        assert widget.columns.horizontalAnchor() == anchor
    check('AT16', at16, '5秒の再描画・directoryLoaded・メニュー開閉・遅延プレビュー完了')
    def at17():
        """明示移動で新しい子一覧を可視化する。"""
        widget.navigate(str(root / 'B'))
        inspectFolder(widget, root / 'B')
        before = widget.columns.horizontalScrollBar().value()
        widget.columns.folderLoaded(str(root / 'B'))
        pause(100)
        assert widget.columns.horizontalScrollBar().value() == before
    check('AT17', at17)
    def at18():
        """先行列の幅変更でも同じ基準列とオフセットを保つ。"""
        widget.navigate(str(deep))
        widget.columns.setWidthMode('names')
        pause(120)
        views = columns(widget)
        bar = widget.columns.horizontalScrollBar()
        bar.setValue(views[0].width() + 20)
        anchor = widget.columns.horizontalAnchor()
        widget.columns.setManualWidth(views[0].rootIndex(), views[0].width() + 100)
        assert widget.columns.horizontalAnchor() == anchor, (anchor, widget.columns.horizontalAnchor())
        widget.resize(widget.width() - 100, widget.height())
        pause(50)
        assert widget.columns.horizontalAnchor() == anchor
        # 縦横が両方動ける親列に斜め入力。
        view = views[1]
        view.verticalScrollBar().setValue(0)
        old = bar.value()
        wheel(view, -20, -30)
        assert bar.value() == old + 20
        assert view.verticalScrollBar().value() == 30
        before = bar.value()
        widget.columns.restoreHorizontalAnchor(('Z:/removed/column', 10))
        assert bar.value() == before
    check('AT18', at18)
    def at19():
        """QPE外入力と編集欄への配送で選択・フォーカスを奪わない。"""
        widget.navigate(str(root))
        selectFile(widget, root / 'File00.txt')
        outside = QtWidgets.QLineEdit(widget.window()) if finished else QtWidgets.QLineEdit()
        outside.show()
        outside.activateWindow()
        outside.setFocus()
        pause(60)
        old = widget.selectedPaths()
        for key in (QtCore.Qt.Key_Down, QtCore.Qt.Key_Space, QtCore.Qt.Key_Return):
            QtTest.QTest.keyClick(outside, key)
        pause(100)
        assert widget.selectedPaths() == old
        assert QtWidgets.QApplication.focusWidget() is outside
        outside.close()
        outside.deleteLater()
    check('AT19', at19, '外部Qt入力欄。Maya標準ビュー・実際のキー配送は未実施')
    def at20():
        """合成IMEイベントは一覧操作を起こさない。"""
        widget.window().activateWindow()
        widget.address.setFocus()
        pause(200)
        old = widget.selectedPaths()
        event = QtGui.QInputMethodEvent('にほん', [])
        QtWidgets.QApplication.sendEvent(widget.address, event)
        assert widget.selectedPaths() == old
        assert widget._inlineRename is None
        assert QtWidgets.QApplication.focusWidget() is widget.address
        widget.renamePath(widget.selectedPath())
        editor = widget._inlineRename
        assert editor is not None
        QtWidgets.QApplication.sendEvent(editor, QtGui.QInputMethodEvent('にほん', []))
        for key in (QtCore.Qt.Key_Left, QtCore.Qt.Key_Space, QtCore.Qt.Key_Return, QtCore.Qt.Key_Escape):
            QtTest.QTest.keyClick(editor, key)
            assert not editor._finished
            assert widget.selectedPaths() == old
        QtWidgets.QApplication.sendEvent(editor, QtGui.QInputMethodEvent('', []))
        QtTest.QTest.keyClick(editor, QtCore.Qt.Key_Escape)
    check('AT20', at20, '合成preeditと編集中の矢印・Space・Enter・Escape。日本語IME実入力は未実施')
    cases['AT21'] = dict(status='not_run', scope='別アプリ初回クリック・Mayaビューのホスト配送は手動確認が必要')
    environment = dict(windows=platform.platform(), qt=QtCore.qVersion(), host='Maya' if finished else 'standalone',
                       shape=('docked workspaceControl' if os.environ.get('QPE_TEST_DOCK') else 'floating workspaceControl') if finished else 'window', input='QtTest synthetic',
                       dpi=widget.devicePixelRatioF())
    if finished:
        environment['maya'] = cmds.about(version=True)
    automated_failed = any(c['status'] == 'failed' for c in cases.values())
    # 一部だけの自動検証を受け入れケース全体の合格と混同させない。
    for case in ('AT14', 'AT19', 'AT20'):
        cases[case]['automatedStatus'] = cases[case]['status']
        if cases[case]['status'] == 'passed':
            cases[case]['status'] = 'not_run'
    result = dict(status='failed' if automated_failed else 'passed',
                  acceptance='incomplete', environment=environment, cases=cases)
    record_timer.stop()
    if recording and frames:
        video = folder / 'QuickPathExplorer-P0.mp4'
        # Mayaの標準入力を継承せず、変換が停止してもGUI検証を無期限に待たせない。
        with (folder / 'encode.log').open('w') as log:
            subprocess.run([os.environ['QPE_FFMPEG'], '-nostdin', '-y', '-framerate', '10', '-i', str(frames_dir / '%05d.png'),
                '-vf', 'scale=1280:940:force_original_aspect_ratio=decrease,pad=1280:940:(ow-iw)/2:(oh-ih)/2,setsar=1',
                '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(video)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
        result['video'] = str(video)
        (folder / 'frames.json').write_text(json.dumps(frames, ensure_ascii=False), encoding='utf-8')
    (folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder / 'events.json').write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(Path(sys.argv[1]))
    sys.exit(0 if result['status'] == 'passed' else 1)
