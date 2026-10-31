"""単体Windowsのタブ統合枠・配色とMayaへの非適用を検証する。"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback

from qpe_ui_maya import pause, waitFor
from qpeQt import QtCore, QtGui, QtWidgets


def main(output_dir, finished=None):
    """専用設定とフォルダーだけで実ウィンドウとWindowsメッセージを検証する。"""
    from quickPathExplorer import Explorer
    import qpeTheme
    from qpeSettings import writeSettings
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    checks = []
    windows = []
    original_settings = os.environ.get('QPE_SETTINGS_FILE')
    reader = qpeTheme.windowsColors
    app = QtWidgets.QApplication.instance()
    original_palette = QtGui.QPalette(app.palette())
    temporary_dir = tempfile.TemporaryDirectory(prefix='chrome-', dir=str(out))
    temporary = temporary_dir.name
    try:
        os.environ['QPE_SETTINGS_FILE'] = str(Path(temporary) / 'settings.json')
        qpeTheme.windowsColors = lambda: (False, '#0078d4')
        widget = Explorer(maya=bool(finished))
        windows.append(widget)
        widget.resize(1000, 700)
        widget.show()
        widget.navigate(temporary)
        pause(150)
        assert widget.appearance.theme.mode == 'system'
        assert not widget.appearance.theme.light
        checks.append('new settings default to Windows system theme')
        if finished:
            assert widget.windowChrome is None
            assert widget.appearance.theme.colors['accent'] == '#326c7b'
            checks.append('Maya Explorer has no native chrome and retains fixed host palette')
        else:
            chrome = widget.windowChrome
            assert chrome is not None
            strip = widget.folderTabs.strip
            for _ in range(11):
                widget.folderTabs.add()
            for scale in (75, 100, 200):
                widget.appearance.apply(12, scale, save=False)
                for width in (560, 1000, 1600):
                    widget.resize(width, 700)
                    pause(70)
                    assert strip.bar.geometry().right() < strip.addButton.x()
                    assert strip.addButton.geometry().right() < chrome.buttons[0].x()
                    assert chrome.buttons[-1].geometry().right() < strip.width()
                    assert strip.mapTo(widget, QtCore.QPoint()).y() < strip.height()
            checks.append('12 tabs at 560/1000/1600 widths and 75/100/200% UI never overlap caption controls')
            widget.appearance.apply(12, 100, save=False)
            widget.resize(1000, 700)
            chrome.buttons[1].click()
            waitFor(widget.isMaximized)
            pause(100)
            assert chrome.buttons[1].accessibleName() == 'Restore'
            assert widget.screen().availableGeometry().contains(widget.geometry().center())
            # Win32のクライアント領域が最大化時に作業領域を超えない。
            rect = wintypes.RECT()
            chrome.user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            chrome.user32.GetClientRect(int(widget.winId()), ctypes.byref(rect))
            available = widget.screen().availableGeometry()
            assert rect.bottom / widget.devicePixelRatioF() <= available.height() + 2
            chrome.buttons[1].click()
            waitFor(lambda: not widget.isMaximized())
            assert chrome.buttons[1].accessibleName() == 'Maximize'
            chrome.buttons[0].click()
            waitFor(widget.isMinimized)
            widget.showNormal()
            pause(100)
            checks.append('maximize/restore/minimize/restore and maximized work area')
            # 実OS入力ではなくnativeEventへのメッセージ試験。負座標にも対応する。
            chrome.user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
            def hit_test(point):
                """ウィジェット座標から物理画面座標へ変換し境界判定する。"""
                point = wintypes.POINT(round(point.x() * widget.devicePixelRatioF()),
                                      round(point.y() * widget.devicePixelRatioF()))
                chrome.user32.ClientToScreen(int(widget.winId()), ctypes.byref(point))
                msg = wintypes.MSG()
                msg.hWnd, msg.message = int(widget.winId()), 0x84
                msg.lParam = (point.x & 0xffff) | ((point.y & 0xffff) << 16)
                return chrome.nativeEvent(ctypes.addressof(msg))[1]
            assert hit_test(QtCore.QPoint(1, 1)) == 13
            assert hit_test(QtCore.QPoint(widget.width() - 1, widget.height() - 1)) == 17
            assert hit_test(strip.mapTo(widget, strip.addButton.geometry().center())) == 1
            assert hit_test(strip.mapTo(widget, chrome.buttons[1].geometry().center())) == 1
            blank = QtCore.QPoint(chrome.buttons[0].x() - 10, strip.height() // 2)
            assert hit_test(strip.mapTo(widget, blank)) == 2
            checks.append('resize corners, draggable gap, tabs and caption button input boundaries')
            for light in (True, False):
                qpeTheme.windowsColors = lambda light=light: (light, '#0078d4')
                widget.appearance.theme.refresh()
                assert widget.appearance.theme.light == light
                widget.grab().save(str(out / ('light.png' if light else 'dark.png')))
            assert app.palette() == original_palette
            checks.append('system light/dark refresh without changing application palette')
            # 閉じるボタンも実行中ファイル操作の保護を飛ばさない。
            widget.organizer.task = object()
            chrome.buttons[2].click()
            assert widget.isVisible()
            widget.organizer.task = None
            chrome.buttons[2].click()
            assert not widget.isVisible()
            checks.append('close button respects active-operation close guard')
            writeSettings({'standaloneTheme': 'light'})
            explicit = Explorer()
            windows.append(explicit)
            assert explicit.appearance.theme.mode == 'light' and explicit.appearance.theme.light
            maya = Explorer(maya=True)
            windows.append(maya)
            assert maya.windowChrome is None and not maya.appearance.theme.light
            owner = QtWidgets.QWidget()
            child = Explorer(parent=owner)
            windows.append(child)
            assert child.windowChrome is None
            checks.append('explicit theme preserved; Maya and embedded Explorer excluded')
        result = dict(status='passed', qt=QtCore.qVersion(), evidence='Qt program operations / Win32 message assertions, not OS input', checks=checks)
    except Exception:
        result = dict(status='error', checks=checks, error=traceback.format_exc())
    finally:
        for widget in windows:
            widget.close()
        temporary_dir.cleanup()
        qpeTheme.windowsColors = reader
        if original_settings is None:
            os.environ.pop('QPE_SETTINGS_FILE', None)
        else:
            os.environ['QPE_SETTINGS_FILE'] = original_settings
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    sys.exit(0 if main(sys.argv[1])['status'] == 'passed' else 1)
