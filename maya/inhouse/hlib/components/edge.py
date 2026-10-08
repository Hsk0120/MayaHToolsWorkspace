"""Mesh の Edge とコレクション。"""

from .._core.getterAlias import _getter_alias
from .component import Component, Components
from .vertex import Vertices


class Edge(Component):
    """Mesh の単一コンポーネント。"""

    shape_type = "mesh"
    component_type = "e"
    count_attribute = "getNumEdges"

    def getVertices(self):
        """接続する頂点群を取得する。

        Returns:
            Vertices: Maya の接続順の頂点群。
        """
        self._validate()
        return Vertices(self.shape, self.shape.meshFn().getEdgeVertices(self.index))

    @_getter_alias(getVertices)
    def vertices(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getVertices(*args, **kwargs)


class Edges(Components):
    """同一 Mesh の Edge 群。"""

    component_class = Edge

    def getVertices(self):
        """接続する頂点群を取得する。

        Returns:
            Vertices: 保持順に集め、重複を除いた頂点群。
        """
        return Vertices(self.shape, (v.index for item in self for v in item.getVertices()))

    @_getter_alias(getVertices)
    def vertices(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getVertices(*args, **kwargs)
