"""Maya の cluster デフォーマを扱う。"""

from .geometryFilter import GeometryFilter


class Cluster(GeometryFilter):
    """Maya の cluster デフォーマラッパー。"""

    def getWeightedNode(self):
        """このクラスタに対応するハンドル transform を取得する。

        Returns:
            Node | None: cluster ハンドルの transform。見つからない場合は ``None``。
        """
        source = self.getPlug("matrix").getSource()
        return None if source is None else source.getNode()
