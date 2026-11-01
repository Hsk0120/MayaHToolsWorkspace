"""ドライブ容量をGUIから離して取得し、短時間キャッシュする。"""
import queue
import os
import shutil
import threading
import time

from qpeQt import QtCore, QtGui, QtWidgets


DRIVE_ROLE = QtCore.Qt.UserRole + 41


def readDisplayName(path):
    """ワーカー内でWindows Shellのローカライズされたドライブ名を取得する。"""
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes

        class ShellFileInfo(ctypes.Structure):
            """SHGetFileInfoWが名前を書き込む領域。アイコン取得は要求しない。"""
            _fields_ = [('icon', wintypes.HANDLE), ('index', ctypes.c_int),
                        ('attributes', wintypes.DWORD), ('displayName', wintypes.WCHAR * 260),
                        ('typeName', wintypes.WCHAR * 80)]

        shell = ctypes.WinDLL('shell32', use_last_error=True)
        query = shell.SHGetFileInfoW
        query.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ShellFileInfo),
                          wintypes.UINT, wintypes.UINT]
        query.restype = ctypes.c_size_t
        info = ShellFileInfo()
        ole = ctypes.OleDLL('ole32')
        ole.CoInitialize.argtypes = [ctypes.c_void_p]
        ole.CoUninitialize.argtypes = []
        ole.CoUninitialize.restype = None
        ole.CoInitialize(None)
        try:
            if query(path.replace('/', '\\'), 0, ctypes.byref(info), ctypes.sizeof(info), 0x200):
                if info.displayName:
                    return info.displayName
        finally:
            ole.CoUninitialize()
    return path.rstrip('/\\')


def readCapacity(path):
    """ドライブ全体と利用者が使える空き容量をバイトで返す。"""
    usage = shutil.disk_usage(path)
    return usage.total, usage.free


class DriveCapacities(QtCore.QObject):
    """低速・切断済みドライブでもナビゲーションを待たせない容量取得。"""
    changed = QtCore.Signal(str, object)

    def __init__(self, view):
        """結果配送は所有ビューのGUIスレッドだけで行う。"""
        super().__init__(view)
        self.values = {}
        self.names = {}
        self.updated = {}
        self.pending = set()
        self.paths = []
        self.results = queue.Queue()
        self.poll = QtCore.QTimer(self)
        self.poll.setInterval(100)
        self.poll.timeout.connect(self._collect)
        self.refresh = QtCore.QTimer(self)
        self.refresh.setInterval(30000)
        self.refresh.timeout.connect(self._refresh)
        self.refresh.start()

    def request(self, paths):
        """同じドライブの重複取得を避け、30秒間は結果を再利用する。"""
        self.paths = list(dict.fromkeys(paths))
        now = time.monotonic()
        for path in self.paths:
            if path in self.pending or now - self.updated.get(path, -60) < 30:
                continue
            self.pending.add(path)
            # ワーカーはQt/ビュー/selfに触れず、値だけをqueueへ返す。
            # 到達不能なネットワーク待ちがMaya/単体版の終了を妨げない。
            threading.Thread(target=self._read, args=(path, self.results), daemon=True).start()
        if self.pending:
            self.poll.start()

    @staticmethod
    def _read(path, results):
        """取得できない媒体は容量不明とし、空き0として誤表示しない。"""
        try:
            value = readCapacity(path)
            if value[0] <= 0 or value[1] < 0:
                value = None
        except OSError:
            value = None
        try:
            name = readDisplayName(path)
        except OSError:
            name = path.rstrip('/\\')
        results.put((path, value, name))

    def _collect(self):
        """遅延結果を現在の行へ通知し、削除済みTreeItemを保持しない。"""
        while True:
            try:
                path, value, name = self.results.get_nowait()
            except queue.Empty:
                break
            self.pending.discard(path)
            self.values[path] = value
            self.names[path] = name
            self.updated[path] = time.monotonic()
            if path in self.paths:
                self.changed.emit(path, value)
        if not self.pending:
            self.poll.stop()

    def _refresh(self):
        """サイドバーが表示されている間だけ容量を再取得する。"""
        if self.parent().isVisible():
            self.request(self.paths)


def capacityText(value):
    """Windows表記に合わせた空き/総容量と、補足のツールチップを返す。"""
    if value is None:
        return 'Capacity unavailable', 'Capacity unavailable'
    total, free = value
    locale = QtCore.QLocale.system()
    # 標準幅のサイドバーでもGBの小数桁でラベルが省略されないようにする。
    total_text = locale.formattedDataSize(total, 2 if total >= 1024 ** 4 else 0, QtCore.QLocale.DataSizeTraditionalFormat)
    free_text = locale.formattedDataSize(free, 2 if free >= 1024 ** 4 else 0, QtCore.QLocale.DataSizeTraditionalFormat)
    return '{} free / {}'.format(free_text, total_text), 'Total capacity: {}\nFree space: {}'.format(total_text, free_text)


def driveHeight(option):
    """名前・バー・容量2行が文字倍率に追従する高さを返す。"""
    line = option.fontMetrics.height()
    return line * 3 + max(6, line // 3) + 16


def usageColor(value):
    """空き10%未満を赤、それ以外を青で表す。取得不可はバーを塗らない。"""
    return '#c42b1c' if value and value[1] / value[0] < 0.1 else '#0078d4'


def paintDrive(painter, option, index, view):
    """標準選択背景の上へ名前・使用量バー・容量を整列して描く。"""
    data = index.data(DRIVE_ROLE)
    painter.save()
    painter.setClipRect(option.rect)
    painter.setFont(option.font)
    line = option.fontMetrics.height()
    icon_size = max(16, line)
    left = option.rect.left() + 4
    top = option.rect.top() + 5
    icon = index.data(QtCore.Qt.DecorationRole)
    if icon:
        icon.paint(painter, QtCore.QRect(left, top, icon_size, icon_size))
    text_left = left + icon_size + 6
    width = max(0, option.rect.right() - text_left - 6)
    selected = bool(option.state & QtWidgets.QStyle.State_Selected)
    color = option.palette.color(QtGui.QPalette.HighlightedText if selected else QtGui.QPalette.Text)
    painter.setPen(color)
    title = option.fontMetrics.elidedText(data['name'], QtCore.Qt.ElideMiddle, width)
    painter.drawText(QtCore.QRect(text_left, top, width, line), QtCore.Qt.AlignVCenter, title)
    bar = QtCore.QRect(text_left, top + line + 4, width, max(6, line // 3))
    background = QtGui.QColor('#dddddd' if color.lightnessF() < 0.5 else '#555555')
    painter.fillRect(bar, background)
    value = data['value']
    if value:
        used = max(0.0, min(1.0, 1.0 - value[1] / value[0]))
        filled = QtCore.QRect(bar)
        filled.setWidth(round(bar.width() * used))
        painter.fillRect(filled, QtGui.QColor(usageColor(value)))
    muted = QtGui.QColor(color)
    muted.setAlpha(210)
    painter.setPen(muted)
    # 狭い標準幅でも空きと総容量を途中省略しないよう別行にする。
    labels = data['summary'].replace(' free / ', ' free\n')
    if value:
        labels += ' total'
    for row, text in enumerate(labels.splitlines()):
        painter.drawText(QtCore.QRect(text_left, bar.bottom() + 4 + row * line, width, line),
                         QtCore.Qt.AlignVCenter, option.fontMetrics.elidedText(text, QtCore.Qt.ElideRight, width))
    painter.restore()
