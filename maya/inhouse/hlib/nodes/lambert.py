"""Mayaのlambertノードを扱う。"""
from .._core.registry import node_wrapper
import maya.cmds as cmds
from .paintableShadingDependNode import PaintableShadingDependNode
from .shadingDependNode import ShadingDependNode

# Maya 2022にはpaintableShadingDependNodeがないため、実際の継承列に合わせる。
_SurfaceBase = (PaintableShadingDependNode
                if "paintableShadingDependNode" in cmds.nodeType("lambert", isTypeName=True, inherited=True)
                else ShadingDependNode)


@node_wrapper("lambert")
class Lambert(_SurfaceBase):
    """Mayaの継承型に対応するLambert。値と接続はPlugで操作する。"""
