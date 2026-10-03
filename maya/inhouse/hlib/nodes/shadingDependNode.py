"""MayaのshadingDependNodeノードを扱う。"""

from .._core.registry import node_wrapper
from .node import Node


@node_wrapper("shadingDependNode")
class ShadingDependNode(Node):
    """Mayaの継承型に対応するShadingDependNode。値と接続はPlugで操作する。"""
