"""MayaのstandardSurfaceノードを扱う。"""

import maya.cmds as cmds

from .paintableShadingDependNode import PaintableShadingDependNode
from .shadingDependNode import ShadingDependNode

# Mayaのバージョンで異なる中間型の有無を反映する。
_SurfaceBase = (PaintableShadingDependNode
                if "paintableShadingDependNode" in cmds.nodeType("standardSurface", isTypeName=True, inherited=True)
                else ShadingDependNode)


class StandardSurface(_SurfaceBase):
    """Mayaの継承型に対応するStandardSurface。値と接続はPlugで操作する。"""
