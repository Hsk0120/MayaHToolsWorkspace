# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の cluster デフォーマを扱う。"""

import maya.api.OpenMayaAnim as oma2
from .node import Node



class Cluster(Node):
    """Maya の cluster デフォーマラッパー。"""
    def getWeightedNode(self) -> Node | None:
        """このクラスタに対応するハンドル transform を取得する。

        Returns:
            Node | None: cluster ハンドルの transform。見つからない場合は ``None``。
        """
        ...
    def getGeometry(self) -> list[Node]:
        """このクラスタが変形するジオメトリ shape を取得する。

        Returns:
            list[Node]: 変形対象の shape。無ければ空リスト。
        """
        ...
