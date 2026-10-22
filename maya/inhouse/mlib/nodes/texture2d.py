"""Mayaのtexture2dノードを扱う。"""

from .shadingDependNode import ShadingDependNode


class Texture2d(ShadingDependNode):
    """Mayaの継承型に対応するTexture2d。値と接続はPlugで操作する。"""

    def getPlacement(self):
        """uvCoordへの入力元ノード。通常はPlace2dTexture。

        Returns:
            Node | None: uvCoordへの入力元ノード。通常はPlace2dTexture。
        """
        source = self.getPlug('uvCoord').getSource(skipConversionNodes=False)
        return None if source is None else source.getNode()
