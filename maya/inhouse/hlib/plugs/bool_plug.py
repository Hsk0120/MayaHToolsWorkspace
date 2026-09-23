"""真偽値属性と値の反転操作を提供する。"""

from .._core.registry import plug_wrapper
from .plug import Plug


@plug_wrapper("bool")
class BoolPlug(Plug):
    """bool 属性用の Plug。"""

    def toggle(self):
        """真偽値を反転する。

        Returns:
            Plug: 自身。
        """
        self.set(not self.get())
        return self
