"""左サイドバー容量の非同期配送・行高・操作を隔離Qtで検証する。"""
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore, QtGui, QtWidgets
from qpe_ui_maya import pause, waitFor


def main(output_dir, finished=None):
    """専用設定で実容量と遅延/失敗注入を区別して検証・録画する。"""
    out = Path(output_dir).resolve()
    if ROOT / '.maya-output' not in out.parents:
        raise ValueError('Dedicated output required')
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    from quickPathExplorer import Explorer
    from qpeDrives import readCapacity, readDisplayName, DRIVE_ROLE, usageColor
    fixture = out / 'Project'
    fixture.mkdir(exist_ok=True)
    e = Explorer(maya=bool(finished))
    e.resize(1080, 760)
    e.show()
    e.navigate(str(fixture))
    e.setSidebarVisible(True)
    provider = e._driveCapacities
    path = Path(sys.executable).anchor.replace('\\', '/')
    caption = QtWidgets.QLabel(e)
    caption.setStyleSheet('background:#24414b;color:white;padding:10px;font-size:17px;')
    e.layout().insertWidget(0, caption)
    frames = out / 'frames'
    frames.mkdir(exist_ok=True)
    samples, checks = [], []

    def item():
        """再構築後のドライブ行をパスから取得する。"""
        for index in range(e.places.topLevelItemCount()):
            group = e.places.topLevelItem(index)
            if group.text(0) == 'Drives':
                return next(group.child(i) for i in range(group.childCount())
                            if group.child(i).data(0, QtCore.Qt.UserRole) == path)
        raise AssertionError('Drive group missing')

    def capture():
        """専用QPEウィンドウの描画だけを記録する。"""
        e.grab().save(str(frames / ('%05d.png' % len(samples))))
        samples.append(time.monotonic())

    def step(text):
        """実測と注入データを画面の字幕で区別する。"""
        caption.setText(text)
        pause(1000)

    timer = QtCore.QTimer(e)
    timer.setInterval(125)
    timer.timeout.connect(capture)
    gate = threading.Event()
    try:
        waitFor(lambda: path in provider.values)
        total, free = provider.values[path]
        actual = readCapacity(path)
        assert total == actual[0] and 0 <= free <= total
        assert 'free /' in item().text(0)
        assert 'Total capacity:' in item().toolTip(0) and 'Free space:' in item().toolTip(0)
        assert item().data(0, DRIVE_ROLE)['name'] == readDisplayName(path)
        assert path[:2] in item().text(0)
        checks.append('actual capacity and Windows Shell drive name/letter displayed')
        e.places.scrollToItem(item())
        assert e.places.property('qpeCurrentDrive') == path[:2].casefold()
        e.files.setFocus()
        pause(100)
        focused = QtWidgets.QApplication.focusWidget()
        e._loadPlaces()
        e._updateDriveCapacity(path, provider.values[path])
        assert QtWidgets.QApplication.focusWidget() is focused
        assert e.places.property('qpeCurrentDrive') == path[:2].casefold()
        checks.append('current drive highlight survives focus change, sidebar rebuild and capacity update')
        timer.start()
        step('Drive capacity | Actual local-drive free / total | Background refresh')
        e.grab().save(str(out / 'actual.png'))
        calls = []

        def delayed(query):
            """遅いドライブの結果をUI再構築後まで保留する。"""
            calls.append(query)
            gate.wait(5)
            return 2 * 1024 ** 4, 512 * 1024 ** 3

        with patch('qpeDrives.readCapacity', side_effect=delayed):
            provider.updated.pop(path, None)
            provider.request([path])
            waitFor(lambda: bool(calls))
            for _ in range(3):
                e._loadPlaces()
                pause(30)
            assert calls.count(path) == 1, calls
            assert path in provider.pending
            gate.set()
            waitFor(lambda: path not in provider.pending)
        assert '512 GB free / 2.00 TB' in item().text(0), item().text(0)
        checks.append('delayed result updates rebuilt row; repeated refresh does not duplicate request')
        for size in (10, 12, 16):
            e.appearance.apply(size, 100, save=False)
            e.outer.setSizes([185, 895, 0])
            e.places.scrollToItem(item())
            pause(150)
            height = e.places.visualItemRect(item()).height()
            assert height >= e.places.fontMetrics().height() * 3 + 6, (size, height)
        e.appearance.apply(12, 100, save=False)
        assert usageColor((100, 9)) == '#c42b1c'
        assert usageColor((100, 10)) == '#0078d4'
        step('Layout test values | 512 GB free / 2.00 TB | Windows drive name / usage bar / free and total')
        e.grab().save(str(out / 'layout.png'))
        checks.append('name/bar/capacity row height follows 10/12/16 px fonts without overlap')
        provider.values[path] = (100, 9)
        e._updateDriveCapacity(path, provider.values[path])
        e.places.scrollToItem(item())
        pause(200)
        crop = e.places.viewport().grab(e.places.visualItemRect(item())).toImage()
        red = sum(crop.pixelColor(x, y).name() == '#c42b1c'
                  for y in range(crop.height()) for x in range(crop.width()))
        assert red > 10, red
        step('Low-space test | Red usage bar below 10% free | Simulated capacity')
        checks.append('low-space bar rendered red below 10 percent free')
        if not e._maya:
            theme = e.appearance.theme
            previous = theme.mode
            for mode in ('light', 'dark'):
                theme.mode = mode
                theme.signature = None
                theme.refresh()
                step('Theme test | ' + mode + ' | Simulated low-space drive')
                e.grab().save(str(out / (mode + '.png')))
            theme.mode = previous
            theme.signature = None
            theme.refresh()
            checks.append('light and dark drive layout rendered')
        with patch('qpeDrives.readCapacity', side_effect=OSError('offline')):
            provider.updated.pop(path, None)
            provider.request([path])
            waitFor(lambda: path not in provider.pending)
        assert 'Capacity unavailable' in item().text(0)
        step('Failure test | Unavailable drive is never reported as zero free space')
        checks.append('unavailable capacity distinguished from zero free space')
        provider.updated.pop(path, None)
        provider.request([path])
        waitFor(lambda: path not in provider.pending)
        assert provider.values[path][0] == actual[0]
        e._visitPlace(item().data(0, QtCore.Qt.UserRole))
        assert e.currentDirectory == path
        e.navigate(str(fixture))
        checks.append('capacity row retains normal drive navigation')
        alternatives = [d.absoluteFilePath() for d in QtCore.QDir.drives()
                        if d.absoluteFilePath().casefold() != path.casefold()]
        if alternatives:
            # 別ドライブはルートの読取だけ。設定と履歴は専用出力内へ保存する。
            other = alternatives[0]
            e.folderTabs.add()
            assert e.navigate(other)
            assert e.places.property('qpeCurrentDrive') == other[:2].casefold()
            step('Current drive follows folder navigation | Other drive (read only)')
            e._back()
            assert e.places.property('qpeCurrentDrive') == path[:2].casefold()
            e._forward()
            assert e.places.property('qpeCurrentDrive') == other[:2].casefold()
            e.folderTabs.bar.setCurrentIndex(0)
            assert e.places.property('qpeCurrentDrive') == path[:2].casefold()
            checks.append('drive highlight follows navigation, Back/Forward and tab switching')
        e.setSidebarVisible(False)
        with patch('quickPathExplorer.os.path.isdir', side_effect=AssertionError('hidden sidebar disk query')):
            e._loadPlaces()
        e.setSidebarVisible(True)
        assert e.places.property('qpeCurrentDrive') == path[:2].casefold()
        checks.append('hidden sidebar refresh performs no filesystem lookup; reopen preserves highlight')
        e.folderTabs.saveSession()
        expected_path, expected_tabs = e.currentDirectory, e.folderTabs.bar.count()
        with patch.object(e, 'navigate', wraps=e.navigate) as navigation:
            e.restoreStartup()
            assert navigation.call_count == 1, navigation.call_count
        assert e.currentDirectory == expected_path and e.folderTabs.bar.count() == expected_tabs
        with patch.object(e, 'navigate', wraps=e.navigate) as navigation:
            e.restoreStartup(str(fixture))
            assert navigation.call_count == 1
        checks.append('startup restores saved tabs with one navigation; explicit folder overrides restoration')
        step('PASS | Actual capacities restored | Drive navigation unchanged')
        result = dict(status='passed', checks=checks, input='Qt programmatic', actualTotal=total)
    except Exception:
        result = dict(status='failed', checks=checks, error=traceback.format_exc())
    finally:
        gate.set()
        timer.stop()
        (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
        (out / 'frames.json').write_text(json.dumps(samples), encoding='utf8')
        e.close()
        e.deleteLater()
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(sys.argv[1])
    QtCore.QThreadPool.globalInstance().waitForDone(10000)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result['status'] == 'passed' else 1)
