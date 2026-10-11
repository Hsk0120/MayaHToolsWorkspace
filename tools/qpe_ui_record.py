"""専用MayaでQuickPathExplorerの実UI操作を連続キャプチャする。"""
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpe_ui_navigation import ROOT, columns, click, inspectFolder
from qpe_ui_maya import pause, waitFor, selectFile
from qpe_ui_context import answerInput, triggerMenu
from qpeQt import QtCore, QtGui, QtWidgets


def main(output_dir, finished):
    """実UIの描画を12fpsで記録し、H.264 MP4と画面を保存する。

    Args:
        output_dir (Path): 隔離GUIの証跡先。
        finished (callable): ランナーの終了通知。
    """
    import qpeHost
    from maya import cmds
    folder = Path(output_dir).resolve()
    movie = folder / 'review'
    frames_dir = movie / 'frames'
    frames_dir.mkdir(parents=True)
    os.environ['QPE_SETTINGS_FILE'] = str(folder / 'settings.json')
    root = folder / 'ReviewProject'
    for part in ('Characters/Hero/Rig/Work', 'Characters/Villain/Model', 'Props/Chair/Textures', 'Empty', '日本語 素材/画像'):
        (root / part).mkdir(parents=True)
    for number in range(70):
        (root / 'Library' / ('Asset_%02d' % number) / 'Textures').mkdir(parents=True)
    (root / 'Characters/Hero/hero_v001.ma').write_text('// preview sample; no scene loaded', encoding='utf-8')
    (root / 'Characters/Hero/README.txt').write_text('QuickPathExplorer UI review', encoding='utf-8')
    widget = qpeHost.show(str(root / 'Characters'))
    cmds.workspaceControl(qpeHost.CONTROL, edit=True, resizeWidth=1280, resizeHeight=900)
    caption = QtWidgets.QLabel(widget)
    caption.setObjectName('testRecordingCaption')
    caption.setStyleSheet('background:#17363b;color:#d5ffff;padding:12px;font-size:18px;')
    widget.layout().insertWidget(0, caption)
    marker = QtWidgets.QLabel(widget)
    marker.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
    marker.setFixedSize(28, 28)
    marker.setStyleSheet('border:3px solid #ffcc66;border-radius:13px;background:transparent;')
    marker.hide()
    captured = []
    checks = []
    stage = ''
    started = time.monotonic()

    def grabReview():
        """Explorer所有のメニュー・ダイアログも実描画から合成する。

        Returns:
            QPixmap: Explorerの領域に収めた実画面。
        """
        pixmap = widget.grab()
        painter = QtGui.QPainter(pixmap)
        for window in QtWidgets.QApplication.topLevelWidgets():
            # isAncestorOfは別ウィンドウ境界で止まるため、QObject所有関係をたどる。
            owner = window.parentWidget()
            while owner is not None and owner is not widget:
                owner = owner.parentWidget()
            if window is not widget and window.isVisible() and owner is widget:
                painter.drawPixmap(widget.mapFromGlobal(window.mapToGlobal(QtCore.QPoint())), window.grab())
        painter.end()
        return pixmap

    def capture():
        """表示中の実ウィジェットを撮影し時刻と段階を記録する。"""
        index = len(captured)
        path = frames_dir / ('frame_%05d.png' % index)
        if not grabReview().save(str(path)):
            raise RuntimeError('Could not capture UI frame')
        captured.append({'frame': index, 'seconds': round(time.monotonic() - started, 3), 'stage': stage})

    timer = QtCore.QTimer(widget)
    timer.setInterval(83)
    timer.timeout.connect(capture)

    def step(title):
        """動画内に今回の操作を表示する。

        Args:
            title (str): 段階の説明。
        """
        nonlocal stage
        stage = title
        caption.setText('QuickPathExplorer  |  Maya ' + str(cmds.about(version=True)) + '  |  ' + title)
        pause(1400)

    def choose(path):
        """クリック位置を示してから実フォルダー選択を行う。

        Args:
            path (Path): 選択対象。
        """
        index = widget.folderModel.index(str(path))
        view = [v for v in columns(widget) if v.rootIndex() == index.parent()][-1]
        view.scrollTo(index)
        point = view.viewport().mapTo(widget, view.visualRect(index).center())
        marker.move(point - QtCore.QPoint(14, 14))
        marker.raise_()
        marker.show()
        pause(450)
        click(widget, path)
        pause(450)
        marker.hide()
        checks.append(str(path.relative_to(root)))
        pause(1200)

    try:
        pause(600)
        timer.start()
        step('01  フォルダー選択 → 右に子フォルダーを表示')
        choose(root / 'Characters/Hero')
        widget.grab().save(str(movie / '01-children.png'))
        step('02  深い階層へ移動 → カラムが自動で狭まり画面内に収まる')
        choose(root / 'Characters/Hero/Rig')
        choose(root / 'Characters/Hero/Rig/Work')
        widget.grab().save(str(movie / '04-adaptive.png'))
        step('03  戻る・進む → 元の階層表示へ復帰')
        widget.backButton.click()
        inspectFolder(widget, root / 'Characters/Hero/Rig', require_visible=False)
        pause(1400)
        widget.forwardButton.click()
        inspectFolder(widget, root / 'Characters/Hero/Rig/Work', require_visible=False)
        pause(1400)
        step('04  兄弟フォルダーを切替 → 一覧内容と選択が一致')
        widget.navigate(str(root / 'Characters'))
        choose(root / 'Characters/Villain')
        choose(root / 'Characters/Hero')
        step('05  サイドバー表示・非表示')
        widget.sidebarButton.click()
        pause(1800)
        widget.grab().save(str(movie / '02-sidebar.png'))
        widget.sidebarButton.click()
        pause(1000)
        step('06  パス欄から日本語・空白を含むフォルダーへ移動')
        widget.address.setText(str(root / '日本語 素材'))
        widget.address.returnPressed.emit()
        inspectFolder(widget, root / '日本語 素材')
        choose(root / '日本語 素材/画像')
        step('07  縦スクロール位置を記憶 → 別フォルダーから戻る')
        widget.navigate(str(root / 'Library'))
        inspectFolder(widget, root / 'Library')
        view = [v for v in columns(widget) if Path(widget.folderModel.filePath(v.rootIndex())) == root / 'Library'][-1]
        waitFor(lambda: view.verticalScrollBar().maximum() > 0)
        view.verticalScrollBar().setValue(35)
        saved = view.verticalScrollBar().value()
        pause(1600)
        widget.navigate(str(root / 'Props'))
        pause(1400)
        widget.backButton.click()
        pause(500)
        view = [v for v in columns(widget) if Path(widget.folderModel.filePath(v.rootIndex())) == root / 'Library'][-1]
        assert view.verticalScrollBar().value() == saved
        pause(1600)
        step('08  再訪したフォルダーの子カラムを画面内に表示')
        widget.navigate(str(root / 'Library/Asset_69'))
        widget.columns.horizontalScrollBar().setValue(0)
        pause(1000)
        widget.navigate(str(root / 'Characters'))
        widget.navigate(str(root / 'Library'))
        widget.columns.scrollTo(widget.columns.currentIndex())
        choose(root / 'Library/Asset_69')
        step('09  検証完了 — 選択・内容・子カラムの表示を確認')
        widget.navigate(str(root / 'Characters'))
        choose(root / 'Characters/Hero')
        widget.grab().save(str(movie / '03-final.png'))
        pause(1600)
        step('10  右クリックから Import / Reference / Rename / 新規作成')
        selectFile(widget, root / 'Characters/Hero/hero_v001.ma')
        menu = widget.createFileMenu()
        menu.popup(widget.mapToGlobal(QtCore.QPoint(500, 320)))
        pause(1800)
        grabReview().save(str(movie / '05-context-menu.png'))
        menu.close()
        menu.deleteLater()
        step('11  新規テキストファイルを作成 → 名前変更')
        answerInput('review_notes.txt')
        triggerMenu(widget.createFileMenu(), 'New Text File…')
        waitFor(lambda: Path(widget.selectedPath()).name == 'review_notes.txt')
        pause(1400)
        answerInput('review_notes_v002.txt')
        triggerMenu(widget.createFileMenu(), 'Rename…')
        waitFor(lambda: Path(widget.selectedPath()).name == 'review_notes_v002.txt')
        pause(1500)
        step('12  Aaから文字サイズとUI倍率を変更・既定に戻す')
        widget.displayButton.click()
        widget.appearance.dialog.move(widget.mapToGlobal(QtCore.QPoint(700, 190)))
        pause(1500)
        widget.appearance.fontSpin.setValue(14)
        widget.appearance.scaleSpin.setValue(125)
        pause(1800)
        grabReview().save(str(movie / '06-display-settings.png'))
        widget.appearance._reset()
        pause(1500)
        widget.appearance.dialog.hide()
        timer.stop()
        capture()
        encoder = Path(os.environ['QPE_FFMPEG'])
        arguments = [str(encoder), '-hide_banner', '-nostdin', '-y', '-framerate', '12', '-i',
                     str(frames_dir / 'frame_%05d.png'), '-vf', 'scale=1280:900:force_original_aspect_ratio=decrease,pad=1280:900:(ow-iw)/2:(oh-ih)/2,setsar=1',
                     '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(movie / 'QuickPathExplorer-review.mp4')]
        with (movie / 'encode.log').open('w', encoding='utf-8') as log:
            subprocess.run(arguments, stdout=log, stderr=subprocess.STDOUT, check=True)
        result = {'status': 'passed', 'title': 'QuickPathExplorer 操作確認', 'maya': cmds.about(version=True),
                  'capture': 'actual Qt widget rendering during automated mouse input; yellow circle marks click location',
                  'fps': 12, 'frame_count': len(captured), 'duration_seconds': len(captured) / 12,
                  'checks': checks, 'frames': captured, 'video': str(movie / 'QuickPathExplorer-review.mp4')}
    except Exception:
        timer.stop()
        widget.grab().save(str(movie / 'failure.png'))
        result = {'status': 'error', 'stage': stage, 'checks': checks, 'error': traceback.format_exc()}
    (movie / 'recording.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {k: v for k, v in result.items() if k != 'frames'}
    (folder / 'result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    finished(summary)
