"""OSの関連付けを使うファイルアイコン。"""
import os
import ctypes
from ctypes import wintypes
from qpeQt import QtCore, QtGui, QtWidgets


class FileIcons:
    """Qtのネイティブアイコン取得をキャッシュする。"""

    def __init__(self):
        """GUIスレッドで使用するプロバイダーを保持する。"""
        self._provider = QtWidgets.QFileIconProvider()
        self._cache = {}

    def icon(self, path):
        """ファイルごとの関連付け・ショートカット等を反映する。

        Args:
            path (str): 対象ファイル。

        Returns:
            QIcon: WindowsではShellのアイコン。サムネイルは含まない。
        """
        info = QtCore.QFileInfo(path)
        key = (info.absoluteFilePath(), info.lastModified().toMSecsSinceEpoch())
        if key not in self._cache:
            if len(self._cache) >= 512:
                self._cache.clear()
            native = windowsIcon(info.absoluteFilePath()) if os.name == 'nt' else QtGui.QIcon()
            self._cache[key] = native if not native.isNull() else self._provider.icon(info)
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
    shell = ctypes.windll.shell32.SHGetFileInfoW
    shell.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(_ShellInfo), wintypes.UINT, wintypes.UINT]
    shell.restype = ctypes.c_size_t
    destroy = ctypes.windll.user32.DestroyIcon
    destroy.argtypes = [wintypes.HANDLE]
    icon = QtGui.QIcon()
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
            icon.addPixmap(QtGui.QPixmap.fromImage(image))
        finally:
            destroy(info.hIcon)
    return icon


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
