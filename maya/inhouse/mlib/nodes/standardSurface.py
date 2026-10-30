"""MayaのstandardSurfaceノードを扱う。"""

from typing import TYPE_CHECKING

from ..core.registry import _inherited_node_types
from .paintableShadingDependNode import PaintableShadingDependNode
from .shadingDependNode import ShadingDependNode

# Mayaのバージョンで異なる中間型の有無を反映する。
_SurfaceBase = (PaintableShadingDependNode
                if "paintableShadingDependNode" in _inherited_node_types("standardSurface")
                else ShadingDependNode)


# 型検査では両方の候補に共通する基底として扱う。
class StandardSurface(ShadingDependNode if TYPE_CHECKING else _SurfaceBase):
    """Mayaの継承型に対応するStandardSurface。値と接続はPlugで操作する。"""
