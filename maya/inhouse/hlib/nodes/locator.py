"""Maya の locator シェイプを扱う。"""

from .._core.getterAlias import _getter_alias
from ..common._fast import fast_edit
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

    @fast_edit
    def setPosition(self, value, *, fast=False):
        """localPosition を設定する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Translate | Iterable[float]): 新しい localPosition。

        Returns:
            Locator: 自身。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        self.getPlug("localPosition").set(tuple(value))
        return self

    @_getter_alias(getPosition)
    def position(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPosition(*args, **kwargs)
