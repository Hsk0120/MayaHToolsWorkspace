"""MayaのstandardSurfaceノードを扱う。"""

from ..core.registry import _inherited_node_types
from .paintableShadingDependNode import PaintableShadingDependNode
from .shadingDependNode import ShadingDependNode

# Mayaのバージョンで異なる中間型の有無を反映する。
_SurfaceBase = (PaintableShadingDependNode
                if "paintableShadingDependNode" in _inherited_node_types("standardSurface")
                else ShadingDependNode)


class StandardSurface(_SurfaceBase):
    """Mayaの継承型に対応するStandardSurface。値と接続はPlugで操作する。"""
