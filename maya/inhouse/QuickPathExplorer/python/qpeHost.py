"""MayaのWindowメニューとシーン操作をブラウザーへ接続する。"""
import os
from pathlib import Path
from maya import cmds, mel, OpenMayaUI
from qpeQt import QtCore, QtGui, QtWidgets, QAction, shiboken
from quickPathExplorer import Explorer, ICON
from qpeSettings import readSettings

CONTROL = 'QuickPathExplorerWorkspaceControl'
MENU = 'quickPathExplorerWindowMenuItem'
_window = None


def installMenu():
    """標準Windowメニューへ重複なしで登録する。"""
    if cmds.about(batch=True):
        return
    if cmds.menuItem(MENU, exists=True):
        return
    parent = 'MayaWindow|mainWindowMenu'
    if not cmds.menu(parent, exists=True):
        return
    mel.eval('buildViewMenu MayaWindow|mainWindowMenu;')
    if not cmds.menuItem(MENU, exists=True):
        cmds.menuItem(MENU, parent=parent, label='QuickPathExplorer', image=ICON.as_posix(),
                      command=lambda *args: show())


def show(path=None):
    """Maya所有のドックを表示する。

    Args:
        path (str | None): 初期フォルダー。

    Returns:
        Explorer: 表示した画面。
    """
    global _window
    if _window is not None and shiboken.isValid(_window) and cmds.workspaceControl(CONTROL, exists=True):
        cmds.workspaceControl(CONTROL, edit=True, restore=True)
        if path:
            _window.navigate(path)
        refresh(_window)
        return _window
    if cmds.workspaceControl(CONTROL, exists=True):
        cmds.deleteUI(CONTROL)
    # MayaCodeEditorと同じMQtUtilの倍率を使う。Qt全体のDPI設定は変更しない。
    dpi_scale = float(OpenMayaUI.MQtUtil.dpiScale(1.0))
    screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
    cmds.workspaceControl(CONTROL, label='QuickPathExplorer', floating=True,
                          initialWidth=min(round(1240 * dpi_scale), round(screen.width() * .9)),
                          initialHeight=min(round(790 * dpi_scale), round(screen.height() * .9)), retain=False)
    widget = Explorer(maya=True, dpi_scale=dpi_scale)
    _window = widget
    # workspaceControlがQtウィジェットを所有する。シーン操作はGUIスレッドで実行する。
    pointer = OpenMayaUI.MQtUtil.findControl(CONTROL)
    OpenMayaUI.MQtUtil.addWidgetToMayaLayout(int(shiboken.getCppPointer(widget)[0]), int(pointer))
    widget.actionRequested.connect(lambda action: perform(widget, action))
    events = cmds.scriptJob(listEvents=True)
    for event in ('SceneOpened', 'NewSceneOpened', 'SceneSaved', 'workspaceChanged'):
        if event in events:
            cmds.scriptJob(event=[event, lambda: refresh(widget)], parent=CONTROL)
    refresh(widget)
    widget.show()
    location = path or readSettings().get('lastPath') or cmds.workspace(query=True, rootDirectory=True)
    widget.navigate(location if os.path.isdir(location) else str(Path.home()))
    return widget


def refresh(widget):
    """現在のシーンとプロジェクト情報を更新する。

    Args:
        widget (Explorer): 表示先。
    """
    if not shiboken.isValid(widget):
        return
    root = cmds.workspace(query=True, rootDirectory=True)
    folders = []
    for rule in cmds.workspace(query=True, fileRuleList=True) or []:
        value = cmds.workspace(fileRuleEntry=rule)
        path = os.path.normpath(os.path.join(root, value)).replace('\\', '/')
        if os.path.isdir(path):
            folders.append(path)
    widget.setProject(root, folders)
    scene = cmds.file(query=True, sceneName=True)
    widget.sceneTarget.setText('Current scene: ' + (scene or '(unsaved)'))
    if scene and not widget.fileName.text():
        widget.fileName.setText(Path(scene).name)
    widget.actionButtons['save'].setToolTip('Save updates current scene: ' + (scene or '(unsaved scene; use Save As)'))


