"""専用データでモダン表示の操作・倍率・設定保持を検証し録画する。"""
import json
import os
from pathlib import Path
import sys
import traceback
from qpe_ui_maya import pause, waitFor, selectFile
from qpeQt import QtCore, QtGui, QtWidgets, QtTest


def main(output_dir, finished=None):
    """作業中シーンとユーザー設定を触らず、表示の回帰を検出する。"""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    from quickPathExplorer import Explorer
    root = out / 'Project'
    for folder in ('Characters/Hero/Scenes', 'Characters/Hero/Textures', 'Environments', 'Props'):
        (root / folder).mkdir(parents=True, exist_ok=True)
    directory = root / 'Characters/Hero/Scenes'
    for i in range(36):
        (directory / ('Hero_animation_%02d.ma' % i)).write_text('//Maya ASCII 2022 scene\n', encoding='utf8')
    (directory / '制作メモ.txt').write_text('Animation review', encoding='utf8')
    e = Explorer(maya=bool(finished))
    e.resize(1360, 880)
    e.show()
    e.setBrowseRoot(str(root))
    e.navigate(str(directory))
    e.addFavoritePath(str(root / 'Characters'))
    e.setSidebarVisible(True)
    recorder = None
    checks = []
    try:
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 37)
        selectFile(e, directory / 'Hero_animation_02.ma')
        if os.environ.get('QPE_RECORD_MODERN'):
            from qpe_record_full import Recorder
            os.environ['QPE_REVIEW_CHAPTER'] = 'modern-' + ('maya' if finished else 'windows')
            recorder = Recorder(e, out)

        def stage(code, title):
            """実描画の静止画と、任意の実時間動画を記録する。"""
            if recorder:
                recorder.step(code, title)
                recorder.hold()
            else:
                pause(200)
                e.grab().save(str(out / (code + '.png')))

        stage('01', '文字・余白・操作部品を統一 / カラムの探索を維持')
        original_width = e.width()
        e.modern.showOptions()
        pause(150)
        assert e.modern.popup.isVisible() and e.organizer.workspace.mode.isVisible()
        stage('02', 'View に表示設定を集約 / Escape で戻る')
        QtTest.QTest.keyClick(e.organizer.workspace.mode, QtCore.Qt.Key_Escape)
        pause(100)
        assert not e.modern.popup.isVisible()
        assert e.width() == original_width
        checks.append('View popup opens with accessible controls and Escape closes without resizing')
        e.search.setText('animation_02')
        e.fileFilter.setCurrentIndex(1)
        pause(200)
        assert e.modern.chips[0][1].isVisible() and e.modern.chips[1][1].isVisible()
        stage('03', '適用中の条件を表示 / × で個別解除')
        QtTest.QTest.mouseClick(e.modern.chips[0][1], QtCore.Qt.LeftButton)
        assert e.search.text() == '' and e.fileFilter.currentIndex() == 1
        QtTest.QTest.mouseClick(e.modern.chips[1][1], QtCore.Qt.LeftButton)
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 37)
        assert not e.modern.chipScroll.isVisible()
        assert e.files.columnWidth(0) > 300
        checks.append('filter chips clear only their own condition and restore flexible filename width')
        e.setInspectorVisible(True)
        selectFile(e, directory / 'Hero_animation_02.ma')
        stage('04', '右ペインは情報から操作へ / ファイル名・基本情報・Open')
        if finished:
            assert not e.readOptions.isVisible()
            e.readOptionsToggle.click()
            pause(100)
            assert e.readOptions.isVisible()
            e.readOptions.controls['import']['mode'].setCurrentIndex(1)
            e.readOptions.controls['import']['name'].setText('hero')
            stage('05', 'Import / Reference 設定を必要時に展開')
            e.readOptionsToggle.click()
            assert e.readOptions.fileArguments('import', str(directory / 'Hero_animation_02.ma'))['namespace'] == ':hero'
            checks.append('collapsed read options retain namespace and expand without executing an import')
        e.setInspectorVisible(False)
        before = e.files.visualRect(e.files.currentIndex()).height()
        e.appearance.setDensity(1)
        pause(150)
        assert e.files.visualRect(e.files.currentIndex()).height() > before
        for view in e.columns.findChildren(QtWidgets.QListView):
            if view.isVisible():
                assert view.property('qpeRowHeight') == e.files.property('qpeRowHeight')
        stage('06', '文字サイズと独立した行間 / Comfortable')
        e.appearance.setDensity(0)
        if not finished:
            for theme in ('dark', 'light'):
                state = e.currentDirectory, e.selectedPaths()
                e.appearance.theme.setMode(theme)
                pause(100)
                assert state == (e.currentDirectory, e.selectedPaths())
                stage('07-' + theme, '同じレイアウトでライト / ダーク切替')
        checks.append('density changes row height; theme preserves selection and location')
        for percentage in (150, 200, 100):
            e.appearance.apply(13, percentage, save=False)
            pause(200)
            assert e.files.visualRect(e.files.currentIndex()).height() >= e.files.fontMetrics().height()
            assert e.address.height() >= e.address.fontMetrics().height() + 4
            if percentage == 200:
                e.setInspectorVisible(True)
                if finished:
                    e.readOptionsToggle.setChecked(True)
                pause(100)
                assert e.inspectorScroll.widget().height() >= e.inspectorScroll.viewport().height()
                assert e.actionsPanel.height() == e.vertical.height()
                if finished:
                    e.readOptionsToggle.setChecked(False)
                e.setInspectorVisible(False)
            e.grab().save(str(out / ('scale-%s.png' % percentage)))
        checks.append('100/150/200 percent text and rows fit without double application')
        e.resize(780, 700)
        e.search.setText('very_long_search_filter_for_layout_check')
        e.fileFilter.setCurrentIndex(1)
        e.organizer.workspace.flat.setChecked(True)
        e.organizer.workspace.group.setCurrentIndex(1)
        pause(300)
        assert e.width() <= 780, e.width()
        # 条件がまだ収まる幅ならスクロールは不要。さらに狭いviewportで発生を検証する。
        e.modern.chipScroll.setMaximumWidth(300)
        pause(100)
        assert e.modern.chipScroll.horizontalScrollBar().maximum() > 0
        e.modern.chipScroll.setMaximumWidth(16777215)
        stage('08', '狭い幅でも条件がウィンドウを押し広げない')
        checks.append('many filter chips scroll in narrow windows instead of increasing minimum width')
        e.search.clear()
        e.fileFilter.setCurrentIndex(0)
        e.organizer.workspace.flat.setChecked(False)
        e.organizer.workspace.group.setCurrentIndex(0)
        e.resize(1360, 880)
        pause(200)
        stage('09', '完了 / 既存のカラム操作・関連付けアプリで開く動作は維持')
        result = dict(status='passed', checks=checks)
        if recorder:
            result['video'] = recorder.finish()
    except Exception:
        if recorder:
            recorder.timer.stop()
        result = dict(status='error', checks=checks, error=traceback.format_exc())
    e.grab().save(str(out / 'overview.png'))
    e.close()
    pause(200)
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(sys.argv[1])
    sys.exit(0 if result['status'] == 'passed' else 1)
