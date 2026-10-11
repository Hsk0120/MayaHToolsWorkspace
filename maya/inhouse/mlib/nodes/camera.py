"""Maya のカメラシェイプを扱う。"""

import maya.api.OpenMaya as om2

from .._core.getterAlias import _getter_alias
from .shape import Shape


class Camera(Shape):
    """Maya camera shape ノードのラッパー。"""

    def cameraFn(self):
        """MFnCamera を取得する。

        Returns:
            om2.MFnCamera: この camera の function set。
        """
        return om2.MFnCamera(self.mpath())

    def getFocalLength(self):
        """焦点距離を取得する。

        Returns:
            float: Maya の焦点距離。
        """
        return self.cameraFn().focalLength

    @_getter_alias(getFocalLength)
    def focalLength(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getFocalLength(*args, **kwargs)
