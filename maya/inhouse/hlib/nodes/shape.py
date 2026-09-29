"""DAG シェイプの共通操作を提供する。"""

from .dagNode import DagNode
from .transform import Transform


class Shape(DagNode):
    """Maya DAG shape ノードの共通ラッパー。"""

    def parent_node(self):
        """親 Transform を取得する。

        Returns:
            Transform | None: 親 Transform。存在しない場合は ``None``。
        """
        parent = super().parent_node()
        return parent if isinstance(parent, Transform) else None

    def transform(self):
        """このShapeの親Transformを返す。

        Returns:
            Transform | None: 親Transform。存在しない場合は ``None``。
        """
        return self.parent_node()

    def is_intermediate_object(self):
        """中間オブジェクト（履歴用の非表示Shape）か判定する。

        Returns:
            bool: 中間オブジェクトの場合は True。
        """
        return self.dag_fn().isIntermediateObject
