# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mayaのlambertノードを扱う。"""

from ..core.registry import _inherited_node_types
from .paintableShadingDependNode import PaintableShadingDependNode
from .shadingDependNode import ShadingDependNode
from typing import Any

_SurfaceBase: Any


class Lambert(_SurfaceBase):
    """Mayaの継承型に対応するLambert。値と接続はPlugで操作する。"""
