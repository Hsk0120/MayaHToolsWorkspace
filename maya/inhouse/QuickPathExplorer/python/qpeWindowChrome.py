"""Windows単体版のタブ段をウィンドウ操作領域として使う。"""
import ctypes
from ctypes import wintypes
import sys

from qpeQt import QtCore, QtGui, QtWidgets


class CaptionButton(QtWidgets.QAbstractButton):
    """配色をQPEに合わせた最小化・最大化・閉じるボタン。"""

    def __init__(self, chrome, command):
        """ホストを閉じず、所有する単体ウィンドウだけを操作する。"""
        super().__init__(chrome.strip)
        self.chrome = chrome
        self.command = command
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.clicked.connect(self.activate)
        self.refresh()

    def refresh(self):
        """最大化状態に合わせてアクセシビリティ名を更新する。"""
        label = {'minimize': 'Minimize', 'maximize': 'Restore' if self.window().isMaximized() else 'Maximize',
                 'close': 'Close window'}[self.command]
        self.setAccessibleName(label)
        self.setToolTip(label)
        self.update()

    def activate(self):
        """閉じる際もQPE既存のファイル操作保護を通す。"""
        window = self.chrome.window
        if self.command == 'close':
            window.close()
        elif self.command == 'minimize':
            window.showMinimized()
        elif window.isMaximized():
            window.showNormal()
        else:
            window.showMaximized()

    def enterEvent(self, event):
        """ホバー表示を更新する。"""
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        """ホバー表示を解除する。"""
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event):
        """OSのDPIはQtに委ね、タブ帯と同じ配色で線画を描く。"""
        painter = QtGui.QPainter(self)
        colors = self.chrome.strip.colors()
        color = QtGui.QColor(colors['text'])
        if self.underMouse() or self.isDown():
            background = QtGui.QColor('#c42b1c') if self.command == 'close' else QtGui.QColor(color)
            if self.command == 'close':
                color = QtGui.QColor('white')
            else:
                background.setAlpha(32 if self.isDown() else 20)
            painter.fillRect(self.rect(), background)
        painter.setPen(QtGui.QPen(color, 1))
        center = self.rect().center()
        x, y = center.x() - 5, center.y() - 5
        if self.command == 'close':
            painter.drawLine(x, y, x + 10, y + 10)
            painter.drawLine(x + 10, y, x, y + 10)
        elif self.command == 'minimize':
            painter.drawLine(x, y + 5, x + 10, y + 5)
        elif self.window().isMaximized():
            painter.drawPolyline([QtCore.QPoint(x + 3, y + 2), QtCore.QPoint(x + 3, y),
                                  QtCore.QPoint(x + 10, y), QtCore.QPoint(x + 10, y + 7),
                                  QtCore.QPoint(x + 8, y + 7)])
            painter.drawRect(x, y + 3, 7, 7)
        else:
            painter.drawRect(x, y, 10, 10)
        painter.end()


class WindowChrome(QtCore.QObject):
    """自分のHWNDだけの非クライアント領域を置換し、OSの移動・拡縮を保つ。"""

    @staticmethod
    def supported(window):
        """Mayaの子ウィンドウ・ドックと他OSには介入しない。"""
        return sys.platform == 'win32' and not window._maya and window.parentWidget() is None

    def __init__(self, window):
        """全体イベントフックを使わず対象ウィンドウだけを監視する。"""
        super().__init__(window)
        self.window = window
        self.strip = window.folderTabs.strip
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        self.user32.MonitorFromWindow.restype = wintypes.HANDLE
        self.user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        self.user32.IsZoomed.argtypes = [wintypes.HWND]
        self.user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        self.user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self.buttons = [CaptionButton(self, name) for name in ('minimize', 'maximize', 'close')]
        self.strip.chrome = self
        window.installEventFilter(self)
        self.strip.refresh()

    def reservedWidth(self):
        """操作ボタンと小さなドラッグ用余白をタブの計算から除く。"""
        return 3 * self.buttonWidth() + 24

    def buttonWidth(self):
        """OS論理ピクセルの幅を基本に、大きなUI設定では拡大する。"""
        return round(46 * max(1.0, self.strip.scale))

    def layoutButtons(self):
        """ウィンドウ幅・UI倍率の変更時にも右端を確保する。"""
        width = self.buttonWidth()
        for index, button in enumerate(self.buttons):
            button.setGeometry(self.strip.width() - (3 - index) * width, 0, width, self.strip.height())
            button.refresh()

    def eventFilter(self, watched, event):
        """生成後の枠更新と最大化アイコンの更新だけを扱う。"""
        if event.type() == QtCore.QEvent.Show:
            hwnd = int(self.window.winId())
            margins = (ctypes.c_int * 4)(1, 1, 1, 1)
            dwm = ctypes.WinDLL('dwmapi')
            dwm.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, ctypes.c_void_p]
            dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
            # WS_CAPTION/THICKFRAMEを保持してタスクバー・OSの移動/リサイズを使う。
            self.user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x37)
        if event.type() == QtCore.QEvent.WindowStateChange:
            self.layoutButtons()
        return False

    def nativeEvent(self, message):
        """自分のWindowsメッセージだけでタイトル領域と境界を処理する。"""
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x83 and msg.wParam:  # WM_NCCALCSIZE: 先頭RECTは新しい全体矩形。
            rect = wintypes.RECT.from_address(msg.lParam)
            if self.user32.IsZoomed(msg.hWnd):
                class MonitorInfo(ctypes.Structure):
                    """最大化時にタスクバーを覆わないための作業領域。"""
                    _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT),
                                ('work', wintypes.RECT), ('flags', wintypes.DWORD)]
                info = MonitorInfo()
                info.size = ctypes.sizeof(info)
                monitor = self.user32.MonitorFromWindow(msg.hWnd, 2)
                if self.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    rect.left, rect.top, rect.right, rect.bottom = info.work.left, info.work.top, info.work.right, info.work.bottom
            return True, 0
        if msg.message == 0x84:  # WM_NCHITTEST: 画面座標は符号付き物理ピクセル。
            point = wintypes.POINT(ctypes.c_short(msg.lParam & 0xffff).value,
                                  ctypes.c_short((msg.lParam >> 16) & 0xffff).value)
            self.user32.ScreenToClient(msg.hWnd, ctypes.byref(point))
            ratio = self.window.devicePixelRatioF()
            pos = QtCore.QPoint(round(point.x / ratio), round(point.y / ratio))
            x, y = pos.x(), pos.y()
            if not self.window.isMaximized():
                left, right = x < 5, x >= self.window.width() - 5
                top, bottom = y < 5, y >= self.window.height() - 5
                if top:
                    edge = 13 if left else 14 if right else 12
                elif bottom:
                    edge = 16 if left else 17 if right else 15
                else:
                    edge = 10 if left else 11 if right else 0
                if edge:
                    return True, edge
            local = self.strip.mapFrom(self.window, pos)
            if self.strip.rect().contains(local) and self.strip.childAt(local) is None:
                return True, 2  # HTCAPTION: ドラッグ・ダブルクリック・システムメニュー。
            # 元のタイトル位置でもタブやボタンへは通常のQt入力を配送する。
            return True, 1  # HTCLIENT
        return False, 0
