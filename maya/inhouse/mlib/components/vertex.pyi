# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mesh の頂点と頂点コレクション。"""

import maya.api.OpenMaya as om2
from ..decorator import _pick_alias, _require_bool
from ..maths.vector import Vector
from ..util import _UNSET, _world_space
from .pointComponent import PointComponent, PointComponents
from typing import Any, Iterator
from mlib.components.face import Faces
from typing import overload



class Vertex(PointComponent):
    """Mesh 上の単一頂点。番号はゼロ始まり。"""
    shape_type: str
    component_type: str
    count_attribute: str
    def getFaces(self) -> Faces:
        """この頂点に触れている面を取得する。

        :meth:`Vertices.getFaces` と同じ規則。

        Returns:
            Faces: 番号の昇順の面(重複なし)。
        """
        ...
    def getNormal(self, worldSpace: bool = ..., angleWeighted: bool = ..., *, ws: bool = ...) -> Vector:
        """頂点の法線(``MFnMesh.getVertexNormal``。接する面の法線の平均)を、長さ1で取得する。

        Args:
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            angleWeighted (bool): Trueは面の角度で重み付けした平均。既定Falseは単純平均。

        Returns:
            Vector: 長さ1の法線。ロックした法線・ハードエッジは考慮しない(面の法線から計算する)。

        Raises:
            TypeError: worldSpace・angleWeightedがbool以外、またはworldSpaceとwsを同時に指定した場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...


class Vertices(PointComponents):
    """同一 Mesh の頂点群。座標取得・部分列取得・ミラーに対応する。"""
    def __iter__(self) -> Iterator[Vertex]: ...
    @overload
    def __getitem__(self, index: int) -> Vertex: ...
    @overload
    def __getitem__(self, index: slice) -> Vertices: ...
    component_class: Any
    def grow(self) -> Vertices:
        """辺でつながった隣の頂点を加えた頂点群を取得する。選択は変えない。

        Returns:
            Vertices: 保持順の頂点のあとに、加えた頂点を番号の昇順で続けた新しい頂点群。

        Raises:
            IndexError: トポロジーの変更で保持番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    def shrink(self) -> Vertices:
        """保持していない頂点と辺でつながる頂点(縁)を除いた頂点群を取得する。選択は変えない。

        Returns:
            Vertices: 保持順を保った新しい頂点群。全てが縁なら空。

        Raises:
            IndexError: トポロジーの変更で保持番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    def getFaces(self) -> Faces:
        """保持している頂点のどれかに触れている面を取得する。選択は変えない。

        ``cmds.polyListComponentConversion(toFace=True)`` と同じ面になる。

        Returns:
            Faces: 番号の昇順の面(重複なし)。頂点が空なら空。

        Raises:
            IndexError: トポロジーの変更で保持番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    def _neighbor_indices(self) -> dict[int, list[int]]:
        """保持している頂点ごとに、辺でつながった頂点番号を返す。

        Returns:
            dict[int, list[int]]: {頂点番号: 隣の頂点番号}。
        """
        ...
    def getNormal(self, worldSpace: bool = ..., angleWeighted: bool = ..., *, ws: bool = ...) -> list[Vector]:
        """各要素の :meth:`~mlib.components.vertex.Vertex.getNormal` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getFullName(self) -> list[str]:
        """各要素の :meth:`~mlib.components.component.Component.getFullName` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def asString(self) -> list[str]:
        """各要素の :meth:`~mlib.core.object.Object.asString` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
