# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mesh の Edge とコレクション。"""

from .component import Component, Components
from .vertex import Vertices
from typing import Any, Iterator
from typing import overload



class Edge(Component):
    """Mesh の単一コンポーネント。"""
    shape_type: str
    component_type: str
    count_attribute: str
    def getVertices(self) -> Vertices:
        """接続する頂点群を取得する。

        Returns:
            Vertices: Maya の接続順の頂点群。
        """
        ...
_EDGE_GET_VERTICES: Any


class Edges(Components):
    """同一 Mesh の Edge 群。"""
    def __iter__(self) -> Iterator[Edge]: ...
    @overload
    def __getitem__(self, index: int) -> Edge: ...
    @overload
    def __getitem__(self, index: slice) -> Edges: ...
    component_class: Any
    def getVertices(self) -> Vertices:
        """接続する頂点群を取得する。

        Returns:
            Vertices: 保持順に集め、重複を除いた頂点群。
        """
        ...
