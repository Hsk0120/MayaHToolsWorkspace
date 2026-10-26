"""MayaのWindowメニューとシーン操作をブラウザーへ接続する。"""
import os
import json
from pathlib import Path
from maya import cmds, mel, OpenMayaUI
from maya.api import OpenMaya
from qpeQt import QtCore, QtGui, QtWidgets, QAction, shiboken
from quickPathExplorer import Explorer, ICON
from qpeSettings import readSettings

CONTROL = 'QuickPathExplorerWorkspaceControl'
MENU = 'quickPathExplorerWindowMenuItem'
_window = None
_building = False


def installMenu():
    """標準Windowメニューへ重複なしで登録する。"""
    if cmds.about(batch=True):
        return
    from qpeDock import startup
    startup()
    if cmds.menuItem(MENU, exists=True):
        return
    parent = 'MayaWindow|mainWindowMenu'
    if not cmds.menu(parent, exists=True):
        return
    mel.eval('buildViewMenu MayaWindow|mainWindowMenu;')
    if not cmds.menuItem(MENU, exists=True):
        cmds.menuItem(MENU, parent=parent, label='QuickPathExplorer', image=ICON.as_posix(),
                      command=lambda *args: show())


def show(path=None, _restoring=False):
    """Maya所有のドックを表示する。

    Args:
        path (str | None): 初期フォルダー。
        _restoring (bool): MayaのuiScriptからの内部復元か。

    Returns:
        Explorer: 表示した画面。
    """
    global _window, _building
    if _building:
        return _window
    from qpeDock import opened, restoreState, releaseWatcher, _control_widget
    control = _control_widget(CONTROL)
    if (_window is not None and shiboken.isValid(_window) and control is not None
            and control.isAncestorOf(_window)):
        if not _restoring:
            cmds.workspaceControl(CONTROL, edit=True, restore=True)
            opened(_window)
        if path:
            _window.navigate(path)
        refresh(_window)
        return _window
    releaseWatcher()
    # MayaCodeEditorと同じMQtUtilの倍率を使う。Qt全体のDPI設定は変更しない。
    dpi_scale = float(OpenMayaUI.MQtUtil.dpiScale(1.0))
    screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
    created = not cmds.workspaceControl(CONTROL, exists=True)
    if created:
        _building = True
        try:
            cmds.workspaceControl(CONTROL, label='QuickPathExplorer', floating=True,
                                  initialWidth=min(round(1240 * dpi_scale), round(screen.width() * .9)),
                                  initialHeight=min(round(790 * dpi_scale), round(screen.height() * .9)),
                                  retain=True, uiScript='import qpeHost; qpeHost.restore()')
        finally:
            _building = False
    widget = Explorer(maya=True, dpi_scale=dpi_scale)
    _window = widget
    # 内容の最小サイズをMaya全体のドック制約にしない。
    # 小さいドックではスクロールで全操作へ到達でき、通常サイズではバーを隠す。
    container = QtWidgets.QScrollArea()
    container.setObjectName('qpeDockViewport')
    container.setFrameShape(QtWidgets.QFrame.NoFrame)
    container.setWidgetResizable(True)
    container.setMinimumSize(240, 160)
    container.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
    container.setWidget(widget)
    widget._dockViewport = container
    # workspaceControlがQtウィジェットを所有する。シーン操作はGUIスレッドで実行する。
    pointer = OpenMayaUI.MQtUtil.findControl(CONTROL)
    OpenMayaUI.MQtUtil.addWidgetToMayaLayout(int(shiboken.getCppPointer(container)[0]), int(pointer))
    widget.actionRequested.connect(lambda action: perform(widget, action))
    events = cmds.scriptJob(listEvents=True)
    for event in ('SceneOpened', 'NewSceneOpened', 'SceneSaved', 'workspaceChanged'):
        if event in events:
            cmds.scriptJob(event=[event, lambda: refresh(widget)], parent=CONTROL)
    # scriptJobのアイドル待ちに依存せず、スクリプトからのOpenにも追従する。
    # Qt側の破棄時に解除し、閉じた画面への通知とコールバックの蓄積を防ぐ。
    callback = OpenMaya.MSceneMessage.addCallback(
        OpenMaya.MSceneMessage.kAfterOpen, lambda *unused: refresh(widget, follow_scene=True))
    widget.destroyed.connect(lambda *unused: OpenMaya.MMessage.removeCallback(callback))
    refresh(widget)
    widget.show()
    location = path or readSettings().get('lastPath') or cmds.workspace(query=True, rootDirectory=True)
    widget.navigate(location if os.path.isdir(location) else str(Path.home()))
    if not path:
        widget.folderTabs.restoreSession()
    if created:
        restoreState(widget)
    opened(widget, restoring=_restoring)
    return widget


