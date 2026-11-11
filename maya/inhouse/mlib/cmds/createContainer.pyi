# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""containerを作成し、指定ノードを所属させる(``cmds.container`` 相当)。

``cmds.container`` の規則(現在のcontainer文脈への自動所属など)に従う。空のcontainerだけが必要なら
``mlib.createNode("container", name=...)`` でも作れる。

.. code-block:: python

    import mlib

    owner = mlib.createContainer("arm_graph", members=[node])
"""

import maya.cmds as cmds
from ..decorator import _pick_alias, undoTransaction
from ..util import _UNSET
from typing import Iterable
from mlib.nodes.container import Container
from mlib.nodes.dagContainer import DagContainer
from mlib.nodes.node import Node


def createContainer(name: str = ..., members: str | Node | Iterable[Node | str] = ..., *, n: str = ...) -> Container:
    """containerを作成し、指定ノードを所属させる(作成 + ``addMembers``)。

    fast引数は持たない(cmds.containerにOpenMayaの同等機能が無い)。Undo有効時は1回で戻せる。
    nameは ``cmds.container`` と同じ短縮名 ``n`` でも受ける(長名と短縮名の同時指定はできない)。

    Args:
        name (str): 希望名。衝突時はMayaが一意名にする。既定 ``"container"``。
        members (str | Node | Iterable[Node | str]): 作成後に所属させるノード。省略時は空のまま。
        n (str): nameの短縮名。同時指定はできない。

    Returns:
        Container: 作成したcontainer。

    Raises:
        TypeError: nameと短縮名 ``n`` を同時に指定した場合。
        RuntimeError: Mayaが作成・所属を拒否した場合。
    """
    ...

def _create_container(name: str, members: Iterable, chunk: str, **flags) -> Container | DagContainer:
    """containerの作成と所属を1回のUndoにまとめる。

    Args:
        name (str): 希望名。
        members (Iterable): 所属させるノード。
        chunk (str): Undoチャンク名。
        **flags: ``cmds.container`` へ渡す型の指定。

    Returns:
        Container | DagContainer: 作成したcontainer。
    """
    ...
