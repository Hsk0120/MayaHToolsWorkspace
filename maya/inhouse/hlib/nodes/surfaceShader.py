"""MayaのsurfaceShaderノードを扱う。"""

from .._core.registry import node_wrapper
from .node import Node


@node_wrapper("surfaceShader")
class SurfaceShader(Node):
    """Mayaの継承型に対応するSurfaceShader。値と接続はPlugで操作する。"""
