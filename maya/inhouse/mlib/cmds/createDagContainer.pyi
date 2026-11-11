# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""DAGコンテナを作成し、指定ノードを所属させる(``cmds.container(type="dagContainer")`` 相当)。

.. code-block:: python

    import mlib

    owner = mlib.createDagContainer("arm_rig", members=[group])
"""

from ..decorator import _pick_alias
from ..util import _UNSET
from .createContainer import _create_container
from typing import Iterable
from mlib.nodes.dagContainer import DagContainer
from mlib.nodes.node import Node


def createDagContainer(name: str = ..., members: str | Node | Iterable[Node | str] = ..., *, n: str = ...) -> DagContainer:
    """DAGコンテナを作成し、指定ノードを所属させる(作成 + ``addMembers``)。

    処理は :func:`~mlib.cmds.createContainer.createContainer` と同じで、型だけが違う。fast引数は持たない。
    nameは ``cmds.container`` と同じ短縮名 ``n`` でも受ける(長名と短縮名の同時指定はできない)。

    Args:
        name (str): 希望名。衝突時はMayaが一意名にする。既定 ``"dagContainer"``。
        members (str | Node | Iterable[Node | str]): 作成後に所属させるノード。省略時は空のまま。
        n (str): nameの短縮名。同時指定はできない。

    Returns:
        DagContainer: 作成したコンテナ。

    Raises:
        TypeError: nameと短縮名 ``n`` を同時に指定した場合。
        RuntimeError: Mayaが作成・所属を拒否した場合。
    """
    ...
