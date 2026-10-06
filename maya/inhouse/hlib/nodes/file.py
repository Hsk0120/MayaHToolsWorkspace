"""Mayaのfileノードを扱う。"""

from .._core.registry import node_wrapper
from ..decorators.undo import undoChunk
from .texture2d import Texture2d


@node_wrapper("file")
class File(Texture2d):
    """Mayaの継承型に対応するFile。値と接続はPlugで操作する。"""

    def getFilePath(self):
        """ファイルパス。UDIM等のトークンは展開せず返す。

        Returns:
            str: ファイルパス。UDIM等のトークンは展開せず返す。
        """
        return self.getPlug("fileTextureName").get()

    @undoChunk("hlibFileSetPath")
    def setFilePath(self, path):
        """ファイルパスを設定する。存在確認・コピーは行わない。

        Args:
            path (str): パスまたはUDIM等のトークンを含むパターン。
        Returns:
            File: 自身。
        """
        if not isinstance(path, str):
            raise TypeError("path must be a string")
        self.getPlug("fileTextureName").set(path)
        return self

    def getColorSpace(self):
        """現在の入力色空間名。

        Returns:
            str: 現在の入力色空間名。
        """
        return self.getPlug("colorSpace").get()

    @undoChunk("hlibFileSetColorSpace")
    def setColorSpace(self, name):
        """入力色空間を設定する。

        Args:
            name (str): 現在のMaya色管理設定で利用可能な色空間名。
        Returns:
            File: 自身。パス変更時の自動ルール設定は変更しない。
        """
        self.getPlug("colorSpace").set(name)
        return self
