"""単一mllのネイティブ部品と、通常Python版の切替を管理する。"""
import ctypes
from qpeQt import QtCore, QtGui, QtWidgets, shiboken

_imageLibrary = None


def prepareImageReader(library=None):
    """GUI側で配布DLLを解決し、ワーカーからMayaを呼ばずに読めるようにする。"""
    global _imageLibrary
    if _imageLibrary is not None or not available():
        return
    if library is None:
        # プラグインの場所はGUI側で一度だけ問い合わせる。
        from maya import cmds
        library = ctypes.CDLL(cmds.pluginInfo('quickPathExplorer', query=True, path=True))
    library.qpeReadImage.argtypes = (ctypes.c_wchar_p, ctypes.c_void_p,
                                  ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                                  ctypes.c_void_p, ctypes.c_int)
    library.qpeReadImage.restype = ctypes.c_int
    _imageLibrary = library


def readImage(path, pixels=True):
    """GILを解放するC ABIで画像を読む。GUI側でprepareImageReaderを先に呼ぶ。

    Args:
        path (str): 対象ファイル。
        pixels (bool): Falseならヘッダーの寸法だけ。

    Returns:
        tuple: QImage、QSize、利用者向けエラー。
    """
    if _imageLibrary is None:
        raise RuntimeError('Native image reader has not been prepared on the GUI thread')
    image = QtGui.QImage()
    width, height = ctypes.c_int(), ctypes.c_int()
    error = ctypes.create_string_buffer(1024)
    pointer = shiboken.getCppPointer(image)[0] if pixels else None
    status = _imageLibrary.qpeReadImage(str(path), pointer, ctypes.byref(width), ctypes.byref(height), error, len(error))
    message = ('Preview skipped: image is too large or unsupported' if status == 2 else
               error.value.decode('utf-8', errors='replace') if status else '')
    return image, QtCore.QSize(width.value, height.value), message


def available():
    """このモジュールがmllから読み込まれた場合だけC++部品を使う。"""
    return getattr(__loader__, 'qpe_embedded', False)


def create(kind, parent, base):
    """親所有のQt部品を既存のPySideインターフェースで受け取る。

    Args:
        kind (str): proxy、delegate、icons。
        parent (QWidget): 所有者。
        base (type): Qtの基底ラッパー。

    Returns:
        QObject: 親と同じ寿命の部品。
    """
    # Maya以外ではimportしない。
    from maya import cmds
    address = cmds.quickPathExplorerNative(kind, str(shiboken.getCppPointer(parent)[0]))
    return shiboken.wrapInstance(int(address), base)


def installView(view):
    """ファイルビューにだけ高速部品を取り付ける。

    Args:
        view (QTreeView): 対象。
    """
    view.setUniformRowHeights(True)
    if available():
        view.setItemDelegate(create('delegate', view, QtWidgets.QStyledItemDelegate))
        view._nativeIcons = create('icons', view, QtCore.QObject)
    else:
        # Windows単体版もShell取得をGUIから分離する。Mayaでは既存C++版を使う。
        from qpeFileIcons import VisibleFileIcons
        view._visibleIcons = VisibleFileIcons(view)


def shutdown():
    """進行中のファイル操作は拒否し、QPEの所有するUIだけを解除する。"""
    # プラグイン解除時のMaya専用処理。
    from maya import cmds
    import qpeHost
    import qpeDock
    widget = qpeHost._window
    if widget is not None and shiboken.isValid(widget):
        if not widget.close():
            raise RuntimeError('Wait for QPE file operations before unloading.')
    if qpeDock._quitJob and cmds.scriptJob(exists=qpeDock._quitJob):
        cmds.scriptJob(kill=qpeDock._quitJob, force=True)
    qpeDock._quitJob = None
    qpeDock._quitting = True
    qpeDock.releaseWatcher()
    if cmds.workspaceControl(qpeHost.CONTROL, exists=True):
        cmds.deleteUI(qpeHost.CONTROL)
    if widget is not None and shiboken.isValid(widget):
        widget.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(widget, QtCore.QEvent.DeferredDelete)
    qpeHost._window = None
    if cmds.menuItem(qpeHost.MENU, exists=True):
        cmds.deleteUI(qpeHost.MENU)
