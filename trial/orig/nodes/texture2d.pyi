# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mayaのtexture2dノードを扱う。"""

from .shadingDependNode import ShadingDependNode
from mlib.nodes.node import Node



class Texture2d(ShadingDependNode):
    """Mayaの継承型に対応するTexture2d。値と接続はPlugで操作する。"""
    def getPlacement(self) -> Node | None:
        """uvCoordへの入力元ノード。通常はPlace2dTexture。

        Returns:
            Node | None: uvCoordへの入力元ノード。通常はPlace2dTexture。
        """
        ...
