# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""名前・参照がシーンに存在するかを返す(``cmds.objExists`` 相当)。

.. code-block:: python

    import mlib

    if not mlib.objExists("rig_grp"):
        mlib.createNode("transform", name="rig_grp")
    mlib.objExists("rig_grp.translateX")  # アトリビュートも調べられる
"""

import maya.cmds as cmds
from ..core.object import Object
from mlib.components.component import Component
from mlib.nodes.node import Node
from mlib.plugs.plug import Plug


def objExists(target: str | Node | Plug | Component) -> bool:
    """名前・参照がシーンに存在するかを返す。

    文字列は ``cmds.objExists`` と同じく、ノード名・``"node.attr"``・コンポーネントを調べる。
    Node・Plug・Component は、参照先が生きているか(``isValid()``)で判定する。

    Args:
        target (str | Node | Plug | Component): 調べる名前または参照。列は受け付けない。

    Returns:
        bool: 存在すればTrue。

    Raises:
        TypeError: 文字列・Node・Plug・Component以外(列を含む)を渡した場合。
    """
    ...
