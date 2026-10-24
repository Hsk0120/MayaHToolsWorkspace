"""Mayaのplace2dTextureノードを扱う。"""

from ..decorator import undoChunk
from ..util import _ArgumentError, _UNSET
from .shadingDependNode import ShadingDependNode


class Place2dTexture(ShadingDependNode):
    """Mayaの継承型に対応するPlace2dTexture。値と接続はPlugで操作する。"""

    def connectTexture(self, texture, force=_UNSET, *, f=_UNSET):
        """標準の2D配置アトリビュートをテクスチャへ接続する。

        Args:
            texture (Texture2d | str): 接続先の2Dテクスチャ。
            force (bool): 既存入力を置換するか。Plug.connectの規約に従う。 別名 ``f`` も使用可能。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            Place2dTexture: 自身。

        Raises:
            TypeError: 対象がTexture2dでない場合。
            RuntimeError: 接続できない場合。完了済み接続は自動で戻さない。
        """
        if f is not _UNSET:
            if force is not _UNSET:
                raise _ArgumentError("Specify only one of 'force' and 'f'")
            force = f
        if force is _UNSET:
            force = False
        with undoChunk("mlibPlace2dConnect"):
            from .node import Node as _InputNode
            from .texture2d import Texture2d
            texture = _InputNode._resolve_input(texture)
            if not isinstance(texture, Texture2d):
                raise TypeError("texture must be Texture2d")
            names = ("coverage", "translateFrame", "rotateFrame", "mirrorU", "mirrorV",
                     "stagger", "wrapU", "wrapV", "repeatUV", "offset", "rotateUV",
                     "noiseUV", "vertexUvOne", "vertexUvTwo", "vertexUvThree", "vertexCameraOne")
            pairs = [(name, name) for name in names] + [("outUV", "uvCoord"), ("outUvFilterSize", "uvFilterSize")]
            for origin, target in pairs:
                if texture.hasAttr(target):
                    source = self.getPlug(origin)
                    destination = texture.getPlug(target)
                    if destination.getSource(skipConversionNodes=False) != source:
                        source.connectTo(destination, force=force)
            return self
