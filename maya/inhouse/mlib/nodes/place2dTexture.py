"""Mayaのplace2dTextureノードを扱う。"""

from ..decorator import _edit_context, _pick_alias
from ..util import _UNSET
from .node import Node
from .shadingDependNode import ShadingDependNode
from .texture2d import Texture2d


class Place2dTexture(ShadingDependNode):
    """Mayaの継承型に対応するPlace2dTexture。値と接続はPlugで操作する。"""

    def connectTexture(self, texture, force=_UNSET, *, fast=False, f=_UNSET):
        """標準の2D配置アトリビュートをテクスチャへ接続する。

        Args:
            texture (Texture2d | str): 接続先の2Dテクスチャ。
            force (bool): 既存入力を置換するか。Plug.connectの規約に従う。別名 ``f`` も使用可能。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            Place2dTexture: 自身。

        Raises:
            TypeError: fastがbool以外、または対象がTexture2dでない場合。
            RuntimeError: 接続できない場合。完了済み接続は自動で戻さない。
        """
        force = _pick_alias(force, f, "force", "f", default=False)
        with _edit_context("mlibPlace2dTextureConnectTexture", fast):
            texture = Node._resolve_input(texture)
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
                        source.connectTo(destination, force=force, fast=fast)
            return self
