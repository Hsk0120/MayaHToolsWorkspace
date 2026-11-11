# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mesh の Face とコレクション。"""

import maya.api.OpenMaya as om2
from ..decorator import _pick_alias
from ..maths.vector import Vector, _vectors_of_points
from ..util import _UNSET, _world_space
from .component import Component, Components
from .vertex import Vertices
from typing import Any, Iterator
from mlib.components.edge import Edges
from mlib.nodes.node import Node
from mlib.nodes.shadingEngine import ShadingEngine
from typing import overload



class Face(Component):
    """Mesh の単一コンポーネント。"""
    shape_type: str
    component_type: str
    count_attribute: str
    def getShadingEngine(self) -> ShadingEngine | None:
        """このインスタンスのフェースに割り当てられたセット。

        Returns:
            ShadingEngine | None: このインスタンスのフェースに割り当てられたセット。
        """
        ...
    def getMaterial(self) -> Node | None:
        """割り当てられたサーフェスシェーダー。

        Returns:
            Node | None: 割り当てられたサーフェスシェーダー。
        """
        ...
    def getVertices(self) -> Vertices:
        """接続する頂点群を取得する。

        Returns:
            Vertices: Maya の接続順の頂点群。
        """
        ...
    def getEdges(self) -> Edges:
        """この面のエッジを取得する。

        :meth:`Faces.getEdges` と同じ規則。

        Returns:
            Edges: 番号の昇順のエッジ(重複なし)。
        """
        ...
    def getCenter(self, worldSpace: bool = ..., *, ws: bool = ...) -> Vector:
        """面の中心(頂点の位置の平均。``MItMeshPolygon.center``)を取得する。

        Args:
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector: 中心の位置(cm)。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...
    def getNormal(self, worldSpace: bool = ..., *, ws: bool = ...) -> Vector:
        """面の法線(``MFnMesh.getPolygonNormal``)を、長さ1で取得する。

        Args:
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector: 長さ1の法線。面の頂点の巡回順で向きが決まる。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...
    def getArea(self, worldSpace: bool = ..., *, ws: bool = ...) -> float:
        """面の面積(``MItMeshPolygon.getArea``)を cm² で取得する。

        Args:
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            float: 面積(cm²)。ワールド空間は親のスケールを含む。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...
_FACE_GET_VERTICES: Any


class Faces(Components):
    """同一 Mesh の Face 群。"""
    def __iter__(self) -> Iterator[Face]: ...
    @overload
    def __getitem__(self, index: int) -> Face: ...
    @overload
    def __getitem__(self, index: slice) -> Faces: ...
    component_class: Any
    def getShadingEngines(self) -> list[ShadingEngine]:
        """対象フェースの割り当てを重複なしで返す。

        Returns:
            list[ShadingEngine]: 対象フェースの割り当てを重複なしで返す。
        """
        ...
    def getMaterials(self) -> list[Node]:
        """対象フェースのマテリアルを重複なしで返す。

        Returns:
            list[Node]: 対象フェースのマテリアルを重複なしで返す。
        """
        ...
    def getVertices(self) -> Vertices:
        """接続する頂点群を取得する。

        Returns:
            Vertices: 保持順に集め、重複を除いた頂点群。
        """
        ...
    def getEdges(self) -> Edges:
        """保持している面のエッジを取得する。選択は変えない。

        ``cmds.polyListComponentConversion(toEdge=True)`` と同じエッジになる。

        Returns:
            Edges: 番号の昇順のエッジ(重複なし)。面が空なら空。

        Raises:
            IndexError: トポロジーの変更で保持番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    def getShadingEngine(self) -> list[ShadingEngine | None]:
        """各要素の :meth:`~mlib.components.face.Face.getShadingEngine` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getMaterial(self) -> list[Node | None]:
        """各要素の :meth:`~mlib.components.face.Face.getMaterial` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getCenter(self, worldSpace: bool = ..., *, ws: bool = ...) -> list[Vector]:
        """各要素の :meth:`~mlib.components.face.Face.getCenter` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getNormal(self, worldSpace: bool = ..., *, ws: bool = ...) -> list[Vector]:
        """各要素の :meth:`~mlib.components.face.Face.getNormal` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getArea(self, worldSpace: bool = ..., *, ws: bool = ...) -> list[float]:
        """各要素の :meth:`~mlib.components.face.Face.getArea` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getFullName(self) -> list[str]:
        """各要素の :meth:`~mlib.components.component.Component.getFullName` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def asString(self) -> list[str]:
        """各要素の :meth:`~mlib.core.object.Object.asString` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
