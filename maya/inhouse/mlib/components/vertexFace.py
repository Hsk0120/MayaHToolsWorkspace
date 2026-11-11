"""Mesh の頂点フェース(フェースごとの頂点)とコレクション。"""

import bisect

import maya.api.OpenMaya as om2

from ..decorator import _pick_alias
from ..maths.vector import Vector
from ..util import _UNSET, _world_space
from .component import Component, Components, _MultiIndexComponent, _MultiIndexComponents
from .face import Face
from .vertex import Vertex


def _face_vertex_layout(shape):
    """フェースごとの頂点の並びを照会する。

    Args:
        shape (Mesh): 型を検査済みのメッシュ。

    Returns:
        tuple[list[int], list[int], list[int]]: (各フェースの先頭の平坦な番号, 各フェースの頂点数,
            平坦な番号順の頂点番号)。平坦な番号はフェース番号順・フェース内の頂点順に数える。
    """
    counts, vertices = shape._geometry_fn().getVertices()
    offsets = []
    total = 0
    for count in counts:
        offsets.append(total)
        total += count
    return offsets, list(counts), list(vertices)


class VertexFace(_MultiIndexComponent, Component):
    """Mesh上の頂点フェース(``vtxFace[頂点][フェース]``)。フェースごとの法線・色を持つ単位。

    保持する :attr:`index` はフェース番号順・フェース内の頂点順に数えた平坦な番号
    (``om2.MFnMesh.getVertices`` の頂点の並び、``MItMeshFaceVertex`` の順)。
    ``(頂点, フェース)`` は :meth:`getMultiIndex` で照会する。
    """

    shape_type = "mesh"
    component_type = "vtxFace"
    index_size = 2

    def getVertex(self):
        """この頂点フェースの頂点を取得する。

        Returns:
            Vertex: 頂点。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        return Vertex(self.shape, self.getMultiIndex()[0])

    def getFace(self):
        """この頂点フェースのフェースを取得する。

        Returns:
            Face: フェース。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        return Face(self.shape, self.getMultiIndex()[1])

    def getNormal(self, worldSpace=_UNSET, *, ws=_UNSET):
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
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        space = om2.MSpace.kWorld if _world_space(worldSpace) else om2.MSpace.kObject
        vertex, face = self.getMultiIndex()
        return Vector(self.shape._geometry_fn().getFaceVertexNormal(face, vertex, space)).normal()

    @classmethod
    def _element_count(cls, shape):
        """頂点フェースの数(全フェースの頂点数の合計)を返す。

        Args:
            shape (Mesh): 型を検査済みのメッシュ。

        Returns:
            int: 頂点フェースの数。
        """
        return shape._geometry_fn().numFaceVertices

    @classmethod
    def _multi_indices(cls, shape, indices, command=False):
        """平坦な番号を ``(頂点, フェース)`` へ変換する。

        Args:
            shape (Mesh): 型を検査済みのメッシュ。
            indices (Iterable[int]): 範囲を検証済みの平坦な番号。
            command (bool): cmds用の番号か。頂点フェースでは同じ番号になる。

        Returns:
            list[tuple[int, int]]: 指定順の ``(頂点, フェース)``。
        """
        offsets, _, vertices = _face_vertex_layout(shape)
        return [(vertices[index], bisect.bisect_right(offsets, index) - 1) for index in indices]

    @classmethod
    def _flat_indices(cls, shape, numbers):
        """``(頂点, フェース)`` を平坦な番号へ変換する。

        Args:
            shape (Mesh): 型を検査済みのメッシュ。
            numbers (Iterable[tuple[int, int]]): 0以上の ``(頂点, フェース)``。

        Returns:
            list[int]: 指定順の平坦な番号。

        Raises:
            IndexError: フェース番号が範囲外、または頂点がそのフェースに無い場合。
        """
        offsets, counts, vertices = _face_vertex_layout(shape)
        result = []
        for vertex, face in numbers:
            if face >= len(offsets):
                raise IndexError(f"Component index out of range: {(vertex, face)}")
            start = offsets[face]
            local = vertices[start:start + counts[face]]
            if vertex not in local:
                raise IndexError(f"Vertex {vertex} is not on face {face}")
            result.append(start + local.index(vertex))
        return result


class VertexFaces(_MultiIndexComponents, Components):
    """同一Meshの頂点フェースの番号列を保持する。

    番号の指定には平坦な番号と ``(頂点, フェース)`` を混ぜられる。名前は範囲へまとめない。
    """

    component_class = VertexFace
