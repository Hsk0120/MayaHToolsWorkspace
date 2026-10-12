"""隔離Mayaで追加機能の実ウィジェット描画を録画する。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpe_ui_advanced import QtCore, QtGui, QtWidgets, QtTest
from qpe_ui_maya import pause, waitFor


def main(output_dir, finished):
    """専用素材だけを操作し、字幕付き動画と時刻ログを保存する。"""
    import qpeHost
    from maya import cmds
    from qpeSettings import writeSettings
    from qpePreferences import PreferencesDialog
    out = Path(output_dir)
    frames = out / 'frames'
    frames.mkdir(exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    root = out / 'ReviewProject'
    assets = root / 'Assets' / 'Textures'
    assets.mkdir(parents=True, exist_ok=True)
    (assets / 'Archive').mkdir(exist_ok=True)
    (assets / 'Archive' / 'notes.txt').write_text('Archived texture notes')
    (root / 'Scenes').mkdir(exist_ok=True)
    images = []
    for i, name in enumerate(['wood_basecolor', 'wood_variant', 'metal_roughness', 'stone_basecolor', 'fabric_blue', 'fabric_red']):
        path = assets / (name + '.png')
        im = QtGui.QImage(640, 360, QtGui.QImage.Format_RGB32)
        im.fill(QtGui.QColor(['#a97744', '#c79559', '#78818a', '#90957d', '#366991', '#944957'][i]))
        p = QtGui.QPainter(im)
        p.setPen(QtGui.QColor('#ffffff'))
        for n in range(12):
            p.drawLine(0, n * 32, 640, n * 32 + 20)
        p.setFont(QtGui.QFont('Segoe UI', 26))
        p.drawText(im.rect(), QtCore.Qt.AlignCenter, name.replace('_', '\n'))
        p.end()
        im.save(str(path))
        images.append(str(path))
    (assets / 'README.md').write_text('# Texture Library\n\n## Review checklist\n\n- Compare color variants\n- Check texture dimensions\n- Assign **Hero** tags\n\nAll assets in this demonstration are test data.', encoding='utf8')
    pdf = assets / 'asset_guide.pdf'
    writer = QtGui.QPdfWriter(str(pdf))
    writer.setResolution(96)
    p = QtGui.QPainter(writer)
    p.setFont(QtGui.QFont('Segoe UI', 24))
    p.drawText(50, 100, 'Texture Library - Page 1')
    p.drawText(50, 180, 'Review materials before import')
    writer.newPage()
    p.drawText(50, 100, 'Texture Library - Page 2')
    p.drawText(50, 180, 'Naming and namespace guidelines')
    p.end()
    del writer
    writeSettings({'fileLabels': {os.path.normcase(images[0]): dict(tags=['Hero'], rating=4, collection='Demo')}})
    e = qpeHost.show(str(assets))
    cmds.workspaceControl(qpeHost.CONTROL, edit=True, resizeWidth=1360, resizeHeight=920)
    e.setBrowseRoot(str(root))
    e.navigate(str(assets))
    e.setInspectorVisible(False)
    w = e.organizer.workspace
    caption = QtWidgets.QLabel(e)
    caption.setStyleSheet('background:#17363b;color:#e0ffff;padding:12px;font-size:19px;')
    e.layout().insertWidget(0, caption)
    samples = []
    stage = ''
    start = time.monotonic()

    def capture():
        """ダイアログを含む実描画を保存する。"""
        pix = e.grab()
        painter = QtGui.QPainter(pix)
        for win in QtWidgets.QApplication.topLevelWidgets():
            owner = win.parentWidget()
            while owner is not None and owner is not e:
                owner = owner.parentWidget()
            if win is not e and win.isVisible() and owner is e:
                painter.drawPixmap(e.mapFromGlobal(win.mapToGlobal(QtCore.QPoint())), win.grab())
        painter.end()
        pix.save(str(frames / ('%05d.png' % len(samples))))
        samples.append(dict(seconds=time.monotonic()-start, stage=stage))
        return pix

    def step(title):
        """字幕を更新する。"""
        nonlocal stage
        stage = title
        caption.setText(title)
        pause(800)

    def showDialog(d):
        """ダイアログを録画範囲内に置く。"""
        d.resize(1040, 640)
        d.move(e.mapToGlobal(QtCore.QPoint(90, 135)))
        d.show()
        pause(3000)

    timer = QtCore.QTimer(e)
    timer.setInterval(125)
    timer.timeout.connect(capture)
    checks = []
    try:
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 8)
        timer.start()
        step('01  Maya版 QuickPathExplorer — カラムで素材フォルダーへ移動')
        pause(2500)
        step('02  Thumbnails：画像を一覧し、名前と内容を同時に確認')
        w.mode.setCurrentIndex(1)
        waitFor(lambda: w.grid.count() == 8 and len(w.cache) >= 6)
        pause(4000)
        capture().save(str(out / 'thumbnails.png'))
        checks.append('8 thumbnail items, 6 rendered images')
        step('04  Metadata：タグ・評価・画像寸法を一覧表示')
        w.mode.setCurrentIndex(2)
        waitFor(lambda: w.tree.topLevelItemCount() == 8)
        pause(3500)
        capture().save(str(out / 'metadata.png'))
        step('05  Heroタグで絞り込み → 種類ごとにグループ化')
        w.labelFilter.setCurrentIndex(w.labelFilter.findData('Hero'))
        waitFor(lambda: w.tree.topLevelItemCount() == 1)
        pause(2500)
        w.labelFilter.setCurrentIndex(0)
        w.group.setCurrentText('Type')
        pause(3000)
        w.group.setCurrentIndex(0)
        step('06  Include subfolders：下層のファイルも同じ一覧で確認')
        w.flat.setChecked(True)
        waitFor(lambda: len(w.items) == 9)
        pause(3500)
        checks.append('tag filtering and recursive 9-item listing')
        step('07  拡張検索：名前・種類・サイズ・タグなどで検索')
        d = e.organizer.search()
        d.root.setText(str(assets))
        d.query.setText('wood')
        showDialog(d)
        d.search()
        waitFor(lambda: d.task is None)
        assert d.results.topLevelItemCount() == 2
        pause(3000)
        d.close()
        checks.append('wood search returns 2 images')
        step('10  Preferences：履歴の保存期限・容量や操作設定をまとめて変更')
        d = PreferencesDialog(w)
        showDialog(d)
        pause(2000)
        d.close()
        step('11  コマンド検索：操作名を入力して表示を切り替える')
        def paletteInput():
            """検索欄からコマンドを実行する。"""
            modal = QtWidgets.QApplication.activeModalWidget()
            modal.move(e.mapToGlobal(QtCore.QPoint(220, 170)))
            query = modal.findChild(QtWidgets.QLineEdit)
            query.setText('View: thumbnails')
            pause(3000)
            QtTest.QTest.keyClick(query, QtCore.Qt.Key_Return)
        QtCore.QTimer.singleShot(200, paletteInput)
        w.palette()
        w.flat.setChecked(False)
        pause(2000)
        step('12  撮影完了 — 専用素材・隔離Maya 2027での操作確認')
        pause(3000)
        timer.stop()
        capture()
        entries = []
        for i, sample in enumerate(samples):
            duration = samples[i+1]['seconds']-sample['seconds'] if i+1 < len(samples) else .125
            entries += ["file '%s'" % (frames / ('%05d.png' % i)).as_posix(), 'duration %.6f' % duration]
        entries += ["file '%s'" % (frames / ('%05d.png' % (len(samples)-1))).as_posix()]
        (out / 'frames.txt').write_text('\n'.join(entries), encoding='utf8')
        video = out / 'Maya-QPE-advanced.mp4'
        args = [os.environ['QPE_FFMPEG'], '-y', '-f', 'concat', '-safe', '0', '-i', str(out / 'frames.txt'), '-vf', 'scale=1360:920:force_original_aspect_ratio=decrease,pad=1360:920:(ow-iw)/2:(oh-ih)/2,setsar=1', '-r', '24', '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(video)]
        with (out / 'encode.log').open('w') as log:
            subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True)
        result = dict(status='passed', maya=cmds.about(version=True), checks=checks, video=str(video), seconds=samples[-1]['seconds'], capture='Actual Qt widgets with automated controls; dialogs composited from their actual rendering; wall-clock frame timing')
    except Exception:
        timer.stop()
        capture().save(str(out / 'failure.png'))
        result = dict(status='error', stage=stage, error=traceback.format_exc())
    (out / 'timeline.json').write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding='utf8')
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    finished(result)
