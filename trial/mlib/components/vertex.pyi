# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mesh の頂点と頂点コレクション。"""

from .pointComponent import PointComponent, PointComponents
from typing import Any, Iterator
from typing import overload



class Vertex(PointComponent):
    """Mesh 上の単一頂点。番号はゼロ始まり。"""
    shape_type: str
    component_type: str
    count_attribute: str


class Vertices(PointComponents):
    """同一 Mesh の頂点群。座標取得・部分列取得・ミラーに対応する。"""
    def __iter__(self) -> Iterator[Vertex]: ...
    @overload
    def __getitem__(self, index: int) -> Vertex: ...
    @overload
    def __getitem__(self, index: slice) -> Vertices: ...
    component_class: Any
