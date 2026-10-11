"""Mayaのコンポーネント（頂点・エッジ・フェース・CV・UV）とその要素群を公開する。

コンポーネントはシェイプを構成する要素への参照。
"""

from .component import Component, Components
from .cv import CV, CVs
from .edge import Edge, Edges
from .face import Face, Faces
from .pointComponent import PointComponent, PointComponents
from .uv import UV, UVs
from .vertex import Vertex, Vertices

__all__ = [
    "Component", "Components", "PointComponent", "PointComponents",
    "Vertex", "Vertices", "CV", "CVs", "Edge", "Edges",
    "Face", "Faces", "UV", "UVs",
]
