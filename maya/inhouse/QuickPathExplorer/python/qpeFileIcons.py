"""OSの関連付けを使うファイルアイコン。"""
import os
import ctypes
from ctypes import wintypes
from collections import OrderedDict
from qpeQt import QtCore, QtGui, QtWidgets


class FileIcons:
    """同じウィンドウの一覧・Recent・サムネイルで共有するGUI専用LRU。

    拡張子だけへ集約せず、ショートカットや実行ファイル固有のアイコンを保持する。
    上限到達時は最も古く参照した項目だけを捨て、全消去による再取得を避ける。
    """

    def __init__(self):
        """GUIスレッドで使用するプロバイダーを保持する。"""
        self._provider = QtWidgets.QFileIconProvider()
        self._cache = OrderedDict()
        self.capacity = 2048

    def icon(self, path):
        """ファイルごとの関連付け・ショートカット等を反映する。

        Args:
            path (str): 対象ファイル。

        Returns:
            QIcon: WindowsではShellのアイコン。サムネイルは含まない。
        """
        info = QtCore.QFileInfo(path)
        key = (os.path.normcase(info.absoluteFilePath()), info.lastModified().toMSecsSinceEpoch(), info.size())
        if key not in self._cache:
            native = windowsIcon(info.absoluteFilePath()) if os.name == 'nt' else QtGui.QIcon()
            self._cache[key] = native if not native.isNull() else self._provider.icon(info)
            while len(self._cache) > self.capacity:
                self._cache.popitem(last=False)
        self._cache.move_to_end(key)
        return self._cache[key]


class _ShellInfo(ctypes.Structure):
    """Shell APIのアイコン・表示名・種類の出力領域。"""
    _fields_ = [('hIcon', wintypes.HANDLE), ('iIcon', ctypes.c_int),
                ('attributes', wintypes.DWORD), ('name', wintypes.WCHAR * 260),
                ('typeName', wintypes.WCHAR * 80)]


def windowsIcon(path, directory=False):
    """Windowsの関連付けアイコンを取得し、所有するHICONを必ず解放する。

    Args:
        path (str): ファイルの絶対パス。
        directory (bool): 実ファイルに問い合わせず標準フォルダーを取得する。

    Returns:
        QIcon: Shellが返す大小のアイコン。取得失敗時は空。
    """
    icon = QtGui.QIcon()
    for image in _shellImages(path, directory):
        icon.addPixmap(QtGui.QPixmap.fromImage(image))
    return icon


def _shellImages(path, directory=False):
    """ShellのHICONを所有権の独立したQImageへ変換する。QPixmapは作らない。"""
    shell = ctypes.windll.shell32.SHGetFileInfoW
    shell.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(_ShellInfo), wintypes.UINT, wintypes.UINT]
    shell.restype = ctypes.c_size_t
    destroy = ctypes.windll.user32.DestroyIcon
    destroy.argtypes = [wintypes.HANDLE]
    images = []
    for flag, size in ((1, 16), (0, 32)):
        info = _ShellInfo()
        if not shell(os.path.normpath(path), 0x10 if directory else 0, ctypes.byref(info),
                     ctypes.sizeof(info), 0x100 | flag | (0x10 if directory else 0)):
            continue
        try:
            if hasattr(QtGui.QImage, 'fromHICON'):
                image = QtGui.QImage.fromHICON(int(info.hIcon))
            else:
                image = _iconImage(info.hIcon, size)
            images.append(image)
        finally:
            destroy(info.hIcon)
    return images


_folderIcon = None


def folderIcon():
    """OS標準のフォルダーアイコンをGUIスレッドで一度だけ取得する。"""
    global _folderIcon
    if _folderIcon is None:
        _folderIcon = windowsIcon('folder', directory=True) if os.name == 'nt' else QtGui.QIcon()
        if _folderIcon.isNull():
            _folderIcon = QtWidgets.QFileIconProvider().icon(QtWidgets.QFileIconProvider.Folder)
    return _folderIcon


def _iconImage(handle, size):
    """Qt5用にHICONを32bit DIBへ描画してコピーする。

    Args:
        handle (int): 借用するHICON。
        size (int): 描画するピクセル寸法。

    Returns:
        QImage: GDI資源から独立した画像。
    """
    import struct
    gdi = ctypes.windll.gdi32
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi.CreateDIBSection.restype = wintypes.HANDLE
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi.SelectObject.restype = wintypes.HANDLE
    gdi.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    draw = ctypes.windll.user32.DrawIconEx
    draw.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HANDLE, ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HANDLE, wintypes.UINT]
    header = ctypes.create_string_buffer(struct.pack('<IiiHHIIiiII', 40, size, -size, 1, 32, 0, size * size * 4, 0, 0, 0, 0))
    bits = ctypes.c_void_p()
    dc = gdi.CreateCompatibleDC(None)
    bitmap = gdi.CreateDIBSection(dc, header, 0, ctypes.byref(bits), None, 0)
    if not bitmap:
        gdi.DeleteDC(dc)
        return QtGui.QImage()
    previous = gdi.SelectObject(dc, bitmap)
    try:
        ctypes.memset(bits, 0, size * size * 4)
        draw(dc, 0, 0, handle, size, size, 0, None, 3)
        data = ctypes.string_at(bits, size * size * 4)
        return QtGui.QImage(data, size, size, size * 4, QtGui.QImage.Format_ARGB32_Premultiplied).copy()
    finally:
        gdi.SelectObject(dc, previous)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(dc)


