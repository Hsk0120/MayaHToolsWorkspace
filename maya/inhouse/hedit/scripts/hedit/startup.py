"""Mayaのメニュー登録と、前回開いていたheditの復元。

ユーザーのSecurity設定・プラグイン自動ロード設定は変更しない。
開閉状態はhedit専用ui.json、ドック配置はMayaのワークスペースへ保存する。
"""
import json
import os
from pathlib import Path
from maya import cmds, mel, utils

_timer = None
_quitting = False
_opened = False
_quit_job = None
_last = None
MENU = 'heditWindowMenuItem'
DIVIDER = 'heditWindowMenuDivider'


def state_path():
    """Path: 現在のMaya/隔離テストに対応するUI復元ファイル。"""
    from .bridge import session_path
    return Path(session_path()).with_name('ui.json')


def previous_open():
    """bool: 保存済みの開閉状態。未保存の場合は明示的な復元を許可する。"""
    try:
        return bool(json.loads(state_path().read_text(encoding='utf-8')).get('open', True))
    except (OSError, ValueError):
        return True


def hide_if_closed():
    """Mayaが非表示ドックのuiScriptを呼んだ場合も、閉じた状態を維持する。"""
    from .docking import CONTROL
    if not _opened and cmds.workspaceControl(CONTROL, exists=True):
        # uiScript直後のcloseはQt5の浮動ウィンドウを破棄し、次のrestoreで
        # 無効なネイティブハンドルを参照し得る。復元済みUIを非表示に留める。
        cmds.workspaceControl(CONTROL, edit=True, visible=False)


def install_menu():
    """Windowメニュー末尾へ、緑アイコン付きの項目を一度だけ登録する。"""
    if cmds.about(batch=True) or not cmds.pluginInfo('hedit', query=True, loaded=True):
        return
    if cmds.menuItem(MENU, exists=True):
        return
    parent = 'MayaWindow|mainWindowMenu'
    if not cmds.menu(parent, exists=True):
        return
    # SIWeightEditorと同じ標準Windowメニューを使用。既存メニューは消去しない。
    mel.eval('buildViewMenu MayaWindow|mainWindowMenu;')
    if not cmds.menuItem(DIVIDER, exists=True):
        cmds.menuItem(DIVIDER, parent=parent, divider=True)
    cmds.menuItem(MENU, parent=parent, label='hedit - Python / MEL',
                  image=str(Path(__file__).resolve().parents[2] / 'icons/hedit.svg'),
                  annotation='Open hedit (additional script editor)', sourceType='python',
                  command='import hedit; hedit.show()')


def record():
    """現在のドック状態を原子的に保存する。終了処理中は上書きしない。"""
    global _last
    from .docking import CONTROL
    if _quitting or not cmds.workspaceControl(CONTROL, exists=True):
        return
    state = {'version': 1, 'open': _opened,
             'floating': cmds.workspaceControl(CONTROL, query=True, floating=True),
             'layout': cmds.workspaceLayoutManager(query=True, current=True)}
    if state == _last:
        return
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('ui.{}.tmp'.format(os.getpid()))
    try:
        temporary.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
        os.replace(str(temporary), str(path))
        _last = state
    except OSError as exc:
        cmds.warning('hedit layout could not be saved: {}'.format(exc))


def closed(*unused):
    """ユーザーが閉じた時だけ、次回の自動表示を停止する。"""
    global _opened
    if not _quitting:
        _opened = False
        record()


def quitting(*unused):
    """MayaがUIを閉じる前に最終状態を保存し、以後の変更を凍結する。"""
    global _quitting
    # ドックの入れ子・タブグループはMaya自身のワークスペースに保存する。
    # workspaceControl.stateStringは版によって空リストを返し、配置復元には使えない。
    cmds.workspaceLayoutManager(save=True)
    record()
    _quitting = True
    if _timer:
        _timer.stop()


def opened():
    """表示後に配置の監視を始める。タイマーと終了通知は重複させない。"""
    global _timer, _opened, _quit_job
    from .docking import CONTROL, QtCore, _host
    _opened = True
    cmds.workspaceControl(CONTROL, edit=True, closeCommand='import hedit.startup; hedit.startup.closed()')
    if _timer is None:
        _timer = QtCore.QTimer(_host)
        _timer.setInterval(1000)
        _timer.timeout.connect(record)
    _timer.start()
    if _quit_job is None:
        _quit_job = cmds.scriptJob(event=['quitApplication', quitting], runOnce=True)
    record()


def restore_previous():
    """前回開いていた時だけ表示する。配置はMayaのワークスペース復元を優先する。"""
    if cmds.about(batch=True):
        return
    try:
        state = json.loads(state_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return
    if state.get('version') != 1:
        return
    if not state.get('open'):
        hide_if_closed()
        return
    import hedit
    from .docking import CONTROL
    existing = cmds.workspaceControl(CONTROL, exists=True)
    hedit.show(floating=None if existing else state.get('floating', True))
    if not existing and not state.get('floating', True):
        cmds.warning('hedit: saved workspace control is unavailable; docked at the bottom. Restore the saved Maya workspace for the original placement.')
    record()


def initialize():
    """userSetupからUI初期化完了後に呼ぶ。失敗はMayaの警告へ通知する。"""
    if cmds.about(batch=True):
        return
    try:
        # .modのscripts/userSetupから呼ばれるGUI初期化。設定のautoloadフラグは変更しない。
        import hedit
        if 'hedit' not in (cmds.pluginInfo(query=True, listPlugins=True) or []):
            version = str(cmds.about(version=True)).split()[0]
            plugin = hedit._plugin_path(version)
            if not plugin.is_file():
                raise RuntimeError('hedit plugin is not built: {}'.format(plugin))
            cmds.loadPlugin(str(plugin))
        restore_previous()
        if 'hedit' in (cmds.pluginInfo(query=True, listPlugins=True) or []):
            install_menu()
    except Exception as exc:
        cmds.warning('hedit startup: {}'.format(exc))


def plugin_loaded():
    """プラグイン登録中の再入を避け、メニュー作成を次のidleへ送る。"""
    if not cmds.about(batch=True):
        utils.executeDeferred(install_menu)


def uninstall():
    """解除時にhedit専用のメニュー・タイマー・終了通知を取り除く。"""
    global _timer, _quit_job
    if not _quitting:
        closed()
    if _timer:
        _timer.stop()
        _timer.deleteLater()
        _timer = None
    if _quit_job is not None and cmds.scriptJob(exists=_quit_job):
        cmds.scriptJob(kill=_quit_job, force=True)
    _quit_job = None
    for item in (MENU, DIVIDER):
        if cmds.menuItem(item, exists=True):
            cmds.deleteUI(item)
