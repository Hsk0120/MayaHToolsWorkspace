"""C++ UIの読込とMayaドック配置。UI本体にMaya依存を持ち込まない。"""
import ctypes
import os
from pathlib import Path
from PySide6 import QtCore, QtWidgets
import shiboken6

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[2]
_libraries = {}
_windows = {}


def library():
    """同一プロセスのQtに合うC++ DLLを保持して返す。

    Returns:
        ctypes.CDLL: UIが生存する間はアンロードしないDLL。
    """
    path = os.environ.get('QPE_NATIVE_DLL', str(ROOT / '.maya-output/plugin-build/QuickPathExplorer/2027/Release/qpeNative.dll'))
    if path not in _libraries:
        dll = ctypes.CDLL(path)
        dll.qpeCreate.argtypes = [ctypes.c_void_p]
        dll.qpeCreate.restype = ctypes.c_void_p
        dll.qpeBenchmark.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        dll.qpeBenchmark.restype = ctypes.c_int
        _libraries[path] = dll
    return _libraries[path]


def create(implementation, parent=None):
    """選択した実装のUIを作る。

    Args:
        implementation (str): cppまたはpython。
        parent (QWidget | None): Qt所有者。

    Returns:
        QWidget: 新規画面。
    """
    if implementation == 'python':
        from qpePrototype import Explorer
        return Explorer(parent)
    if implementation != 'cpp':
        raise ValueError(implementation)
    pointer = library().qpeCreate(shiboken6.getCppPointer(parent)[0] if parent else None)
    if not pointer:
        raise RuntimeError('Could not create native widget')
    return shiboken6.wrapInstance(pointer, QtWidgets.QWidget)


def show(implementation='python', path=None):
    """Maya内のフローティング可能なドックへ表示する。

    Args:
        implementation (str): cppまたはpython。
        path (str | None): 開くフォルダー。空文字は計測用の未読込状態。

    Returns:
        QWidget: 表示したブラウザー。
    """
    from maya import cmds, OpenMayaUI
    name = 'QuickPathExplorer_' + implementation
    if cmds.workspaceControl(name, exists=True):
        cmds.workspaceControl(name, edit=True, restore=True)
        return _windows[name]
    cmds.workspaceControl(name, label='QuickPathExplorer — ' + implementation,
                          floating=True, initialWidth=1100, initialHeight=650, retain=False)
    widget = create(implementation)
    widget.setObjectName(name + '_widget')
    # Mayaが所有するworkspaceControlへQtの所有権を移す。DLLはプロセス中保持する。
    pointer = OpenMayaUI.MQtUtil.findControl(name)
    OpenMayaUI.MQtUtil.addWidgetToMayaLayout(int(shiboken6.getCppPointer(widget)[0]), int(pointer))
    actions = QtWidgets.QHBoxLayout()
    widget.layout().addLayout(actions)
    for label, action in (('Open in Maya', 'open'), ('Import', 'import'), ('Reference', 'reference')):
        button = QtWidgets.QPushButton(label, widget)
        actions.addWidget(button)
        button.clicked.connect(lambda checked=False, mode=action: _mayaAction(widget, mode))
    _windows[name] = widget
    widget.show()
    if path != '':
        address = widget.findChild(QtWidgets.QLineEdit, 'address')
        address.setText(path or QtCore.QDir.homePath())
        address.returnPressed.emit()
    return widget


def _mayaAction(widget, mode):
    """選択シーンをユーザーの明示操作で読み込む。

    Args:
        widget (QWidget): 対象画面。
        mode (str): open/import/reference。
    """
    from maya import cmds
    model = widget.findChild(QtWidgets.QFileSystemModel, 'fileModel')
    view = widget.findChild(QtWidgets.QColumnView, 'columns')
    path = model.filePath(view.currentIndex())
    if Path(path).suffix.lower() not in ('.ma', '.mb'):
        QtWidgets.QMessageBox.information(widget, 'QuickPathExplorer', 'Select a .ma or .mb file.')
        return
    if mode == 'open':
        if cmds.file(query=True, modified=True):
            answer = QtWidgets.QMessageBox.question(widget, 'QuickPathExplorer',
                'The current scene has unsaved changes. Discard them and open this file?',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel, QtWidgets.QMessageBox.Cancel)
            if answer != QtWidgets.QMessageBox.Yes:
                return
        cmds.file(path, open=True, force=True)
    elif mode == 'import':
        cmds.file(path, i=True)
    else:
        cmds.file(path, reference=True)
