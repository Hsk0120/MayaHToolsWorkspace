# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""MayaのpaintableShadingDependNodeノードを扱う。"""

from .shadingDependNode import ShadingDependNode



class PaintableShadingDependNode(ShadingDependNode):
    """Mayaの継承型に対応するPaintableShadingDependNode。値と接続はPlugで操作する。"""
