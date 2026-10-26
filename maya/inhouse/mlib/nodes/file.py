"""Mayaのfileノードを扱う。"""

from ..decorator import undoChunk
from .texture2d import Texture2d


class File(Texture2d):
    """Mayaの継承型に対応するFile。値と接続はPlugで操作する。"""

    def getFilePath(self):
        """ファイルパス。UDIM等のトークンは展開せず返す。

        Returns:
            str: ファイルパス。UDIM等のトークンは展開せず返す。
        """
        return self.getPlug("fileTextureName").get()

    @undoChunk("mlibFileSetPath")
    def setFilePath(self, path):
        """ファイルパスを設定する。存在確認・コピーは行わない。

        Args:
            path (str): パスまたはUDIM等のトークンを含むパターン。

        Returns:
            File: 自身。

        Raises:
            TypeError: pathがstr以外の場合。
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

    @undoChunk("mlibFileSetColorSpace")
    def setColorSpace(self, name):
        """入力色空間を設定する。

        名前は検証せず、そのまま保持する。利用できる色空間は色管理の設定(OCIO構成など)で
        変わるため、現在の設定に無い名前も設定できる。

        Args:
            name (str): 色空間名。現在のMaya色管理設定で利用可能な名前を指定する。

        Returns:
            File: 自身。パス変更時の自動ルール設定は変更しない。

        Raises:
            TypeError: nameがstr以外の場合。
        """
        if not isinstance(name, str):
            raise TypeError("name must be a string")
        self.getPlug("colorSpace").set(name)
        return self
