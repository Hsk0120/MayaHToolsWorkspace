"""専用Mayaと専用ファイルで日常操作を章別に録画・検証する。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpe_ui_maya import pause, waitFor, selectFile
from qpeQt import QtCore, QtGui, QtWidgets, QtTest


class Recorder:
    """実ウィジェットと所有ダイアログを実時間の動画にする。"""

    def __init__(self, explorer, output):
        """記録先と読みやすい字幕欄を用意する。"""
        self.e, self.out = explorer, Path(output)
        self.surface = explorer
        self.frames = self.out/'frames'
        self.frames.mkdir(exist_ok=True)
        self.samples, self.operations = [], []
        self.stage = ''
        self.start = time.monotonic()
        self.caption = QtWidgets.QLabel(explorer)
        self.caption.setStyleSheet('background:#17363b;color:#e0ffff;padding:12px;font-size:18px;')
        explorer.layout().insertWidget(0, self.caption)
        self.timer = QtCore.QTimer(explorer)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.capture)
        self.timer.start()

    def position(self, dialog):
        """QPE内へダイアログを置き、字幕を隠さないようにする。"""
        dialog.resize(min(1160, dialog.width()), min(690, dialog.height()))
        dialog.move(self.e.mapToGlobal(QtCore.QPoint(55, 145)))
        dialog.show()

    def capture(self):
        """実描画を取得する。デスクトップの録画ではない。"""
        pix = self.surface.grab()
        painter = QtGui.QPainter(pix)
        for win in QtWidgets.QApplication.topLevelWidgets():
            owner = win.parentWidget()
            while owner is not None and owner is not self.e:
                owner = owner.parentWidget()
            if win is not self.e and win.isVisible() and owner is self.e:
                painter.drawPixmap(self.surface.mapFromGlobal(win.mapToGlobal(QtCore.QPoint())), win.grab())
        if self.surface is not self.e:
            painter.fillRect(0, 0, pix.width(), 48, QtGui.QColor('#17363b'))
            painter.setPen(QtCore.Qt.white)
            painter.setFont(QtGui.QFont('Yu Gothic UI', 14))
            painter.drawText(QtCore.QRect(15, 0, pix.width()-30, 48), QtCore.Qt.AlignVCenter, self.stage)
        painter.end()
        pix.save(str(self.frames/('%05d.png' % len(self.samples))))
        self.samples.append(dict(seconds=time.monotonic()-self.start, stage=self.stage))
        return pix

    def step(self, code, title):
        """操作IDと字幕を動画・索引の両方へ残す。"""
        self.stage = code+'  '+title
        self.operations.append(dict(id=code, title=title, seconds=time.monotonic()-self.start))
        self.caption.setText(self.stage)
        pause(900)

    def hold(self):
        """操作結果を読める時間だけ表示し、対応する静止画も残す。"""
        pause(1500)
        self.capture().save(str(self.out/(self.operations[-1]['id']+'.png')))

    def input(self, text=None, answer=None, callback=None):
        """本物のQt確認・入力ダイアログへ遅延して入力する。"""
        deadline = time.monotonic()+10
        def respond():
            """表示後に実際のボタンを押す。"""
            modal = QtWidgets.QApplication.activeModalWidget()
            if modal is None:
                if time.monotonic() < deadline:
                    QtCore.QTimer.singleShot(100, respond)
                return
            self.position(modal)
            if callback:
                callback(modal)
            elif isinstance(modal, QtWidgets.QInputDialog):
                if text is not None:
                    modal.setTextValue(text)
                pause(1200)
                modal.accept() if text is not None else modal.reject()
            elif isinstance(modal, QtWidgets.QMessageBox):
                pause(1200)
                modal.button(answer or QtWidgets.QMessageBox.Cancel).click()
        QtCore.QTimer.singleShot(150, respond)

    def finish(self):
        """実時間のフレーム間隔を維持してMP4へ変換する。"""
        self.timer.stop()
        self.capture()
        lines = []
        for i, sample in enumerate(self.samples):
            duration = self.samples[i+1]['seconds']-sample['seconds'] if i+1 < len(self.samples) else .15
            lines += ["file '%s'" % (self.frames/('%05d.png' % i)).as_posix(), 'duration %.6f' % duration]
        lines.append("file '%s'" % (self.frames/('%05d.png' % (len(self.samples)-1))).as_posix())
        (self.out/'frames.txt').write_text('\n'.join(lines), encoding='utf8')
        (self.out/'timeline.json').write_text(json.dumps(self.samples, ensure_ascii=False, indent=2), encoding='utf8')
        offset = self.samples[0]['seconds']
        for operation in self.operations:
            operation['seconds'] = max(0, operation['seconds'] - offset)
        video = self.out/('Maya-QPE-'+os.environ['QPE_REVIEW_CHAPTER']+'.mp4')
        # Mayaの標準入力を継承せず、変換が停止してもGUI検証を無期限に待たせない。
        with (self.out/'encode.log').open('w') as log:
            subprocess.run([os.environ['QPE_FFMPEG'], '-nostdin', '-y', '-f', 'concat', '-safe', '0', '-i', str(self.out/'frames.txt'),
                '-vf', 'scale=1360:920:force_original_aspect_ratio=decrease,pad=1360:920:(ow-iw)/2:(oh-ih)/2,setsar=1',
                '-r', '24', '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(video)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
        (self.out/'operations.json').write_text(json.dumps(self.operations, ensure_ascii=False, indent=2), encoding='utf8')
        return str(video)


def main(output_dir, finished):
    """章に対応する実操作を行い、結果と動画を保存する。"""
    from maya import cmds
    import qpeHost
    from qpeSettings import readSettings
    out = Path(output_dir)
    os.environ['QPE_SETTINGS_FILE'] = str(out/'settings.json')
    root = out/'ReviewProject'
    source, target = root/'Materials', root/'Delivery'
    for path in (source/'Textures/VersionA', source/'Textures/VersionB', target, root/'Scenes'):
        path.mkdir(parents=True, exist_ok=True)
    note = source/'readme.txt'
    note.write_text('Hero material review\nApproved for delivery\nAll assets are disposable test files.', encoding='utf8')
    (source/'other.txt').write_text('Other material', encoding='utf8')
    for i in range(1, 4):
        image = QtGui.QImage(640, 360, QtGui.QImage.Format_RGB32)
        image.fill(QtGui.QColor(['#32758b', '#598258', '#986e42'][i-1]))
        image.save(str(source/('texture.%04d.png' % (1000+i))))
    e = qpeHost.show(str(source))
    cmds.workspaceControl(qpeHost.CONTROL, edit=True, resizeWidth=1360, resizeHeight=920)
    e.setBrowseRoot(str(root))
    e.navigate(str(source))
    o, w = e.organizer, e.organizer.workspace
    r = Recorder(e, out)
    chapter = os.environ['QPE_REVIEW_CHAPTER']

    def settled():
        """全予約の完了を待ち、実エラーを見逃さない。"""
        waitFor(lambda: o.task is None and not o.queue)
        if o.jobRecords:
            record = o.jobRecords[-1]
            assert not record.get('error'), record
            if isinstance(record.get('result'), dict):
                assert not record['result'].get('errors'), record

    def closeDialogs():
        """前操作の結果ウィンドウを閉じ、次の操作を見やすくする。"""
        for dialog in o.dialogs:
            dialog.close()

    try:
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 5)
        if chapter == 'navigation':
            from qpe_ui_navigation import click
            r.step('N01', '階層を単クリックで掘る・空の末尾列は表示しない')
            click(e, source/'Textures')
            click(e, source/'Textures/VersionA')
            r.hold()
            r.step('N02', '戻る・進む・パス欄から移動')
            e.backButton.click(); pause(800); e.forwardButton.click(); pause(800)
            e.address.setText(str(source)); QtTest.QTest.keyClick(e.address, QtCore.Qt.Key_Return)
            assert Path(e.currentDirectory) == source
            r.hold()
            r.step('N03', '左右サイドバーを開閉しても最深列を保つ')
            e.sidebarButton.click(); pause(900); e.inspectorButton.click(); pause(900)
            e.sidebarButton.click(); pause(900); e.inspectorButton.click()
            r.hold()
            r.step('N04', '名前フィルター・拡張子フィルター・列の並べ替え')
            e.search.setText('texture'); pause(1200); e.search.clear()
            e.fileFilter.setCurrentIndex(2); pause(1200); e.fileFilter.setCurrentIndex(0)
            e.files.sortByColumn(1, QtCore.Qt.DescendingOrder)
            r.hold()
            r.step('N05', 'フォルダーとファイルをお気に入りに登録・選択して移動')
            e.addFavoritePath(str(target)); e.addFavoritePath(str(note)); e.setSidebarVisible(True)
            pause(700); e._visitPlace(str(note))
            r.hold()
            r.step('N06', 'タブ追加・切替・閉じる・閉じたタブの復元')
            e.folderTabs.add(); e.navigate(str(target)); pause(1000)
            e.folderTabs.close(e.folderTabs.active); pause(800); e.folderTabs.reopen()
            r.hold()
            r.step('N07', '文字・UI倍率を変更して標準へ戻す')
            e.appearance.show(); r.position(e.appearance.dialog)
            e.appearance.setPreset(1); pause(1300); e.appearance.setPreset(0)
            r.hold(); e.appearance.dialog.hide()
            r.step('N08', 'Toolsを用途別に整理・操作名はコマンド検索からも利用')
            o.populateTools(); o.toolsMenu.popup(e.mapToGlobal(QtCore.QPoint(1010, 105)))
            r.hold(); o.toolsMenu.close()
            r.step('N09', '第2ペインは別の場所を独立表示')
            o.toggleSecond(); o.second.navigate(str(source))
            r.hold(); o.toggleSecond()
            r.step('N10', '探索の起点を解除・現在地を起点に設定')
            e.rootButton.click(); pause(1200); e.rootButton.click()
            r.hold()
        elif chapter == 'files':
            from qpe_ui_context import triggerMenu
            r.step('F01', '右クリックから新規フォルダー・テキストを作成')
            r.input('Notes'); triggerMenu(e.createFileMenu([]), 'New Folder…')
            r.input('review'); triggerMenu(e.createFileMenu([]), 'New Text File…')
            assert (source/'Notes').is_dir() and (source/'review.txt').is_file()
            r.hold()
            r.step('F02', 'F2で名前を変更・拡張子は維持')
            selectFile(e, source/'review.txt'); e.renamePath(str(source/'review.txt')); pause(200)
            QtTest.QTest.keyClicks(e._inlineRename, 'approved'); pause(1200)
            QtTest.QTest.keyClick(e._inlineRename, QtCore.Qt.Key_Return)
            assert (source/'approved.txt').exists(); r.hold()
            r.step('F03', 'コピーして別フォルダーへ貼り付け')
            o.clipboard([str(note)]); e.navigate(str(target)); o.paste(str(target)); settled()
            assert (target/note.name).read_bytes() == note.read_bytes(); r.hold()
            r.step('F04', '同名ファイルは別名保存・スキップ・置換を選べる')
            r.input('Keep both (new name)'); o.paste(str(target)); settled()
            assert len(list(target.glob('*.txt'))) == 2; r.hold()
            r.step('F05', 'Undo・Redoでファイル操作を戻す・やり直す')
            o.undo(); settled(); pause(1200); w.redo(); settled(); r.hold()
            r.step('F06', '切り取りで移動・Undoで元の場所へ戻す')
            o.clipboard([str(source/'approved.txt')], True); o.paste(str(target)); settled()
            assert not (source/'approved.txt').exists(); pause(1100)
            o.undo(); settled(); assert (source/'approved.txt').exists(); r.hold()
            r.step('F07', '複製・ごみ箱移動・Undoによる復元')
            e.navigate(str(source)); o.transfer('duplicate', [str(source/'approved.txt')], conflict='rename'); settled()
            duplicate = next(p for p in source.glob('approved*.txt') if p.name != 'approved.txt')
            r.input(answer=QtWidgets.QMessageBox.Yes); o.transfer('trash', [str(duplicate)]); settled()
            assert not duplicate.exists(); o.undo(); settled(); assert duplicate.exists(); r.hold()
            r.step('F08', '一括リネームは実行前に変更後の名前を確認')
            o.batchRename([str(note), str(source/'other.txt')]); dialog=o.dialogs[-1]; r.position(dialog)
            dialog.findChildren(QtWidgets.QLineEdit)[2].setText('delivery_'); pause(1500)
            next(b for b in dialog.findChildren(QtWidgets.QPushButton) if b.text() == 'Apply rename').click()
            settled(); assert (source/'delivery_readme.txt').exists(); r.hold()
            o.undo(); settled()
            r.step('F09', 'サイズ・件数集計、SHA-256、重複ファイルの確認')
            w.summary([str(source)]); settled(); r.position(o.dialogs[-1]); r.hold(); closeDialogs()
            triggerMenu(e.createFileMenu([str(note)]), 'SHA-256'); settled(); r.position(o.dialogs[-1]); r.hold(); closeDialogs()
            o.duplicates(); settled(); r.position(o.dialogs[-1]); r.hold(); closeDialogs()
            r.step('F10', '履歴を確認・保存期限を超えたバックアップを整理')
            w.history(); r.position(o.dialogs[-1]); r.hold(); closeDialogs()
            r.input(answer=QtWidgets.QMessageBox.Yes); w.cleanupHistory(); settled(); r.hold()
            r.step('F11', '同名競合：スキップは宛先保持・置換はUndo可能')
            conflict=target/note.name
            conflict.write_text('Destination version', encoding='utf8')
            r.input('Skip existing'); o.transfer('copy', [str(note)], str(target)); settled()
            assert conflict.read_text(encoding='utf8')=='Destination version'
            r.input('Replace (Undo backup)'); o.transfer('copy', [str(note)], str(target)); settled()
            assert conflict.read_bytes()==note.read_bytes()
            o.undo(); settled(); assert conflict.read_text(encoding='utf8')=='Destination version'; r.hold()
            r.step('F12', 'フォルダー結合：同名項目ごとに判断・宛先だけのファイルは維持')
            (source/'Notes/same.txt').write_text('source', encoding='utf8')
            (target/'Notes').mkdir()
            (target/'Notes/same.txt').write_text('target', encoding='utf8')
            (target/'Notes/keep.txt').write_text('keep', encoding='utf8')
            def chooseMerge(dialog):
                """結合を選び、続く競合比較で置換を確定する。"""
                dialog.setTextValue('Merge folders (keep destination-only files)'); pause(1100); dialog.accept()
                r.input(callback=lambda d: (pause(1400), d.accept()))
            r.input(callback=chooseMerge); o.transfer('copy', [str(source/'Notes')], str(target)); settled()
            assert (target/'Notes/same.txt').read_text()=='source' and (target/'Notes/keep.txt').exists()
            r.hold()
        elif chapter == 'organize':
            r.step('O01', 'タグ・評価・コレクションをファイルへ付与')
            def labels(dialog):
                """ラベル編集欄へ入力して保存する。"""
                fields = dialog.findChildren(QtWidgets.QLineEdit)
                fields[0].setText('Hero, Approved'); fields[1].setText('Delivery')
                dialog.findChild(QtWidgets.QSpinBox).setValue(4); pause(1500)
                next(b for b in dialog.findChildren(QtWidgets.QPushButton) if b.text() == 'Save').click()
            r.input(callback=labels); o.tag([str(note)]); r.hold()
            r.step('O02', 'タグ・評価でファイルを探す')
            r.input('rating:3'); o.browseTags(); r.position(o.dialogs[-1]); r.hold(); closeDialogs()
            r.step('O03', '複数条件の検索を保存し、結果から元のフォルダーへ')
            search=o.search(); r.position(search); search.query.setText('readme'); search.content.setText('Hero')
            search.search(); waitFor(lambda: search.task is None)
            assert search.results.topLevelItemCount() == 1
            r.input('Approved review'); search.saveQuery(); r.hold()
            search.locate(search.results.topLevelItem(0)); search.close()
            r.step('O04', 'タグ名をまとめて変更')
            responses=iter(['Approved', 'Ready'])
            def answerTag(dialog):
                """二段階の名称変更を本物の入力欄で行う。"""
                dialog.setTextValue(next(responses)); pause(900); dialog.accept()
                r.input(callback=lambda d: (d.setTextValue(next(responses)), pause(900), d.accept()))
            r.input(callback=answerTag); w.manageLabels(); r.hold()
            r.step('O05', 'ZIP作成・中身の確認・選択項目だけ展開')
            # OSネイティブの保存先ダイアログだけ専用パスへ固定する。ZIP処理は本番経路。
            archive=source/'delivery.zip'
            with patch.object(QtWidgets.QFileDialog, 'getSaveFileName', return_value=(str(archive), 'ZIP')):
                o.zip([str(note), str(source/'other.txt')])
            settled(); w.productivity.archive(str(archive)); dialog=o.dialogs[-1]; r.position(dialog)
            waitFor(lambda: dialog.extract.isEnabled()); dialog.table.topLevelItem(0).setSelected(True); r.hold()
            r.input(str(target/'Selected')); dialog.extract.click(); settled(); dialog.close()
            assert (target/'Selected').is_dir()
            r.step('O06', 'ZIP全体を新しいフォルダーへ展開')
            r.input(str(target/'All')); o.unzip(str(archive)); settled()
            assert (target/'All'/note.name).exists(); r.hold()
            r.step('O07', 'フォルダー比較・差分確認後に一方向同期')
            e.navigate(str(source))
            r.input(answer=QtWidgets.QMessageBox.Yes)
            with patch.object(QtWidgets.QFileDialog, 'getExistingDirectory', return_value=str(target/'Sync')):
                (target/'Sync').mkdir(); o.compare()
            settled(); pause(500); settled()
            assert (target/'Sync'/note.name).exists(); r.hold(); closeDialogs()
        elif chapter == 'settings':
            r.step('S01', '作業セットを保存・切替・直前のセットを復元')
            e.folderTabs.add(); e.navigate(str(target)); w.productivity.saveSet('Review')
            e.navigate(str(source)); w.productivity.loadSet('Review'); pause(1100)
            e.folderTabs.restoreSession(readSettings()['previousWorkspace']); r.hold()
            r.step('S02', '固定タブは閉じられないことをボタンで示す')
            w.productivity.setTabFlag(e.folderTabs.active, 'pinned', True)
            r.hold(); w.productivity.setTabFlag(e.folderTabs.active, 'pinned', False)
            r.step('S03', '設定を変更・JSONへ書出し・取込み')
            from qpePreferences import PreferencesDialog
            dialog=PreferencesDialog(w); r.position(dialog)
            dialog.days.setValue(14); dialog.local.setChecked(True); assert dialog.apply()
            settings=out/'portable-settings.json'
            with patch.object(QtWidgets.QFileDialog, 'getSaveFileName', return_value=(str(settings), 'JSON')):
                dialog.export()
            dialog.days.setValue(30); dialog.apply(); r.hold()
            r.input(answer=QtWidgets.QMessageBox.Yes)
            with patch.object(QtWidgets.QFileDialog, 'getOpenFileName', return_value=(str(settings), 'JSON')):
                dialog.load()
            assert readSettings()['preferences']['undoDays'] == 14; r.hold()
            r.step('S04', '保存された待機転送を確認・明示的に再開')
            o.queuePaused=True; o.transfer('copy', [str(note)], str(target), 'rename')
            saved=o.queue.pop(); saved[-1]['state']='Cancelled before start'
            w.recoverTransfers(); dialog=o.dialogs[-1]; r.position(dialog)
            table=dialog.findChild(QtWidgets.QTreeWidget); table.setCurrentItem(table.topLevelItem(0)); r.hold()
            o.queuePaused=False
            next(b for b in dialog.findChildren(QtWidgets.QPushButton) if b.text()=='Resume selected').click()
            settled(); assert (target/note.name).exists(); r.hold()
            r.step('S05', '待機ジョブを中止・保存記録を破棄')
            o.queuePaused=True; o.transfer('copy', [str(note)], str(target), 'rename'); w.jobs()
            dialog=o.dialogs[-1]; r.position(dialog)
            next(b for b in dialog.findChildren(QtWidgets.QPushButton) if b.text()=='Cancel queued').click(); r.hold(); dialog.close()
            w.recoverTransfers(); dialog=o.dialogs[-1]; r.position(dialog)
            table=dialog.findChild(QtWidgets.QTreeWidget); table.setCurrentItem(table.topLevelItem(0))
            next(b for b in dialog.findChildren(QtWidgets.QPushButton) if b.text()=='Discard record').click()
            assert table.topLevelItemCount()==0; r.hold(); dialog.close(); o.queuePaused=False
            r.step('S06', '失敗した転送の理由を確認・原因解消後に再試行')
            missing=source/'temporarily_missing.txt'
            o.transfer('copy', [str(missing)], str(target), 'rename')
            waitFor(lambda: o.task is None)
            assert o.jobRecords[-1]['result']['errors']
            r.position(o.dialogs[-1]); r.hold(); closeDialogs()
            missing.write_text('Source restored for retry', encoding='utf8')
            w.jobs(); dialog=o.dialogs[-1]; r.position(dialog)
            table=dialog.findChild(QtWidgets.QTreeWidget); table.setCurrentItem(table.topLevelItem(table.topLevelItemCount()-1))
            next(b for b in dialog.findChildren(QtWidgets.QPushButton) if b.text()=='Retry failed items').click()
            settled(); assert (target/missing.name).exists(); r.hold(); dialog.close()
            r.step('S07', '実行中の転送を中止・原本を保持')
            o.queuePaused=True; o.transfer('copy', [str(note)], str(target), 'rename')
            record=o.queue[-1][-1]; record['paused'].set(); o.queuePaused=False; o.nextJob()
            w.jobs(); dialog=o.dialogs[-1]; r.position(dialog)
            next(b for b in dialog.findChildren(QtWidgets.QPushButton) if b.text()=='Cancel active').click()
            settled(); assert record['result']['cancelled'] and note.exists(); r.hold(); dialog.close()
        elif chapter == 'maya':
            e.navigate(str(root/'Scenes')); e.setInspectorVisible(True)
            cmds.file(new=True, force=True); cube=cmds.polyCube(name='reviewCube')[0]
            cmds.select(cube); cmds.viewFit()
            r.step('M01', '現在のシーンを名前を付けて保存')
            e.operationTabs.setCurrentWidget(e.savePanel); e.fileName.setText('asset')
            e.actionButtons['saveAs'].click(); scene=root/'Scenes/asset.ma'
            assert scene.exists(); r.hold()
            r.step('M02', '現在のシーンを上書き保存・選択物を書出し')
            cmds.setAttr(cube+'.translateX', 2); e.actionButtons['save'].click()
            e.fileName.setText('selection'); e.actionButtons['export'].click()
            exported=root/'Scenes/selection.ma'; assert exported.exists(); r.hold()
            r.step('M03', '未保存変更があるOpenをキャンセル・シーンを保護')
            e.operationTabs.setCurrentWidget(e.readPanel)
            selectFile(e, scene); cmds.setAttr(cube+'.translateX', 4)
            r.input(answer=QtWidgets.QMessageBox.Cancel); e.actionButtons['open'].click()
            assert cmds.getAttr(cube+'.translateX')==4; r.hold()
            r.step('M04', 'ファイルを開く・選択外からのダブルクリックでもOpen')
            cmds.file(modified=False); e.files.clearSelection()
            index=e.fileProxy.mapFromSource(e.fileModel.index(str(scene)))
            QtTest.QTest.mouseDClick(e.files.viewport(), QtCore.Qt.LeftButton, pos=e.files.visualRect(index).center())
            assert cmds.getAttr(cube+'.translateX')==2; r.hold()
            r.step('M05', 'Import：名前空間を指定して読込み')
            selectFile(e, exported); e.readOptions.setCurrentIndex(0)
            fields=e.readOptions.controls['import']; fields['mode'].setCurrentIndex(1); fields['name'].setText('imported')
            pause(1300); e.actionButtons['import'].click()
            assert cmds.objExists('imported:reviewCube'); r.hold()
            r.step('M06', 'Reference：名前空間と遅延読込みを指定')
            e.readOptions.setCurrentIndex(1); fields=e.readOptions.controls['reference']
            fields['mode'].setCurrentIndex(1); fields['name'].setText('referenced'); fields['deferReference'].setChecked(True)
            pause(1300); e.actionButtons['reference'].click()
            assert cmds.file(query=True, reference=True); r.hold()
            r.step('M07', '読込み設定プリセット保存・既存名前空間から指定')
            r.input('Character reference'); o.saveReadPreset()
            r.input('imported'); o.namespaces(); r.hold()
            r.step('M08', '保存済みシーンのプレビューと依存情報を生成')
            e.operationTabs.setCurrentWidget(e.savePanel)
            e.actionButtons['save'].click(); o.sidecar()
            assert scene.with_suffix('.qpe.json').exists() or Path(str(scene)+'.qpe.json').exists()
            e.operationTabs.setCurrentWidget(e.readPanel)
            selectFile(e, scene); r.hold()
            from qpeSearch import sceneInfo
            o.showText(json.dumps(sceneInfo(str(scene)), ensure_ascii=False, indent=2)); r.position(o.dialogs[-1]); r.hold(); closeDialogs()
            r.step('M09', 'Mayaへドッキング・フローティングへ戻す')
            r.surface=qpeHost.shiboken.wrapInstance(int(qpeHost.OpenMayaUI.MQtUtil.mainWindow()), QtWidgets.QWidget)
            cmds.workspaceControl(qpeHost.CONTROL, edit=True, dockToMainWindow=('right', False)); pause(1700)
            assert not cmds.workspaceControl(qpeHost.CONTROL, query=True, floating=True)
            r.hold()
            r.surface=e
            cmds.workspaceControl(qpeHost.CONTROL, edit=True, floating=True, resizeWidth=1360, resizeHeight=920)
            r.hold()
        else:
            raise ValueError(chapter)
        r.step('END', '専用データでの実操作確認が完了しました')
        r.hold()
        result=dict(status='passed', chapter=chapter, maya=cmds.about(version=True), video=r.finish(),
                    operations=r.operations, capture='Actual Qt widget rendering; automated inputs; owned dialogs composited; native file selectors supplied fixture paths')
    except Exception:
        r.timer.stop()
        r.capture().save(str(out/'failure.png'))
        result=dict(status='error', chapter=chapter, stage=r.stage, operations=r.operations, error=traceback.format_exc())
    (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    finished(result)
