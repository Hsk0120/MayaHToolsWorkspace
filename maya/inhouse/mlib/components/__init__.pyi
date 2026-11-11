# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mayaのコンポーネント(頂点・エッジ・フェース・CV・UV・頂点フェース・曲面のCV・ラティスの点)とその要素群を公開する。

コンポーネントはシェイプを構成する要素への参照。頂点・CV・UVは座標の照会に加えて、
座標の書込み(setPosition・setPositions等)と頂点・CVの反転(mirror)ができる。
曲面のCV・ラティスの点も頂点・CVと同じ座標の照会・書込みができる。
"""

from .component import Component, Components
from .cv import CV, CVs
from .edge import Edge, Edges
from .face import Face, Faces
from .latticePoint import LatticePoint, LatticePoints
from .pointComponent import PointComponent, PointComponents
from .surfaceCV import SurfaceCV, SurfaceCVs
from .uv import UV, UVs
from .vertex import Vertex, Vertices
from .vertexFace import VertexFace, VertexFaces

__all__ = ['Component', 'Components', 'PointComponent', 'PointComponents', 'Vertex', 'Vertices', 'CV', 'CVs', 'Edge', 'Edges', 'Face', 'Faces', 'UV', 'UVs', 'VertexFace', 'VertexFaces', 'SurfaceCV', 'SurfaceCVs', 'LatticePoint', 'LatticePoints']
