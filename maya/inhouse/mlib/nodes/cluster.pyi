# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の cluster デフォーマを扱う。"""

from .geometryFilter import GeometryFilter
from mlib.nodes.node import Node



class Cluster(GeometryFilter):
    """Maya の cluster デフォーマラッパー。"""
    def getWeightedNode(self) -> Node | None:
        """このクラスタに対応するハンドル transform を取得する。

        Returns:
            Node | None: cluster ハンドルの transform。見つからない場合は ``None``。
        """
        ...
