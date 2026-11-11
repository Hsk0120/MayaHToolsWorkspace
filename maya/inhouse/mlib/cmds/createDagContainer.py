"""DAGコンテナを作成し、指定ノードを所属させる(``cmds.container(type="dagContainer")`` 相当)。

.. code-block:: python

    import mlib

    owner = mlib.createDagContainer("arm_rig", members=[group])
"""

from ..decorator import _pick_alias
from ..util import _UNSET
from .createContainer import _create_container


def createDagContainer(name=_UNSET, members=(), *, n=_UNSET):
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
    name = _pick_alias(name, n, "name", "n", default="dagContainer")
    return _create_container(name, members, "mlibCreateDagContainer", type="dagContainer")
