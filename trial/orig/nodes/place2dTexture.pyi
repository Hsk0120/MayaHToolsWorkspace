# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mayaのplace2dTextureノードを扱う。"""

from ..decorator import _edit_context
from .node import Node
from .shadingDependNode import ShadingDependNode
from .texture2d import Texture2d



class Place2dTexture(ShadingDependNode):
    """Mayaの継承型に対応するPlace2dTexture。値と接続はPlugで操作する。"""
    def connectTexture(self, texture: Texture2d | str, force: bool = ..., *, fast: bool = ...) -> Place2dTexture:
        """標準の2D配置アトリビュートをテクスチャへ接続する。

        Args:
            texture (Texture2d | str): 接続先の2Dテクスチャ。
            force (bool): 既存入力を置換するか。Plug.connectの規約に従う。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Place2dTexture: 自身。

        Raises:
            TypeError: fastがbool以外、または対象がTexture2dでない場合。
            RuntimeError: 接続できない場合。完了済み接続は自動で戻さない。
        """
        ...