def fileType(path):
    """WindowsではShellの種類名、それ以外はQtの種類名を返す。

    Args:
        path (str): 対象ファイル。

    Returns:
        str: OSが表示するファイルの種類。
    """
    if os.name == 'nt':
        info = _ShellInfo()
        shell = ctypes.windll.shell32.SHGetFileInfoW
        shell.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(_ShellInfo), wintypes.UINT, wintypes.UINT]
        shell.restype = ctypes.c_size_t
        if shell(os.path.normpath(path), 0, ctypes.byref(info), ctypes.sizeof(info), 0x400):
            return info.typeName
    return QtWidgets.QFileIconProvider().type(QtCore.QFileInfo(path))


class _IconJob(QtCore.QRunnable):
    """ウィジェットを保持せず、Shell取得結果の画像だけを公開する。"""

    def __init__(self, path):
        """対象をコピーする。完了状態の公開まではGUI側から画像を読まない。"""
        super().__init__()
        self.path = path
        self.images = []
        self.ready = False

    def run(self):
        """ワーカー自身のCOMだけを初期化・解放し、最後に完了を公開する。"""
        initialized = None
        try:
            if os.name == 'nt':
                com = ctypes.windll.ole32
                com.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
                com.CoInitializeEx.restype = ctypes.c_long
                initialized = com.CoInitializeEx(None, 2)
                self.images = _shellImages(self.path)
        except Exception:
            # 取得不可は既定のファイルアイコンを維持し、移動操作を失敗させない。
            self.images = []
        finally:
            if initialized is not None and initialized >= 0:
                ctypes.windll.ole32.CoUninitialize()
            self.ready = True


class VisibleFileIcons(QtCore.QObject):
    """単体版で可視ファイルだけを最大2要求ずつ取得する。ビューが所有する。"""

    def __init__(self, view):
        """GUIタイマーとキャッシュを初期化し、ワーカーにはビューを渡さない。"""
        super().__init__(view)
        self.view = view
        self.pending = []
        self.cache = OrderedDict()
        self.applied = {}
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.update)
        view.installEventFilter(self)
        view.viewport().installEventFilter(self)
        view.verticalScrollBar().valueChanged.connect(self.wake)
        view.horizontalScrollBar().valueChanged.connect(self.wake)
        self.timer.start()

    def wake(self, *unused):
        """画面変化時だけ可視行の確認を予約し、同じフレームの通知をまとめる。"""
        if not self.timer.isActive():
            self.timer.start()

    def eventFilter(self, watched, event):
        """モデル更新・ルート変更の描画と、表示範囲の変化で再確認する。"""
        if event.type() in (QtCore.QEvent.Paint, QtCore.QEvent.Show, QtCore.QEvent.Resize):
            self.wake()
        return False

    def key(self, index):
        """GUIで保持済みのパス・サイズ・時刻から対象世代を作る。ディスクは読まない。"""
        path_role = self.view.property('qpeIconPathRole')
        if path_role is not None:
            return (index.data(path_role), index.data(QtCore.Qt.UserRole + 101))
        return (index.data(QtCore.Qt.UserRole + 1),
                index.sibling(index.row(), 1).data(QtCore.Qt.UserRole + 3),
                index.sibling(index.row(), 3).data(QtCore.Qt.EditRole).toMSecsSinceEpoch())

    def update(self):
        """完了を照合してGUIでQPixmapを生成し、次の可視行を要求する。"""
        for pending in list(self.pending):
            index, key, job = pending
            if not job.ready:
                continue
            icon = QtGui.QIcon()
            for image in job.images:
                icon.addPixmap(QtGui.QPixmap.fromImage(image))
            self.cache[key] = icon
            self.cache.move_to_end(key)
            while len(self.cache) > 2048:
                self.cache.popitem(last=False)
            if index.isValid() and self.key(index) == key:
                if not icon.isNull() and not index.data(QtCore.Qt.UserRole + 102):
                    self.view.model().setData(index, icon, QtCore.Qt.DecorationRole)
                self.applied[index] = key
            self.pending.remove(pending)
        if not self.view.isVisible() or self.view.model() is None:
            if not self.pending:
                self.timer.stop()
            return
        if len(self.applied) > 4096:
            self.applied.clear()
        index = self.view.indexAt(QtCore.QPoint(2, 2))
        budget = self.view.viewport().height() // max(12, self.view.property('qpeRowHeight') or 22) + 2
        tree = isinstance(self.view, QtWidgets.QTreeView)
        if not tree:
            width, height = max(1, self.view.gridSize().width()), max(1, self.view.gridSize().height())
            columns = max(1, self.view.viewport().width() // width)
            index = self.view.indexAt(QtCore.QPoint(min(width // 2, self.view.viewport().width() - 1), height // 2))
            if index.isValid():
                index = self.view.model().index(max(0, index.row() - columns), 0, self.view.rootIndex())
            budget = (self.view.viewport().height() // height + 4) * columns
        if not index.isValid():
            index = self.view.model().index(0, 0, self.view.rootIndex())
        for unused in range(budget):
            if not index.isValid():
                break
            key = self.key(index)
            if key[0] and not index.data(QtCore.Qt.UserRole + 2) and not index.data(QtCore.Qt.UserRole + 102):
                persistent = QtCore.QPersistentModelIndex(index)
                if self.applied.get(persistent) != key:
                    if key in self.cache:
                        icon = self.cache[key]
                        self.cache.move_to_end(key)
                        if not icon.isNull():
                            self.view.model().setData(index, icon, QtCore.Qt.DecorationRole)
                        self.applied[persistent] = key
                    elif len(self.pending) < 2 and not any(p[1] == key for p in self.pending):
                        job = _IconJob(key[0])
                        self.pending.append((persistent, key, job))
                        QtCore.QThreadPool.globalInstance().start(job)
            index = (self.view.indexBelow(index) if tree else
                     self.view.model().index(index.row() + 1, 0, self.view.rootIndex()))
        if not self.pending:
            self.timer.stop()
