# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""MayaのshadingDependNodeノードを扱う。"""

from .node import Node



class ShadingDependNode(Node):
    """Mayaの継承型に対応するShadingDependNode。値と接続はPlugで操作する。"""
