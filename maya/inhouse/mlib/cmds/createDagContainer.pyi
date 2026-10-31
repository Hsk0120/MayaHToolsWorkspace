# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""DAGコンテナを作成し、指定ノードを所属させる(``cmds.container(type="dagContainer")`` 相当)。

.. code-block:: python

    import mlib

    owner = mlib.createDagContainer("arm_rig", members=[group])
"""

from .createContainer import _create_container
from typing import Iterable
from mlib.nodes.dagContainer import DagContainer
from mlib.nodes.node import Node


def createDagContainer(name: str = ..., members: str | Node | Iterable[Node | str] = ...) -> DagContainer:
    """DAGコンテナを作成し、指定ノードを所属させる(作成 + ``addMembers``)。

    処理は :func:`~mlib.cmds.createContainer.createContainer` と同じで、型だけが違う。fast引数は持たない。

    Args:
        name (str): 希望名。衝突時はMayaが一意名にする。
        members (str | Node | Iterable[Node | str]): 作成後に所属させるノード。省略時は空のまま。

    Returns:
        DagContainer: 作成したコンテナ。

    Raises:
        RuntimeError: Mayaが作成・所属を拒否した場合。
    """
    ...
