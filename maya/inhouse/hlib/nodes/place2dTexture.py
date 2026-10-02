"""Mayaのplace2dTextureノードを扱う。"""
from .._core.registry import node_wrapper
from .shadingDependNode import ShadingDependNode
from ..decorators.undo import undo_chunk


@node_wrapper("place2dTexture")
class Place2dTexture(ShadingDependNode):
    """Mayaの継承型に対応するPlace2dTexture。値と接続はPlugで操作する。"""

    @undo_chunk("hlibPlace2dConnect")
    def connect_texture(self, texture, force=False):
        """標準の2D配置アトリビュートをテクスチャへ接続する。

        Args:
            texture (Texture2d | str): 接続先の2Dテクスチャ。
            force (bool): 既存入力を置換するか。Plug.connectの規約に従う。
        Returns:
            Place2dTexture: 自身。
        Raises:
            TypeError: 対象がTexture2dでない場合。
            RuntimeError: 接続できない場合。完了済み接続は自動で戻さない。
        """
        from hlib.nodes.node import Node as _InputNode
        from .texture2d import Texture2d
        texture = _InputNode._resolve_input(texture)
        if not isinstance(texture, Texture2d):
            raise TypeError("texture must be Texture2d")
        names = ("coverage", "translateFrame", "rotateFrame", "mirrorU", "mirrorV",
                 "stagger", "wrapU", "wrapV", "repeatUV", "offset", "rotateUV",
                 "noiseUV", "vertexUvOne", "vertexUvTwo", "vertexUvThree", "vertexCameraOne")
        pairs = [(name, name) for name in names] + [("outUV", "uvCoord"), ("outUvFilterSize", "uvFilterSize")]
        for origin, target in pairs:
            if texture.has_attribute(target):
                source = self.plug(origin)
                destination = texture.plug(target)
                if destination.source() != source:
                    source.connect(destination, force=force)
        return self
