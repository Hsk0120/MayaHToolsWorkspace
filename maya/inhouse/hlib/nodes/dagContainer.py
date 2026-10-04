"""DAG階層とメンバーの所有を扱うMaya dagContainer。"""

import maya.cmds as cmds

from .._core.registry import node_wrapper
from ..decorators.undo import undoTransaction
from .container import Container
from .transform import Transform


@node_wrapper("dagContainer")
class DagContainer(Transform, Container):
    """Transform操作とContainerの所属・公開操作を持つコンテナ。

    DAGの子もMaya標準の所属管理に従う。removeMembersは子を階層からも
    外し、removeContainerはメンバーを残して箱を解除する。
    解除時はローカル値が維持されるため、ワールド姿勢は変化する場合がある。
    """

    @classmethod
    @undoTransaction("hlib.DagContainer.create")
    def create(cls, name="dagContainer"):
        """空のDAGコンテナを作成する。

        Args:
            name (str): 希望名。衝突時はMayaが一意名にする。

        Returns:
            DagContainer: 作成したコンテナ。
        """
        return cls(cmds.container(type="dagContainer", name=name))
