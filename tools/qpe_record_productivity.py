"""追加操作を専用Mayaで字幕付き録画する。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpe_ui_advanced import QtCore, QtGui, QtWidgets
from qpe_ui_maya import pause, waitFor, selectFile


def main(output_dir, finished):
    """実UIの操作と画面を記録し、実時間のMP4へ保存する。"""
    import qpeHost
    from maya import cmds
    out = Path(output_dir)
    frames = out/'frames'
    frames.mkdir(exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out/'settings.json')
    root = out/'ReviewProject'
    source, target = root/'Materials', root/'Delivery'
    source.mkdir(parents=True, exist_ok=True)
    target.mkdir(exist_ok=True)
    note = source/'readme.txt'
    note.write_text('Material review\n\nHero texture: check surface detail.\nApproved for the sample delivery.\n\nAll files in this video are test assets.', encoding='utf8')
    im = QtGui.QImage(640, 360, QtGui.QImage.Format_RGB32)
    im.fill(QtGui.QColor('#347a89'))
    painter = QtGui.QPainter(im)
    painter.setPen(QtCore.Qt.white)
    painter.setFont(QtGui.QFont('Segoe UI', 30))
    painter.drawText(im.rect(), QtCore.Qt.AlignCenter, 'Hero texture')
    painter.end()
    im.save(str(source/'hero.png'))
    with zipfile.ZipFile(source/'delivery.zip', 'w') as z:
        z.writestr('Materials/readme.txt', 'Sample delivery')
        z.writestr('Scenes/notes.txt', 'Scene notes')
    e = qpeHost.show(str(source))
    cmds.workspaceControl(qpeHost.CONTROL, edit=True, resizeWidth=1360, resizeHeight=920)
    e.setBrowseRoot(str(root))
    e.navigate(str(source))
    w, p = e.organizer.workspace, e.organizer.workspace.productivity
    caption = QtWidgets.QLabel(e)
    caption.setStyleSheet('background:#17363b;color:#e0ffff;padding:12px;font-size:19px;')
    e.layout().insertWidget(0, caption)
    samples, stage = [], ''
    started = time.monotonic()

    def capture():
        """所有ダイアログと候補ポップアップも実描画から記録する。"""
        pix = e.grab()
        painter = QtGui.QPainter(pix)
        popup = p.completer.popup()
        for win in QtWidgets.QApplication.topLevelWidgets():
            owner = win.parentWidget()
            while owner is not None and owner is not e:
                owner = owner.parentWidget()
            if win is not e and win.isVisible() and (owner is e or win is popup):
                painter.drawPixmap(e.mapFromGlobal(win.mapToGlobal(QtCore.QPoint())), win.grab())
        painter.end()
        pix.save(str(frames/('%05d.png' % len(samples))))
        samples.append(dict(seconds=time.monotonic()-started, stage=stage))
        return pix

    def step(text):
        """利用者向けの操作字幕を表示する。"""
        nonlocal stage
        stage = text
        caption.setText(text)
        pause(800)

    def position(dialog):
        """実ダイアログを録画領域内へ置く。"""
        dialog.resize(1080, 640)
        dialog.move(e.mapToGlobal(QtCore.QPoint(70, 145)))
        dialog.show()

    timer = QtCore.QTimer(e)
    timer.setInterval(125)
    timer.timeout.connect(capture)
    try:
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 3)
        timer.start()
        step('01  Maya QPE — 日常操作を短縮する追加機能')
        pause(2200)
        step('02  パス補完：入力途中のフォルダーを候補から選択')
        e.address.setFocus()
        e.address.setText(str(root).replace('\\', '/')+'/Mat')
        p.edited(e.address.text())
        waitFor(lambda: bool(p.model.stringList()))
        pause(3000)
        p.completer.popup().hide()
        e.address.setText(str(source))
        step('03  ファイル選択で詳細を確認 — 開く操作は関連付けアプリへ')
        selectFile(e, note)
        e.setInspectorVisible(True)
        pause(3000)
        capture().save(str(out/'details.png'))
        e.setInspectorVisible(False)
        step('04  場所ロック：元のタブを残して別フォルダーへ移動')
        p.setTabFlag(e.folderTabs.active, 'locked', True)
        e.navigate(str(target))
        pause(2600)
        p.saveSet('Material review')
        e.navigate(str(source))
        pause(1000)
        step('05  本文検索：Heroが書かれた行とファイルを確認')
        search = e.organizer.search()
        position(search)
        search.content.setText('Hero')
        search.search()
        waitFor(lambda: search.task is None)
        pause(3500)
        capture().save(str(out/'search.png'))
        search.close()
        step('06  ZIP内部閲覧：展開前に中身を確認し、必要な項目を選択')
        p.archive(str(source/'delivery.zip'))
        archive = e.organizer.dialogs[-1]
        position(archive)
        waitFor(lambda: archive.extract.isEnabled())
        archive.table.topLevelItem(0).setSelected(True)
        pause(3500)
        capture().save(str(out/'zip.png'))
        archive.close()
        step('07  転送ジョブ：待機・実行中の停止・再開を分けて操作')
        e.organizer.queuePaused = True
        e.organizer.transfer('copy', [str(note)], str(target), 'rename')
        w.jobs()
        jobs = e.organizer.dialogs[-1]
        position(jobs)
        jobs.resize(1210, 550)
        pause(2000)
        record = e.organizer.queue[0][-1]
        record['paused'].set()
        e.organizer.queuePaused = False
        e.organizer.nextJob()
        record['state'] = 'Paused'
        pause(1800)
        record['paused'].clear()
        record['state'] = 'Running'
        waitFor(lambda: e.organizer.task is None)
        pause(2000)
        jobs.close()
        step('08  Availability：取得状態を表示。オンライン素材は自動取得しない')
        w.mode.setCurrentIndex(2)
        waitFor(lambda: w.tree.topLevelItemCount() == 3)
        w.tree.setColumnWidth(0, 190)
        w.tree.setColumnWidth(6, 120)
        w.tree.setColumnWidth(8, 220)
        pause(3500)
        capture().save(str(out/'overview.png'))
        step('09  ファイル状態の診断：原因と次の確認先を表示')
        p.diagnose([str(note)])
        waitFor(lambda: e.organizer.task is None)
        diagnosis = e.organizer.dialogs[-1]
        position(diagnosis)
        pause(3500)
        diagnosis.close()
        step('10  確認完了 — 専用データ・Maya 2027。実クラウド同期は別途確認')
        pause(2200)
        timer.stop()
        capture()
        lines = []
        for i, sample in enumerate(samples):
            duration = samples[i+1]['seconds']-sample['seconds'] if i+1 < len(samples) else .125
            lines += ["file '%s'" % (frames/('%05d.png' % i)).as_posix(), 'duration %.6f' % duration]
        lines.append("file '%s'" % (frames/('%05d.png' % (len(samples)-1))).as_posix())
        (out/'frames.txt').write_text('\n'.join(lines), encoding='utf8')
        video = out/'Maya-QPE-productivity.mp4'
        args = [os.environ['QPE_FFMPEG'], '-y', '-f', 'concat', '-safe', '0', '-i', str(out/'frames.txt'), '-vf',
                'scale=1360:920:force_original_aspect_ratio=decrease,pad=1360:920:(ow-iw)/2:(oh-ih)/2,setsar=1',
                '-r', '24', '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(video)]
        with (out/'encode.log').open('w') as log:
            subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True)
        result = dict(status='passed', seconds=samples[-1]['seconds'], video=str(video),
                      capture='Actual Qt widgets with automated controls, actual dialog rendering composited, wall-clock timing')
    except Exception:
        timer.stop()
        capture().save(str(out/'failure.png'))
        result = dict(status='error', stage=stage, error=traceback.format_exc())
    (out/'timeline.json').write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding='utf8')
    (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    finished(result)
