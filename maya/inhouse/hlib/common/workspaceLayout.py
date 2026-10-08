"""Mayaの画面ワークスペースを管理する。プロジェクトのWorkspaceとは別。"""

import maya.cmds as cmds
import maya.mel as mel

from .._core.getterAlias import _getter_alias
from ._windowReference import _WindowReference


class WorkspaceLayout:
    """登録済みの画面配置への参照。配置の切り替え・保存と全体のドッキングロックを扱う。

    ドッキング配置のメモリ退避・復元は提供しない。Mayaのコマンドからは workspaceControl の
    ドッキング先(分割・タブの構成)を照会できず、``window -dockingLayout`` にも含まれないため。
    """

    def __init__(self, name=None):
        """登録済みの配置を参照する。切り替えや保存は行わない。

        Args:
            name (str | None): 配置名。省略時は現在の配置。
        """
        _WindowReference._require_gui()
        if name is not None and (not isinstance(name, str) or not name):
            raise TypeError("Expected a non-empty workspace layout name")
        self._name = name if name is not None else cmds.workspaceLayoutManager(query=True, current=True)
        self.getName()

    def __str__(self):
        """保持した配置名。

        Returns:
            str: 保持した配置名。
        """
        return self._name

    @classmethod
    def list(cls):
        """Mayaに登録済みの配置を取得する。

        Returns:
            list[WorkspaceLayout]: Mayaに登録済みの配置を取得する。
        """
        _WindowReference._require_gui()
        return [cls(name) for name in cmds.workspaceLayoutManager(listLayouts=True) or []]

    @classmethod
    def getCurrent(cls):
        """現在の配置への新しい参照。

        Returns:
            WorkspaceLayout: 現在の配置への新しい参照。
        """
        return cls()

    @staticmethod
    def getLocked():
        """Maya全体のドッキングロック状態を取得する。

        Returns:
            bool: Maya全体のドッキングロック状態を取得する。
        """
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

    @classmethod
    @_getter_alias(getCurrent)
    def current(cls, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return cls.getCurrent(*args, **kwargs)

    @classmethod
    @_getter_alias(getLocked, static=True)
    def locked(cls, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return cls.getLocked(*args, **kwargs)

    def exists(self):
        """登録済みの配置か取得する。

        Returns:
            bool: 登録済みの配置か取得する。
        """
        _WindowReference._require_gui()
        return self._name in (cmds.workspaceLayoutManager(listLayouts=True) or [])

    def getName(self):
        """存在を確認した配置名。

        Returns:
            str: 存在を確認した配置名。
        """
        if not self.exists():
            raise RuntimeError("Workspace layout is unavailable: " + str(self._name))
        return self._name

    def isCurrent(self):
        """現在使用中の配置か取得する。

        Returns:
            bool: 現在使用中の配置か取得する。
        """
        return self.getName() == cmds.workspaceLayoutManager(query=True, current=True)

    def activate(self):
        """配置名で切り替える。Mayaの自動保存設定に従う副作用がある。

        切り替え時に現在の配置が自動保存される場合がある。UIのuiScriptや
        必要プラグインに依存し、任意のQtウィンドウは再生成できない。
        """
        cmds.workspaceLayoutManager(setCurrent=self.getName())

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

    @_getter_alias(getName)
    def name(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getName(*args, **kwargs)

    def _require_current(self):
        """別の配置を誤ってリセット・保存しないよう検証する。"""
        if not self.isCurrent():
            raise RuntimeError("Activate this workspace layout first")
