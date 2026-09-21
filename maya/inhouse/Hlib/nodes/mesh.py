"""Mesh shape wrapper."""

import maya.api.OpenMaya as om2

from ..core.registry import node_wrapper
from .shape import Shape


@node_wrapper("mesh")
class Mesh(Shape):
    """Maya mesh shape ノードのラッパー。"""

    def mesh_fn(self):
        """MFnMesh を取得する。

        Returns:
            om2.MFnMesh: この mesh の function set。
        """
        return om2.MFnMesh(self.dag_path())

    @property
    def num_vertices(self):
        """頂点数を取得する。

        Returns:
            int: mesh の頂点数。
        """
        return self.mesh_fn().numVertices

    @property
    def num_polygons(self):
        """ポリゴン数を取得する。

        Returns:
            int: mesh のポリゴン数。
        """
        return self.mesh_fn().numPolygons