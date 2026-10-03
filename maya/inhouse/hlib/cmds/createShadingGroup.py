"""シェーディンググループを作成する。"""

import maya.cmds as cmds

from .._core.flags import flag_aliases
from ..decorators.undo import undoChunk


@flag_aliases(n="name")
@undoChunk("hlibCreateShadingGroup")
def createShadingGroup(shader=None, name=None):
    """レンダー用セットを作成し、必要なら表面シェーダーを接続する。

    Args:
        shader (Node | Plug | str | None): 接続元。省略時は未接続。
        name (str | None): 作成名。
    Returns:
        ShadingEngine: 作成したセット。
    """
    from ..nodes.shadingEngine import ShadingEngine
    flags = {} if name is None else {"name": name}
    group = ShadingEngine(cmds.sets(renderable=True, noSurfaceShader=True, empty=True, **flags))
    if shader is not None:
        group.setShader(shader)
    return group
