"""Maya の locator シェイプを扱う。"""

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

    def set_position(self, value):
        """localPosition を設定する。

        Args:
            value (Translate | Iterable[float]): 新しい localPosition。

        Returns:
            Locator: 自身。
        """
        self.plug("localPosition").set(tuple(value))
        return self
