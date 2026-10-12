"""探索から保存までのユーザー操作を検証し、自己レビュー用に録画する。"""
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpe_ui_maya import pause, waitFor, selectFile
from qpe_ui_navigation import click, columns, inspectFolder, visibleWidth
from qpe_ui_context import answerInput, triggerMenu
from qpeQt import QtCore, QtGui, QtWidgets, QtTest, shiboken


def main(output_dir, finished=None):
    """専用データでUXの各場面を実行し、結果と映像を保存する。

    Args:
        output_dir (Path): 証跡先。
        finished (callable | None): 専用Mayaの終了通知。

    Returns:
        dict: 検証結果。
    """
    folder = Path(output_dir).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(folder / 'settings.json')
    root = folder / 'StudioProject'
    hero = root / 'Assets/Characters/Hero'
    for part in ('Assets/Characters/Hero/Rig/Work', 'Assets/Characters/Villain/Model',
                 'Assets/VeryLongEnvironmentFolderNameForTooltip', 'Exports', 'Empty'):
        (root / part).mkdir(parents=True, exist_ok=True)
    (hero / 'notes_v001.txt').write_text('Hero rig review notes', encoding='utf-8')
    (hero / 'readme.txt').write_text('Review source files', encoding='utf-8')
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
    checks, frames = [], []
    stage = 'setup'
    recording = bool(os.environ.get('QPE_FFMPEG'))
    frames_dir = folder / 'frames'
    if recording:
        frames_dir.mkdir(exist_ok=True)

    def grab():
        """Explorerと所有するポップアップを実描画で取得する。

        Returns:
            QPixmap: UI画像。
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
        """一定間隔で映像フレームを保存する。"""
        path = frames_dir / ('%05d.png' % len(frames))
        grab().save(str(path))
        frames.append({'frame': len(frames), 'stage': stage})

    timer = QtCore.QTimer(widget)
    timer.setInterval(100)
    timer.timeout.connect(capture)

    def step(title):
        """人が追える速度で操作の目的を示す。

        Args:
            title (str): 字幕。
        """
        nonlocal stage
        stage = title
        caption.setText('QuickPathExplorer  |  ' + title)
        pause(1300 if recording else 80)

    def screenshot(name):
        """直前の描画と非同期更新を待って静止画を保存する。

        Args:
            name (str): 保存名。
        """
        pause(850 if recording else 100)
        grab().save(str(folder / name))

    try:
        pause(300)
        if recording:
            timer.start()
        step('01  このプロジェクトを探索の起点にする')
        triggerMenu(widget.createFolderMenu(str(root)), 'Explore from this folder')
        inspectFolder(widget, root)
        assert Path(widget.folderModel.filePath(widget.columns.rootIndex())) == root
        assert widget.rootButton.isVisible()
        assert len(columns(widget)) == 1
        screenshot('01-project-root.png')
        checks.append('project root hides irrelevant ancestors')

        step('02  フォルダーを掘る — 近い階層は読みやすい幅を維持')
        for path in (root / 'Assets', root / 'Assets/Characters', hero, hero / 'Rig', hero / 'Rig/Work'):
            click(widget, path)
            assert Path(widget.browseRoot) == root
            pause(350 if recording else 30)
        for view in columns(widget)[-4:]:
            assert view.width() >= widget.columns.contentWidth(view.rootIndex())
        assert not any(widget.columns.emptyChild(view.rootIndex()) for view in columns(widget))
        waitFor(lambda: 'No files' in widget.emptyFiles.text())
        assert 'Work' in widget.folderLabel.text() and '0 files' in widget.folderLabel.text()
        screenshot('02-readable-columns.png')
        checks.append('near columns remain wide and empty state distinguishes files and subfolders')

        step('03  兄弟フォルダーの切替でもカラム位置が動かない')
        widget.navigate(str(hero))
        pause(80)
        before = [(v.x(), v.width()) for v in columns(widget)]
        click(widget, root / 'Assets/Characters/Villain')
        after = [(v.x(), v.width()) for v in columns(widget)]
        assert before[:-1] == after[:-1], (before, after)
        click(widget, hero)
        checks.append('sibling switching preserves column positions')

        step('04  上下のフォルダー名・ファイル件数・検索結果を確認')
        waitFor(lambda: '2 files' in widget.folderLabel.text())
        widget.search.setText('not_present')
        waitFor(lambda: '0 files' in widget.folderLabel.text())
        assert 'No matching' in widget.emptyFiles.text()
        pause(650 if recording else 50)
        widget.search.clear()
        waitFor(lambda: '2 files' in widget.folderLabel.text())
        long_index = widget.folderModel.index(str(root / 'Assets/VeryLongEnvironmentFolderNameForTooltip'))
        assert 'VeryLongEnvironmentFolderNameForTooltip' in str(long_index.data(QtCore.Qt.ToolTipRole))
        checks.append('file counts filtering and full name tooltip')

        step('05  F2で一覧内リネーム — 拡張子は選択しない')
        selectFile(widget, hero / 'notes_v001.txt')
        widget.window().raise_()
        widget.window().activateWindow()
        widget.files.setFocus()
        pause(100)
        QtTest.QTest.keyClick(widget.files, QtCore.Qt.Key_F2)
        editor = widget._inlineRename
        assert editor is not None and editor.isVisible()
        assert editor.selectedText() == 'notes_v001'
        screenshot('03-inline-rename.png')
        QtTest.QTest.keyClicks(editor, 'notes_v002')
        QtTest.QTest.keyClick(editor, QtCore.Qt.Key_Return)
        waitFor(lambda: (hero / 'notes_v002.txt').exists())
        assert (hero / 'notes_v002.txt').read_text(encoding='utf-8') == 'Hero rig review notes'
        checks.append('inline rename preserves extension and file bytes')

        step('06  新規テキスト作成とMayaシーン保存を分ける')
        answerInput('review_log')
        triggerMenu(widget.createFileMenu(), 'New Text File…')
        assert (hero / 'review_log.txt').exists()
        answerInput('fake_scene.ma')
        triggerMenu(widget.createFileMenu(), 'New Text File…')
        assert not (hero / 'fake_scene.ma').exists()
        widget.status.hide()
        checks.append('text creation cannot create a misleading empty Maya scene')

        step('07  ★からお気に入りへ移動 — サイドバーは閉じたまま')
        widget.addFavorite()
        widget.navigate(str(root / 'Empty'))
        menu = widget.createLocationsMenu()
        menu.popup(widget.mapToGlobal(QtCore.QPoint(700, 120)))
        screenshot('04-quick-locations.png')
        menu.close()
        triggerMenu(menu, 'Hero')
        inspectFolder(widget, hero)
        assert not widget.places.isVisible()
        checks.append('quick locations works without sidebar')

        step('08  Aaで標準・大きめ・特大を切替')
        widget.displayButton.click()
        widget.appearance.dialog.move(widget.mapToGlobal(QtCore.QPoint(640, 130)))
        widget.appearance.setPreset(1)
        pause(600 if recording else 50)
        widget.appearance.setPreset(2)
        assert widget.appearance.uiPercent == 150
        assert widget.appearance.presetCombo.currentText() == 'Largest'
        screenshot('05-size-presets.png')
        widget.appearance.setPreset(0)
        widget.appearance.dialog.hide()
        checks.append('size presets reset without accumulated scaling')

        if finished:
            step('09  選択ファイルの読込と現在シーンの保存を別タブに')
            cmds.file(new=True, force=True)
            cmds.polyCube(name='uxReviewCube')
            widget.fileName.setText('hero_review')
            selectFile(widget, hero / 'readme.txt')
            assert widget.fileName.text() == 'hero_review'
            assert widget.readTarget.text() == 'readme.txt'
            assert widget.operationTabs.currentWidget() is widget.readPanel
            screenshot('06-selected-file.png')
            triggerMenu(widget.createFolderMenu(str(root / 'Exports')), 'Save current scene here…')
            assert widget.operationTabs.currentWidget() is widget.savePanel
            assert not (root / 'Exports/hero_review.ma').exists()
            assert 'Exports' in widget.saveDestination.text()
            screenshot('07-save-destination.png')
            widget.actionButtons['saveAs'].click()
            assert (root / 'Exports/hero_review.ma').stat().st_size > 0
            assert Path(cmds.file(query=True, sceneName=True)) == root / 'Exports/hero_review.ma'
            assert 'hero_review.ma' in widget.sceneTarget.text()
            checks.append('save preparation is non-destructive and save action uses shown destination')

        step('10  起点を解除して全体の階層へ戻る')
        widget.rootButton.click()
        assert not widget.browseRoot and widget.rootButton.text() == 'Focus folder'
        assert len(columns(widget)) > 3
        inspectFolder(widget, Path(widget.currentDirectory))
        widget.setBrowseRoot(str(root))
        widget.navigate(str(hero))
        widget.operationTabs.setCurrentWidget(widget.readPanel)
        assert Path(widget.browseRoot) == root
        screenshot('08-final.png')
        checks.append('scope can be cleared and restored')
        result = {'status': 'passed', 'checks': checks}
    except Exception:
        result = {'status': 'error', 'stage': stage, 'checks': checks, 'error': traceback.format_exc()}
        screenshot('failure.png')
    timer.stop()
    if recording and frames:
        video = folder / 'QuickPathExplorer-UX-review.mp4'
        args = [os.environ['QPE_FFMPEG'], '-hide_banner', '-nostdin', '-y', '-framerate', '10',
                '-i', str(frames_dir / '%05d.png'), '-vf',
                'scale=1280:940:force_original_aspect_ratio=decrease,pad=1280:940:(ow-iw)/2:(oh-ih)/2,setsar=1',
                '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(video)]
        with (folder / 'encode.log').open('w') as log:
            subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True)
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
