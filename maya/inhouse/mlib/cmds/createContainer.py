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


def createContainer(name=_UNSET, members=(), *, n=_UNSET):
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
    name = _pick_alias(name, n, "name", "n", default="container")
    return _create_container(name, members, "mlibCreateContainer")


def _create_container(name, members, chunk, **flags):
    """containerの作成と所属を1回のUndoにまとめる。

    Args:
        name (str): 希望名。
        members (Iterable): 所属させるノード。
        chunk (str): Undoチャンク名。
        **flags: ``cmds.container`` へ渡す型の指定。

    Returns:
        Container | DagContainer: 作成したcontainer。
    """
    # nodes はcmdsを参照するため、循環importを避けて関数内で読み込む。
    from ..nodes.node import Node

    with undoTransaction(chunk):
        container = Node(cmds.container(name=name, **flags))
        if members:
            container.addMembers(members)
        return container
