"""Mayaの画面ワークスペースを管理する。プロジェクトのWorkspaceとは別。"""
from contextlib import contextmanager
import maya.cmds as cmds
import maya.mel as mel
from ..ui._windowReference import _WindowReference
from ..ui.mainWindow import MainWindow
from ..ui.window import Window
from ..ui.uiSnapshot import UiSnapshot


class WorkspaceLayout:
    """登録済みの画面配置への参照。保存とメモリ退避を明確に分ける。"""

    def __init__(self, name=None):
        """登録済みの配置を参照する。切り替えや保存は行わない。

        Args:
            name (str | None): 配置名。省略時は現在の配置。
        """
        _WindowReference._require_gui()
        if name is not None and (not isinstance(name, str) or not name):
            raise TypeError("Expected a non-empty workspace layout name")
        self._name = name if name is not None else cmds.workspaceLayoutManager(query=True, current=True)
        self.name()

    @classmethod
    def list(cls):
        """list[WorkspaceLayout]: Mayaに登録済みの配置を取得する。"""
        _WindowReference._require_gui()
        return [cls(name) for name in cmds.workspaceLayoutManager(listLayouts=True) or []]

    @classmethod
    def current(cls):
        """WorkspaceLayout: 現在の配置への新しい参照。"""
        return cls()

    def exists(self):
        """bool: 登録済みの配置か取得する。"""
        _WindowReference._require_gui()
        return self._name in (cmds.workspaceLayoutManager(listLayouts=True) or [])

    def name(self):
        """str: 存在を確認した配置名。"""
        if not self.exists():
            raise RuntimeError("Workspace layout is unavailable: " + str(self._name))
        return self._name

    def isCurrent(self):
        """bool: 現在使用中の配置か取得する。"""
        return self.name() == cmds.workspaceLayoutManager(query=True, current=True)

    def _require_current(self):
        """別の配置を誤って保存・復元しないよう検証する。"""
        if not self.isCurrent():
            raise RuntimeError("Activate this workspace layout first")

    def activate(self):
        """配置名で切り替える。Mayaの自動保存設定に従う副作用がある。

        切り替え時に現在の配置が自動保存される場合がある。UIのuiScriptや
        必要プラグインに依存し、任意のQtウィンドウは再生成できない。
        """
        cmds.workspaceLayoutManager(setCurrent=self.name())

    def reset(self):
        """現在の配置を保存済み状態へ戻す。未保存の配置変更は失われる。"""
        self._require_current()
        cmds.workspaceLayoutManager(reset=True)

    def save(self):
        """現在の配置をMaya標準の保存先へ永続保存する。

        prefs/workspacesの管理はMayaへ委譲する。シーン保存ではなく、Undoで戻せない。
        """
        self._require_current()
        cmds.workspaceLayoutManager(save=True)

    def saveAs(self, name, overwrite=False):
        """現在の配置を別名で保存して切り替える。

        Args:
            name (str): Mayaの配置名。ファイルパスではない。
            overwrite (bool): 同名配置への上書きを許可するか。既定は拒否。

        Returns:
            WorkspaceLayout: 保存先の配置参照。元の参照の名前は変えない。
        """
        self._require_current()
        _WindowReference._boolean(overwrite)
        if not isinstance(name, str) or not name.strip() or any(c in name for c in '/\\\r\n\x00'):
            raise ValueError("Expected a workspace name, not a file path")
        if not overwrite and name in (cmds.workspaceLayoutManager(listLayouts=True) or []):
            raise ValueError("Workspace layout already exists: " + name)
        cmds.workspaceLayoutManager(saveAs=name)
        result = type(self)(name)
        result.activate()
        return result

    @staticmethod
    def getLocked():
        """bool: Maya全体のドッキングロック状態を取得する。"""
        _WindowReference._require_gui()
        return bool(cmds.optionVar(query="workspacesLockDocking"))

    @staticmethod
    def setLocked(locked):
        """Maya右上の鍵と同じ状態を設定する。ディスク保存は行わない。

        Args:
            locked (bool): 移動・閉じる操作をロックするか。サイズ変更・折り畳みは可能。
        """
        _WindowReference._require_gui()
        _WindowReference._boolean(locked)
        # 標準手続きはoptionVarと鍵アイコンの表示を同期する。
        mel.eval('source "workspaceHelperProcs.mel"; updateWorkspaceDocking {};'.format(int(locked)))

    @staticmethod
    def lock():
        """全体のドッキング操作をロックする。個別ウィンドウの固定ではない。"""
        WorkspaceLayout.setLocked(True)

    @staticmethod
    def unlock():
        """全体のドッキングロックを解除する。"""
        WorkspaceLayout.setLocked(False)

    def captureDockingLayout(self):
        """UiSnapshot: メインウィンドウのドッキング配置とロックをメモリ退避する。

        同じセッション・同じ配置・既存UIを対象にする。ファイルは作らない。
        独立した浮動ウィンドウの位置やエディタの内容は対象外。
        """
        self._require_current()
        main = MainWindow.name()
        if not main or not cmds.window(main, exists=True):
            raise RuntimeError("Maya main window is unavailable")
        from ..ui.workspaceControl import WorkspaceControl
        # 浮動UIはこの退避範囲に含めない。削除されてもドッキング復元を妨げない。
        targets = [Window(main)]
        targets.extend(control for control in WorkspaceControl.list() if not control.getFloating())
        return UiSnapshot("dockingLayout", self.name(), {
            "main_window": main,
            "docking": cmds.window(main, query=True, dockingLayout=True),
            "locked": self.getLocked(),
        }, tuple(targets))

    def restoreDockingLayout(self, snapshot):
        """メモリ退避したドッキング配置とロックを復元する。

        Args:
            snapshot (UiSnapshot): captureDockingLayoutの返り値。

        Note:
            別のワークスペースへ切り替えた場合や、退避時のUIが削除された場合は拒否する。
            追加されたUIの削除は行わない。Mayaの復元失敗時はロックのみ元に戻し例外を伝える。
        """
        self._require_current()
        if not isinstance(snapshot, UiSnapshot) or snapshot.scope != "dockingLayout" or snapshot.name != self.name():
            raise ValueError("Snapshot belongs to another workspace layout")
        if type(snapshot.data.get("docking")) is not str or type(snapshot.data.get("locked")) is not bool:
            raise ValueError("Invalid layout snapshot")
        snapshot.validate()
        main = MainWindow.name()
        if snapshot.data.get("main_window") != main or not snapshot._targets or snapshot._targets[0].name() != main:
            raise RuntimeError("Snapshot main window is unavailable")
        old_lock = self.getLocked()
        self.unlock()
        try:
            cmds.window(main, edit=True, dockingLayout=snapshot["docking"])
        except BaseException:
            self.setLocked(old_lock)
            raise
        self.setLocked(snapshot["locked"])

    @contextmanager
    def temporaryDockingLayout(self):
        """同じ配置でのドッキング編集を例外時も復元する。ファイル保存はしない。

        Yields:
            WorkspaceLayout: この配置。ブロック内でUI削除・配置切り替えは行わないこと。
        """
        snapshot = self.captureDockingLayout()
        try:
            yield self
        finally:
            self.restoreDockingLayout(snapshot)

    def __str__(self):
        """str: 保持した配置名。"""
        return self._name
