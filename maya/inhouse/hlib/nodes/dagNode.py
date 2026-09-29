"""TransformとShapeに共通するDAG階層へのアクセスを提供する。"""

import maya.api.OpenMaya as om2

from .node import Node


class DagNode(Node):
    """DAGノードの共通基底。具象ラッパーの型登録は変更しない。"""

    __hlib_public__ = True

    def dag_path(self):
        """保持するインスタンスのDAGパスを取得する。

        Returns:
            om2.MDagPath: この参照が保持するDAGパス。

        Raises:
            RuntimeError: 保持していたパスが無効な場合。他のインスタンスへ切り替えない。
        """
        return self._current_dag_path()

    def dag_fn(self):
        """保持するDAGパスに対応するfunction setを取得する。

        Returns:
            om2.MFnDagNode: このインスタンスのfunction set。

        Raises:
            RuntimeError: 保持していたパスが無効な場合。
        """
        return om2.MFnDagNode(self.dag_path())

    def parent_path(self):
        """保持するインスタンスの親パスを取得する。

        Returns:
            om2.MDagPath | None: 親のパス。無効なノード、またはルートならNone。

        Raises:
            RuntimeError: ノードは存在するが保持していたパスが無効な場合。
        """
        if not self.is_valid():
            return None
        path = self.dag_path()
        if path.length() <= 1:
            return None
        parent = om2.MDagPath(path)
        parent.pop()
        return parent

    def parent_node(self):
        """親ノードを汎用 Node として取得する。

        Returns:
            Node | None: 親ノード。親がない場合は ``None``。
        """
        parent_path = self.parent_path()
        return Node(parent_path) if parent_path is not None else None