def restore():
    """Mayaが復元したworkspaceControlへ内容だけを取り付ける。"""
    return show(_restoring=True)


def refresh(widget, follow_scene=False):
    """現在のシーンとプロジェクト情報を更新する。

    Args:
        widget (Explorer): 表示先。
        follow_scene (bool): シーン読込成功時だけ、その保存先へ移動する。
    """
    if widget is not _window or not shiboken.isValid(widget):
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
    if follow_scene and scene:
        directory = str(Path(scene).parent)
        if os.path.isdir(directory):
            widget.navigate(directory)
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
    answer = QtWidgets.QMessageBox.question(widget, 'Unsaved scene', 'Save changes before switching scenes?',
        QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
        QtWidgets.QMessageBox.Cancel)
    if answer == QtWidgets.QMessageBox.Save:
        mel.eval('SaveScene;')
        return not cmds.file(query=True, modified=True)
    return answer == QtWidgets.QMessageBox.Discard


def readFile(path, action, options):
    """親ネームスペースを用意して明示したファイルを読み込む。

    Args:
        path (str): 読込元。
        action (str): importまたはreference。
        options (dict): 検証済みfile引数。
    """
    # fileは存在しない親を含むnamespaceを末尾名へ縮めるため親だけ作る。
    # 葉はfileに作らせ、衝突時の自動採番を維持する。現在namespaceは変えない。
    parent = ':'
    for part in options['namespace'].strip(':').split(':')[:-1]:
        child = parent.rstrip(':') + ':' + part
        if not cmds.namespace(exists=child):
            cmds.namespace(addNamespace=part, parent=parent)
        parent = child
    cmds.file(path, **dict(options, **{'i' if action == 'import' else 'reference': True}))


def recordRecentScene():
    """成功後の実シーンをMaya標準のRecent Filesへ登録する。

    標準手続きに重複除去・件数制限・設定保存を委ねる。履歴の失敗だけで
    完了済みのシーン読込や保存を失敗扱いにしない。
    """
    try:
        scene = cmds.file(query=True, sceneName=True)
        if not scene:
            return
        file_type = cmds.file(query=True, type=True)[0]
        mel.eval('addRecentFile({}, {});'.format(
            json.dumps(scene.replace('\\', '/'), ensure_ascii=False),
            json.dumps(file_type, ensure_ascii=False)))
    except RuntimeError as error:
        cmds.warning('QuickPathExplorer: Could not update Recent Files: ' + str(error))


def perform(widget, action):
    """明示された操作だけをMayaに適用する。

    Args:
        widget (Explorer): 操作元。
        action (str): 操作名。
    """
    try:
        paths = widget.operationPaths()
        path = paths[0] if paths else ''
        if action == 'new':
            if not _allowOpen(widget):
                return
            cmds.file(new=True, force=True)
        elif action == 'project':
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
                    widget.openAssociatedFile(path)
                    return
                if not _allowOpen(widget):
                    return
                cmds.file(path, open=True, force=True)
                widget.recordSuccessfulFiles([path])
                recordRecentScene()
            elif action == 'import':
                arguments = [widget.readOptions.fileArguments(action, path) for path in paths]
                for path, options in zip(paths, arguments):
                    readFile(path, action, options)
                    widget.recordSuccessfulFiles([path])
            else:
                arguments = [widget.readOptions.fileArguments(action, path) for path in paths]
                for path, options in zip(paths, arguments):
                    readFile(path, action, options)
                    widget.recordSuccessfulFiles([path])
        elif action == 'save':
            if not cmds.file(query=True, sceneName=True):
                perform(widget, 'saveAs')
                return
            cmds.file(save=True)
            recordRecentScene()
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
                recordRecentScene()
        refresh(widget)
        widget.status.setText('Completed: ' + {'new': 'New Scene', 'save': 'Save Scene', 'saveAs': 'Save Scene As',
                                               'export': 'Export Selection', 'reference': 'Create Reference'}.get(action, action.title()))
    except (RuntimeError, OSError, ValueError) as error:
        widget.status.setText(str(error))
        QtWidgets.QMessageBox.warning(widget, 'QuickPathExplorer', str(error))
