# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""MayaのstandardSurfaceノードを扱う。"""

from typing import TYPE_CHECKING
from ..core.registry import _inherited_node_types
from .paintableShadingDependNode import PaintableShadingDependNode
from .shadingDependNode import ShadingDependNode
from typing import Any

_SurfaceBase: Any


class StandardSurface(ShadingDependNode if TYPE_CHECKING else _SurfaceBase):
    """Mayaの継承型に対応するStandardSurface。値と接続はPlugで操作する。"""
