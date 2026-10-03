"""MayaのドッキングUIの容器を操作する。"""

import maya.cmds as cmds

from ..ui._windowReference import _WindowReference


class WorkspaceControl(_WindowReference):
    """既存workspaceControlへの参照。エディタ本体やプラグインは再生成しない。"""

    _command = "workspaceControl"

    @classmethod
    def list(cls):
        """list[WorkspaceControl]: 登録済みのドッキングUIを取得する。"""
        cls._require_gui()
        return [cls(name) for name in cmds.lsUI(type="workspaceControl") or []]

    def show(self):
        """非表示・最小化・折り畳みを解除し、タブをアクティブにする。"""
        cmds.workspaceControl(self.name(), edit=True, restore=True)

    def getFloating(self):
        """bool: 浮動状態か取得する。"""
        return bool(cmds.workspaceControl(self.name(), query=True, floating=True))

    def undock(self):
        """浮動ウィンドウへ切り離す。全体ロック中は拒否する。"""
        self._require_unlocked()
        cmds.workspaceControl(self.name(), edit=True, floating=True)

    def dock(self, side="right", target=None):
        """Maya本体または他のドックの横へ配置する。

        Args:
            side (str): left/right/top/bottom。
            target (WorkspaceControl | str | None): 相対配置先。省略時はMaya本体。
        """
        if side not in ("left", "right", "top", "bottom"):
            raise ValueError("side must be left, right, top or bottom")
        target_name = None if target is None else (target.name() if isinstance(target, WorkspaceControl) else WorkspaceControl(target).name())
        if target_name == self.name():
            raise ValueError("Cannot dock a control to itself")
        self._require_unlocked()
        if target_name is None:
            cmds.workspaceControl(self.name(), edit=True, dockToMainWindow=(side, False))
        else:
            cmds.workspaceControl(self.name(), edit=True, dockToControl=(target_name, side))

    def tabTo(self, target, index=-1):
        """他のドックとタブをまとめる。

        Args:
            target (WorkspaceControl | str): まとめる先のドック。
            index (int): タブ位置。-1は末尾。
        """
        if type(index) is not int:
            raise TypeError("index must be int")
        target = target if isinstance(target, WorkspaceControl) else WorkspaceControl(target)
        if target.name() == self.name():
            raise ValueError("Cannot tab a control to itself")
        self._require_unlocked()
        cmds.workspaceControl(self.name(), edit=True, tabToControl=(target.name(), index))

    def getSize(self):
        """tuple[int, int]: 現在の幅・高さを取得する。"""
        return (cmds.workspaceControl(self.name(), query=True, width=True),
                cmds.workspaceControl(self.name(), query=True, height=True))

    def setSize(self, width, height):
        """浮動状態の幅・高さを変更する。ドッキング中は拒否する。

        Args:
            width (int): 正の幅。
            height (int): 正の高さ。
        """
        width, height = self._pair(width, height, positive=True)
        if not self.getFloating():
            raise RuntimeError("Resize requires a floating workspace control")
        cmds.workspaceControl(self.name(), edit=True, resizeWidth=width, resizeHeight=height)

    def getCollapsed(self):
        """bool: タブの親が折り畳まれているか取得する。"""
        return bool(cmds.workspaceControl(self.name(), query=True, collapse=True))

    def setCollapsed(self, collapsed):
        """タブの親を折り畳む。同じグループの他タブにも影響する。

        Args:
            collapsed (bool): 折り畳むか。
        """
        collapsed = self._boolean(collapsed)
        cmds.workspaceControl(self.name(), edit=True, collapse=collapsed)

    def capture(self):
        """UiSnapshot: stateString・表示・折り畳み状態をメモリに退避する。

        stateStringはMayaとUI実装が管理する状態。周辺のタブ配置全体は
        WorkspaceLayoutで退避する。任意のエディタ内部データは含まない。
        """
        return self._capture({
                "state": cmds.workspaceControl(self.name(), query=True, stateString=True),
                "visible": self.getVisible(), "collapsed": self.getCollapsed()})

    def restore(self, snapshot):
        """同じUIへ退避状態を戻す。失われたUIは再生成しない。

        Args:
            snapshot (UiSnapshot): captureの返り値。
        """
        self._validate_snapshot(snapshot, {"state": str, "visible": bool, "collapsed": bool})
        cmds.workspaceControl(self.name(), edit=True, stateString=snapshot["state"])
        cmds.workspaceControl(self.name(), edit=True, collapse=snapshot["collapsed"])
        cmds.workspaceControl(self.name(), edit=True, visible=snapshot["visible"])

    @staticmethod
    def _require_unlocked():
        """ユーザーが有効にしたドッキングロックを迂回しない。"""
        from ..ui.workspaceLayout import WorkspaceLayout
        if WorkspaceLayout.getLocked():
            raise RuntimeError("Unlock the workspace layout before changing docking")
