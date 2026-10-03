"""Maya標準windowの表示・サイズ・位置を操作する。"""
import maya.cmds as cmds
from hlib.ui._windowReference import _WindowReference


class Window(_WindowReference):
    """既存のcmds.windowを参照する。任意のQtウィジェットは対象外。"""

    _command = "window"

    @classmethod
    def list(cls):
        """list[Window]: Mayaに登録されたwindowを取得する。"""
        cls._require_gui()
        return [cls(name) for name in cmds.lsUI(windows=True) or []]

    def show(self):
        """ウィンドウを表示する。"""
        cmds.showWindow(self.name())

    def get_size(self):
        """tuple[int, int]: 枠を除く幅・高さをピクセルで取得する。"""
        return tuple(cmds.window(self.name(), query=True, widthHeight=True))

    def set_size(self, width, height):
        """ウィンドウの幅・高さを変更する。

        Args:
            width (int): 幅。正数。
            height (int): 高さ。正数。
        """
        size = self._pair(width, height, positive=True)
        cmds.window(self.name(), edit=True, widthHeight=size)

    def getPosition(self):
        """tuple[int, int]: 左・上の位置(x, y)を取得する。"""
        top, left = cmds.window(self.name(), query=True, topLeftCorner=True)
        return left, top

    def setPosition(self, x, y):
        """ウィンドウの左上位置を変更する。

        Args:
            x (int): 左端。
            y (int): 上端。
        """
        x, y = self._pair(x, y)
        cmds.window(self.name(), edit=True, topLeftCorner=(y, x))

    def get_resizable(self):
        """bool: ユーザーがサイズを変更できるか取得する。"""
        return bool(cmds.window(self.name(), query=True, sizeable=True))

    def set_resizable(self, enabled):
        """サイズ変更を許可する。移動禁止やドッキングロックではない。

        Args:
            enabled (bool): サイズ変更を許可するか。
        """
        enabled = self._boolean(enabled)
        cmds.window(self.name(), edit=True, sizeable=enabled)

    def capture(self):
        """UiSnapshot: ネイティブwindow状態と表示・サイズ変更許可をメモリへ退避する。

        同一セッション・同一UIへのrestore用。内容や実行コードは保存しない。
        """
        return self._capture({
                "state": cmds.window(self.name(), query=True, state=True),
                "visible": self.get_visible(), "resizable": self.get_resizable()})

    def restore(self, snapshot):
        """capture時点の状態を同じUIへ復元する。再生成しない。

        Args:
            snapshot (UiSnapshot): captureの返り値。
        """
        self._validate_snapshot(snapshot, {"state": str, "visible": bool, "resizable": bool})
        cmds.window(self.name(), edit=True, state=snapshot["state"])
        self.set_resizable(snapshot["resizable"])
        cmds.window(self.name(), edit=True, visible=snapshot["visible"])
