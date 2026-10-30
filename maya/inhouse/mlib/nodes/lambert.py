"""Mayaのlambertノードを扱う。"""

from typing import TYPE_CHECKING

from ..core.registry import _inherited_node_types
from .paintableShadingDependNode import PaintableShadingDependNode
from .shadingDependNode import ShadingDependNode

# Maya 2022にはpaintableShadingDependNodeがないため、実際の継承列に合わせる。
_SurfaceBase = (PaintableShadingDependNode
                if "paintableShadingDependNode" in _inherited_node_types("lambert")
                else ShadingDependNode)


# 型検査では両方の候補に共通する基底として扱う。
class Lambert(ShadingDependNode if TYPE_CHECKING else _SurfaceBase):
    """Mayaの継承型に対応するLambert。値と接続はPlugで操作する。"""
