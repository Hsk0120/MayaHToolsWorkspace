"""真偽値アトリビュートと値の反転操作を提供する。"""

from .plug import Plug


class BoolPlug(Plug):
    """bool アトリビュート用の Plug。"""

    def toggle(self):
        """真偽値を反転する。

        Returns:
            Plug: 自身。
        """
        self.set(not self.get())
        return self
