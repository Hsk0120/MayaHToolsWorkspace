"""Mesh の Edge とコレクション。"""

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
        self._require_valid()
        return Vertices(self.shape, self.shape._geometry_fn().getEdgeVertices(self.index))


_EDGE_GET_VERTICES = Edge.getVertices


class Edges(Components):
    """同一 Mesh の Edge 群。"""

    component_class = Edge

    def getVertices(self):
        """接続する頂点群を取得する。

        Returns:
            Vertices: 保持順に集め、重複を除いた頂点群。
        """
        if not (self._uses_standard_iteration(Edge) and self._uses_standard_vertices()
                and Edge.getVertices is _EDGE_GET_VERTICES):
            return Vertices(self.shape, (v.index for item in self for v in item.getVertices()))
        indices = self._mesh_vertex_indices("numEdges", "getEdgeVertices")
        return Vertices(self.shape, indices)
