"""Mesh の Edge とコレクション。"""
from .component import Component, Components
from .vertex import Vertices


class Edge(Component):
    """Mesh の単一コンポーネント。"""
    shape_type = "mesh"
    component_type = "e"
    count_attribute = "num_edges"

    def vertices(self):
        """接続する頂点群を取得する。

        Returns:
            Vertices: Maya の接続順の頂点群。
        """
        self._validate()
        return Vertices(self.shape, self.shape.mesh_fn().getEdgeVertices(self.index))


class Edges(Components):
    """同一 Mesh の Edge 群。"""
    component_class = Edge

    def vertices(self):
        """接続する頂点群を取得する。

        Returns:
            Vertices: 保持順に集め、重複を除いた頂点群。
        """
        return Vertices(self.shape, (v.index for item in self for v in item.vertices()))
