"""Mayaのfileノードを扱う。"""

from ..decorator import _edit_context
from .texture2d import Texture2d


class File(Texture2d):
    """Mayaの継承型に対応するFile。値と接続はPlugで操作する。"""

    def getFilePath(self):
        """ファイルパス。UDIM等のトークンは展開せず返す。

        Returns:
            str: ファイルパス。UDIM等のトークンは展開せず返す。
        """
        return self.getPlug("fileTextureName").get()

    def setFilePath(self, path, *, fast=False):
        """ファイルパスを設定する。存在確認・コピーは行わない。

        Args:
            path (str): パスまたはUDIM等のトークンを含むパターン。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            File: 自身。

        Raises:
            TypeError: fastがbool以外、またはpathがstr以外の場合。
            RuntimeError: ロックや入力接続により設定できない場合。

        Note:
            ``fast=True`` は通常と同じ検証の後にOpenMayaで直接更新する(Undoなし)。
        """
        with _edit_context("mlibFileSetFilePath", fast):
            if not isinstance(path, str):
                raise TypeError("path must be a string")
            self.getPlug("fileTextureName").set(path, fast=fast)
            return self

    def getColorSpace(self):
        """現在の入力色空間名。

        Returns:
            str: 現在の入力色空間名。
        """
        return self.getPlug("colorSpace").get()

    def setColorSpace(self, name, *, fast=False):
        """入力色空間を設定する。

        名前は検証せず、そのまま保持する。利用できる色空間は色管理の設定(OCIO構成など)で
        変わるため、現在の設定に無い名前も設定できる。

        Args:
            name (str): 色空間名。現在のMaya色管理設定で利用可能な名前を指定する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            File: 自身。パス変更時の自動ルール設定は変更しない。

        Raises:
            TypeError: fastがbool以外、またはnameがstr以外の場合。
            RuntimeError: ロックや入力接続により設定できない場合。

        Note:
            ``fast=True`` は通常と同じ検証の後にOpenMayaで直接更新する(Undoなし)。
        """
        with _edit_context("mlibFileSetColorSpace", fast):
            if not isinstance(name, str):
                raise TypeError("name must be a string")
            self.getPlug("colorSpace").set(name, fast=fast)
            return self
