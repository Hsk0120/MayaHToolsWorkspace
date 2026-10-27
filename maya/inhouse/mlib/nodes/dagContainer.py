"""DAG階層とメンバーの所有を扱うMaya dagContainer。"""

import maya.cmds as cmds

from ..decorator import undoTransaction
from .container import Container
from .transform import Transform


class DagContainer(Transform, Container):
    """Transform操作とContainerの所属・公開操作を持つコンテナ。

    DAGの子もMaya標準の所属管理に従う。removeMembersは子を階層からも
    外し、removeContainerはメンバーを残して箱を解除する。
    解除時はローカル値が維持されるため、ワールド姿勢は変化する場合がある。

    基底の例外: Maya の dagContainer は transform の派生で container を継承しないが、
    このクラスは所属・公開操作を共有するため Container も基底に持つ。Maya の継承チェーン上の
    抽象祖先(entity・containerBase)に対応するクラスは無く、``isinstance`` は Maya の継承を
    表さない。継承の判定は ``isType()`` を使う。
    """

    @classmethod
    @undoTransaction("mlib.DagContainer.create")
    def create(cls, name="dagContainer", members=()):
        """DAGコンテナを作成し、指定ノードを所属させる(作成 + :meth:`addMembers`)。

        ``cmds.container(type="dagContainer")`` 専用の特化ビルダー。fast引数は持たない。

        Args:
            name (str): 希望名。衝突時はMayaが一意名にする。位置引数でも指定できる。
            members (str | Node | Iterable[Node | str]): 作成後に所属させるノード。省略時は空のまま。

        Returns:
            DagContainer: 作成したコンテナ。
        """
        container = cls(cmds.container(type="dagContainer", name=name))
        if members:
            container.addMembers(members)
        return container
