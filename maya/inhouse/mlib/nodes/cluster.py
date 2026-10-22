"""Maya の cluster デフォーマを扱う。"""

import maya.api.OpenMayaAnim as oma2

from .node import Node


class Cluster(Node):
    """Maya の cluster デフォーマラッパー。"""

    def getWeightedNode(self):
        """このクラスタに対応するハンドル transform を取得する。

        Returns:
            Node | None: cluster ハンドルの transform。見つからない場合は ``None``。
        """
        source = self.getPlug("matrix").getSource(skipConversionNodes=False)
        return None if source is None else source.getNode()

    def getGeometry(self):
        """このクラスタが変形するジオメトリ shape を取得する。

        Returns:
            list[Node]: 変形対象の shape。無ければ空リスト。
        """
        return [Node(mobject) for mobject in oma2.MFnGeometryFilter(self.mnode()).getOutputGeometry()]
