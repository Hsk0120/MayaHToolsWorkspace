"""MayaのpaintableShadingDependNodeノードを扱う。"""

from .shadingDependNode import ShadingDependNode


class PaintableShadingDependNode(ShadingDependNode):
    """Mayaの継承型に対応するPaintableShadingDependNode。値と接続はPlugで操作する。"""
