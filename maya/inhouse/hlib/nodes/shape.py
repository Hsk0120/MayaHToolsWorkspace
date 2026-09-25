"""DAG シェイプの共通操作を提供する。"""

import maya.api.OpenMaya as om2

from .node import Node
from .transform import Transform


class Shape(Node):
    """Maya DAG shape ノードの共通ラッパー。"""

    def dag_path(self):
        """Shape の MDagPath を取得する。

        Returns:
            om2.MDagPath | None: 有効な DAG パス。取得できない場合は ``None``。
        """
        if self._dag_path is None and self.is_valid():
            self._dag_path = om2.MFnDagNode(self.mobject()).getPath()
        return self._dag_path

    def dag_node(self):
        """Shape 用の MFnDagNode を取得する。

        Returns:
            om2.MFnDagNode: この Shape の function set。
        """
        return om2.MFnDagNode(self.dag_path())

    def parent_path(self):
        """親ノードの DAG パスを取得する。

        Returns:
            om2.MDagPath | None: 親パス。親がない場合は ``None``。
        """
        if not self.is_valid() or self.dag_path().length() <= 1:
            return None
        parent_path = om2.MDagPath(self.dag_path())
        parent_path.pop()
        return parent_path

    def parent_transform(self):
        """親 Transform を取得する。

        Returns:
            Transform | None: 親 Transform。存在しない場合は ``None``。
        """
        parent_path = self.parent_path()
        if parent_path is None or not parent_path.node().hasFn(om2.MFn.kTransform):
            return None
        return Transform(parent_path)

    def transform(self):
        """このShapeの親Transformを返す。

        Returns:
            Transform | None: 親Transform。存在しない場合は ``None``。
        """
        return self.parent_transform()

    def is_intermediate_object(self):
        """中間オブジェクト（履歴用の非表示Shape）か判定する。

        Returns:
            bool: 中間オブジェクトの場合は True。
        """
        return self.dag_node().isIntermediateObject