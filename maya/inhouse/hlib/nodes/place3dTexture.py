"""Mayaのplace3dTextureノードを扱う。"""

from .._core.registry import node_wrapper
from .transform import Transform


@node_wrapper("place3dTexture")
class Place3dTexture(Transform):
    """Mayaの継承型に対応するPlace3dTexture。値と接続はPlugで操作する。"""
