"""真偽値アトリビュートと値の反転操作を提供する。"""

from .plug import Plug


class BoolPlug(Plug):
    """bool アトリビュート用の Plug。"""

    def toggle(self, *, fast=False):
        """真偽値を反転する。

        Args:
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。:meth:`set` へそのまま渡す。

        Returns:
            Plug: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
            RuntimeError: 無効参照、またはロック・入力接続で書き込めない場合。
        """
        self.set(not self.get(), fast=fast)
        return self
