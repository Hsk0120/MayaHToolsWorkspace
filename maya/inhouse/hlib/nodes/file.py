"""Mayaのfileノードを扱う。"""
from .._core.registry import node_wrapper
from .texture2d import Texture2d
from ..decorators.undo import undo_chunk


@node_wrapper("file")
class File(Texture2d):
    """Mayaの継承型に対応するFile。値と接続はPlugで操作する。"""

    def getFilePath(self):
        """str: ファイルパス。UDIM等のトークンは展開せず返す。"""
        return self.plug("fileTextureName").get()

    @undo_chunk("hlibFileSetPath")
    def setFilePath(self, path):
        """ファイルパスを設定する。存在確認・コピーは行わない。

        Args:
            path (str): パスまたはUDIM等のトークンを含むパターン。
        Returns:
            File: 自身。
        """
        if not isinstance(path, str):
            raise TypeError("path must be a string")
        self.plug("fileTextureName").set(path)
        return self

    def getColorSpace(self):
        """str: 現在の入力色空間名。"""
        return self.plug("colorSpace").get()

    @undo_chunk("hlibFileSetColorSpace")
    def setColorSpace(self, name):
        """入力色空間を設定する。

        Args:
            name (str): 現在のMaya色管理設定で利用可能な色空間名。
        Returns:
            File: 自身。パス変更時の自動ルール設定は変更しない。
        """
        self.plug("colorSpace").set(name)
        return self
