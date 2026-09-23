"""Maya の cluster デフォーマを扱う。"""

import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds

from .._core.registry import node_wrapper
from .node import Node


@node_wrapper("cluster")
class Cluster(Node):
    """Maya の cluster デフォーマラッパー。"""

    def weighted_node(self):
        """このクラスタに対応するハンドル transform を取得する。

        Returns:
            Node | None: cluster ハンドルの transform。見つからない場合は ``None``。
        """
        result = cmds.cluster(self.name(), query=True, weightedNode=True)
        if not result:
            return None
        if isinstance(result, (list, tuple)):
            result = result[0]
        return Node(result)

    def geometry(self):
        """このクラスタが変形するジオメトリ shape を取得する。

        Returns:
            list[Node]: 変形対象の shape。無ければ空リスト。
        """
        return [Node(mobject) for mobject in oma2.MFnGeometryFilter(self.mobject()).getOutputGeometry()]