def _allowOverwrite(widget, path):
    """既存ファイルを置き換える明示操作を確認する。

    Args:
        widget (Explorer): 親画面。
        path (str): 保存先。

    Returns:
        bool: 保存を続けられるか。
    """
    return not os.path.exists(path) or QtWidgets.QMessageBox.question(widget, 'Overwrite file',
        'Replace this file?\n' + path, QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
        QtWidgets.QMessageBox.Cancel) == QtWidgets.QMessageBox.Yes


def _allowOpen(widget):
    """未保存シーンの保存・破棄・中止を確認する。

    Args:
        widget (Explorer): 親画面。

    Returns:
        bool: シーンを切り替えてよいか。
    """
    if not cmds.file(query=True, modified=True):
        return True
    answer = QtWidgets.QMessageBox.question(widget, 'Unsaved scene', 'Save changes before opening another scene?',
        QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
        QtWidgets.QMessageBox.Cancel)
    if answer == QtWidgets.QMessageBox.Save:
        mel.eval('SaveScene;')
        return not cmds.file(query=True, modified=True)
    return answer == QtWidgets.QMessageBox.Discard


def perform(widget, action):
    """明示された操作だけをMayaに適用する。

    Args:
        widget (Explorer): 操作元。
        action (str): 操作名。
    """
    try:
        paths = widget.operationPaths()
        path = paths[0] if paths else ''
        if action == 'project':
            widget.navigate(cmds.workspace(query=True, rootDirectory=True))
        elif action == 'sceneFolder':
            scene = cmds.file(query=True, sceneName=True)
            if scene:
                widget.navigate(str(Path(scene).parent))
        elif action == 'options':
            menu = QtWidgets.QMenu(widget)
            for title, command in [('Open options', 'OpenSceneOptions'), ('Import options', 'ImportOptions'),
                                   ('Reference options', 'CreateReferenceOptions'), ('Save As options', 'SaveSceneAsOptions'),
                                   ('Export selection options', 'ExportSelectionOptions'), ('Set Project', 'SetProject')]:
                if cmds.runTimeCommand(command, exists=True):
                    menu.addAction(title, lambda checked=False, value=command: mel.eval(value + ';'))
            menu.exec_(QtGui.QCursor.pos())
        elif action in ('open', 'import', 'reference'):
            if not paths or any(not os.path.isfile(value) for value in paths):
                raise ValueError('Select an existing file.')
            if action == 'open' and len(paths) != 1:
                raise ValueError('Open one file at a time.')
            if len(paths) > 1:
                answer = QtWidgets.QMessageBox.question(widget, 'QuickPathExplorer',
                    '{} {} files?\n\n{}'.format(action.title(), len(paths), '\n'.join(paths)),
                    QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel, QtWidgets.QMessageBox.Cancel)
                if answer != QtWidgets.QMessageBox.Ok:
                    return
            if action == 'open':
                if Path(path).suffix.lower() not in ('.ma', '.mb'):
                    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))
                    return
                if not _allowOpen(widget):
                    return
                cmds.file(path, open=True, force=True)
            elif action == 'import':
                for path in paths:
                    cmds.file(path, i=True)
            else:
                for path in paths:
                    cmds.file(path, reference=True)
        elif action == 'save':
            if not cmds.file(query=True, sceneName=True):
                perform(widget, 'saveAs')
                return
            cmds.file(save=True)
        elif action in ('saveAs', 'export'):
            target = widget.targetPath()
            if not target or not os.path.isdir(str(Path(target).parent)):
                raise ValueError('Enter a file name and select a valid destination folder.')
            if action == 'export' and not cmds.ls(selection=True):
                raise ValueError('Select objects in Maya before exporting.')
            if not _allowOverwrite(widget, target):
                return
            file_type = widget.saveType.currentData()
            if action == 'export':
                cmds.file(target, exportSelected=True, type=file_type, force=True)
            else:
                previous = cmds.file(query=True, sceneName=True)
                cmds.file(rename=target)
                try:
                    cmds.file(save=True, type=file_type, force=True)
                except RuntimeError:
                    cmds.file(rename=previous or 'untitled')
                    raise
        refresh(widget)
        widget.status.setText('Completed: ' + action)
    except (RuntimeError, OSError, ValueError) as error:
        widget.status.setText(str(error))
        QtWidgets.QMessageBox.warning(widget, 'QuickPathExplorer', str(error))
