"""Mayaのtexture2dノードを扱う。"""

from .._core.registry import node_wrapper
from .shadingDependNode import ShadingDependNode


@node_wrapper("texture2d")
class Texture2d(ShadingDependNode):
    """Mayaの継承型に対応するTexture2d。値と接続はPlugで操作する。"""

    def getPlacement(self):
        """Node | None: uvCoordへの入力元ノード。通常はPlace2dTexture。"""
        source = self.plug("uvCoord").sourceWithConversion()
        return None if source is None else source.node()
