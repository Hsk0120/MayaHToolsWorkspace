# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mesh の頂点フェース(フェースごとの頂点)とコレクション。"""

import bisect
import maya.api.OpenMaya as om2
from ..decorator import _pick_alias
from ..maths.vector import Vector
from ..util import _UNSET, _world_space
from .component import Component, Components, _MultiIndexComponent, _MultiIndexComponents
from .face import Face
from .vertex import Vertex
from typing import Any, Iterable, Iterator
from mlib.nodes.mesh import Mesh
from typing import overload


def _face_vertex_layout(shape: Mesh) -> tuple[list[int], list[int], list[int]]:
    """フェースごとの頂点の並びを照会する。

    Args:
        shape (Mesh): 型を検査済みのメッシュ。

    Returns:
        tuple[list[int], list[int], list[int]]: (各フェースの先頭の平坦な番号, 各フェースの頂点数,
            平坦な番号順の頂点番号)。平坦な番号はフェース番号順・フェース内の頂点順に数える。
    """
    ...


class VertexFace(_MultiIndexComponent, Component):
    """Mesh上の頂点フェース(``vtxFace[頂点][フェース]``)。フェースごとの法線・色を持つ単位。

    保持する :attr:`index` はフェース番号順・フェース内の頂点順に数えた平坦な番号
    (``om2.MFnMesh.getVertices`` の頂点の並び、``MItMeshFaceVertex`` の順)。
    ``(頂点, フェース)`` は :meth:`getMultiIndex` で照会する。
    """
    shape_type: str
    component_type: str
    index_size: int
    def getVertex(self) -> Vertex:
        """この頂点フェースの頂点を取得する。

        Returns:
            Vertex: 頂点。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...
    def getFace(self) -> Face:
        """この頂点フェースのフェースを取得する。

        Returns:
            Face: フェース。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...
    def getNormal(self, worldSpace: bool = ..., *, ws: bool = ...) -> Vector:
        """頂点フェースの法線(``MFnMesh.getFaceVertexNormal``)を、長さ1で取得する。

        ハードエッジ・ロックした法線を反映した、表示に使う法線(``polyNormalPerVertex`` の照会と同じ)。

        Args:
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector: 長さ1の法線。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...
    @classmethod
    def _element_count(cls, shape: Mesh) -> int:
        """頂点フェースの数(全フェースの頂点数の合計)を返す。

        Args:
            shape (Mesh): 型を検査済みのメッシュ。

        Returns:
            int: 頂点フェースの数。
        """
        ...
    @classmethod
    def _multi_indices(cls, shape: Mesh, indices: Iterable[int], command: bool = ...) -> list[tuple[int, int]]:
        """平坦な番号を ``(頂点, フェース)`` へ変換する。

        Args:
            shape (Mesh): 型を検査済みのメッシュ。
            indices (Iterable[int]): 範囲を検証済みの平坦な番号。
            command (bool): cmds用の番号か。頂点フェースでは同じ番号になる。

        Returns:
            list[tuple[int, int]]: 指定順の ``(頂点, フェース)``。
        """
        ...
    @classmethod
    def _flat_indices(cls, shape: Mesh, numbers: Iterable[tuple[int, int]]) -> list[int]:
        """``(頂点, フェース)`` を平坦な番号へ変換する。

        Args:
            shape (Mesh): 型を検査済みのメッシュ。
            numbers (Iterable[tuple[int, int]]): 0以上の ``(頂点, フェース)``。

        Returns:
            list[int]: 指定順の平坦な番号。

        Raises:
            IndexError: フェース番号が範囲外、または頂点がそのフェースに無い場合。
        """
        ...


class VertexFaces(_MultiIndexComponents, Components):
    """同一Meshの頂点フェースの番号列を保持する。

    番号の指定には平坦な番号と ``(頂点, フェース)`` を混ぜられる。名前は範囲へまとめない。
    """
    def __iter__(self) -> Iterator[VertexFace]: ...
    @overload
    def __getitem__(self, index: int) -> VertexFace: ...
    @overload
    def __getitem__(self, index: slice) -> VertexFaces: ...
    component_class: Any
    def getVertex(self) -> list[Vertex]:
        """各要素の :meth:`~mlib.components.vertexFace.VertexFace.getVertex` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getFace(self) -> list[Face]:
        """各要素の :meth:`~mlib.components.vertexFace.VertexFace.getFace` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getNormal(self, worldSpace: bool = ..., *, ws: bool = ...) -> list[Vector]:
        """各要素の :meth:`~mlib.components.vertexFace.VertexFace.getNormal` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getFullName(self) -> list[str]:
        """各要素の :meth:`~mlib.components.component.Component.getFullName` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def asString(self) -> list[str]:
        """各要素の :meth:`~mlib.core.object.Object.asString` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
