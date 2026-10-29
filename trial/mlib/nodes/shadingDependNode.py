"""MayaのshadingDependNodeノードを扱う。"""

from .node import Node


class ShadingDependNode(Node):
    """Mayaの継承型に対応するShadingDependNode。値と接続はPlugで操作する。"""
