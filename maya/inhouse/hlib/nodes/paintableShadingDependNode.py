"""MayaのpaintableShadingDependNodeノードを扱う。"""
from .._core.registry import node_wrapper
from .shadingDependNode import ShadingDependNode


@node_wrapper("paintableShadingDependNode")
class PaintableShadingDependNode(ShadingDependNode):
    """Mayaの継承型に対応するPaintableShadingDependNode。値と接続はPlugで操作する。"""
