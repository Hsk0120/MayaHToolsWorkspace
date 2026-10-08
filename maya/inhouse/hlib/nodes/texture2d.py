"""Mayaのtexture2dノードを扱う。"""

from .._core.getterAlias import _getter_alias
from .shadingDependNode import ShadingDependNode


class Texture2d(ShadingDependNode):
    """Mayaの継承型に対応するTexture2d。値と接続はPlugで操作する。"""

    def getPlacement(self):
        """uvCoordへの入力元ノード。通常はPlace2dTexture。

        Returns:
            Node | None: uvCoordへの入力元ノード。通常はPlace2dTexture。
        """
        source = self.getPlug("uvCoord").getSourceWithConversion()
        return None if source is None else source.getNode()

    @_getter_alias(getPlacement)
    def placement(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getPlacement(*args, **kwargs)
