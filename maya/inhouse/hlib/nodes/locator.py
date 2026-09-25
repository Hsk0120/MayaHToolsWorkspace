"""Maya の locator シェイプを扱う。"""

from ..decorators._fast import fast_edit

from .._core.registry import node_wrapper
from ..maths import Translate
from .shape import Shape


@node_wrapper("locator")
class Locator(Shape):
    """Maya の locator シェイプラッパー。"""

    def get_position(self):
        """localPosition を取得する。

        Returns:
            Translate: localPosition の値。
        """
        return Translate(*self.plug("localPosition").get())

    @fast_edit
    def set_position(self, value, *, fast=False):
        """localPosition を設定する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Translate | Iterable[float]): 新しい localPosition。

        Returns:
            Locator: 自身。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        self.plug("localPosition").set(tuple(value))
        return self
