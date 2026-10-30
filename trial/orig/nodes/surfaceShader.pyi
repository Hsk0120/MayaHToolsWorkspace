# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""MayaのsurfaceShaderノードを扱う。"""

from .node import Node



class SurfaceShader(Node):
    """Mayaの継承型に対応するSurfaceShader。値と接続はPlugで操作する。"""
