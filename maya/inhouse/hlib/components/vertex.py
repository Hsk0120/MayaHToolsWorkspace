"""Mesh の頂点と頂点コレクション。"""

from .point_component import PointComponent, PointComponents


class Vertex(PointComponent):
    """Mesh 上の単一頂点。番号はゼロ始まり。"""

    shape_type = "mesh"
    component_type = "vtx"
    count_attribute = "num_vertices"


class Vertices(PointComponents):
    """同一 Mesh の頂点群。座標取得・部分列取得・ミラーに対応する。"""

    component_class = Vertex
