"""Maya の locator シェイプを扱う。"""

from ..decorator import _require_bool
from ..maths import Translate
from .shape import Shape


class Locator(Shape):
    """Maya の locator シェイプラッパー。"""

    def getPosition(self):
        """localPosition を取得する。

        Returns:
            Translate: localPosition の値。
        """
        return Translate(*self.getPlug("localPosition").get())

    def setPosition(self, value, *, fast=False):
        """localPosition を設定する。

        Args:
            value (Translate | Iterable[float]): 新しい localPosition。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Locator: 自身。

        Note:
            ``fast=True`` はOpenMaya直接更新(Undoなし)。既定の ``False`` は通常処理。
            fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        _require_bool(fast, "fast")
        self.getPlug("localPosition").set(tuple(value), fast=fast)
        return self
