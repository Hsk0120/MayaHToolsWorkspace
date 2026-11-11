# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mesh の Face とコレクション。"""

import maya.api.OpenMaya as om2
from ..decorator import _pick_alias
from ..maths.vector import Vector, _vectors_of_points
from ..util import _UNSET, _checked_tolerance, _world_space
from .component import Component, Components
from .uv import UVs
from .vertex import Vertices
from typing import Any, Iterator
from mlib.components.edge import Edges
from mlib.components.vertexFace import VertexFaces
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
    def getConnectedFaces(self) -> Faces:
        """このフェースとエッジを共有するフェース(自身を含まない)を取得する(``MItMeshPolygon.getConnectedFaces``)。

        Returns:
            Faces: 番号の昇順のフェース(重複なし)。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...
    def getVertexFaces(self) -> VertexFaces:
        """このフェースの頂点フェースを、フェースの頂点の順に取得する。

        Returns:
            VertexFaces: フェースの頂点の巡回順の頂点フェース。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...
    def getUVs(self) -> UVs:
        """このフェースの、現在のUVセットのUVを取得する。

        Returns:
            UVs: フェースの頂点の巡回順のUV(重複なし)。UVの無いフェースは空。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...
    def isOnBoundary(self) -> bool:
        """メッシュの縁(接する面が1つだけのエッジ)に接するフェースか照会する(``MItMeshPolygon.onBoundary``)。

        Returns:
            bool: 縁のエッジを持てばTrue。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...
    def isPlanar(self) -> bool:
        """フェースの頂点が同一平面上にあるか照会する(``MItMeshPolygon.isPlanar``)。

        Returns:
            bool: 平面ならTrue。三角形は常にTrue。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...
    def isConvex(self) -> bool:
        """凸多角形のフェースか照会する(``MItMeshPolygon.isConvex``)。

        Returns:
            bool: 凸ならTrue。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...
    def isLamina(self) -> bool:
        """ラミナフェース(別のフェースとすべてのエッジを共有する重なったフェース)か照会する
        (``MItMeshPolygon.isLamina``)。

        Returns:
            bool: ラミナフェースならTrue。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...
    def isHoled(self) -> bool:
        """穴を持つフェースか照会する(``MItMeshPolygon.isHoled``)。

        Returns:
            bool: 穴があればTrue。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...
    def isZeroArea(self, tolerance: float = ...) -> bool:
        """面積がほぼゼロ(頂点が1点・一直線上に潰れた)のフェースか照会する。

        Shapeのオブジェクト空間の面積(``MItMeshPolygon.getArea``)で判定する。``MItMeshPolygon.zeroArea`` は
        頂点を1点へ集めたフェースでもFalseを返すことがあるため使わない。

        Args:
            tolerance (float): 面積の許容誤差(cm²)。0以上。

        Returns:
            bool: 面積が tolerance 以下ならTrue。

        Raises:
            TypeError: toleranceが数値でない場合。
            ValueError: toleranceが負・有限でない場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...
    def getTriangleCount(self) -> int:
        """フェースを三角形に分割したときの三角形の数を取得する(``MItMeshPolygon.numTriangles``)。

        Returns:
            int: 三角形の数(``cmds.polyEvaluate(triangle=True)`` のフェース単位の値)。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        ...
    def _iterator(self) -> om2.MItMeshPolygon:
        """番号を検証し、このフェースへ移した ``om2.MItMeshPolygon`` を返す。

        Returns:
            om2.MItMeshPolygon: このフェースを指す反復子。
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
    def getConnectedFaces(self) -> list[Faces]:
        """各要素の :meth:`~mlib.components.face.Face.getConnectedFaces` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getVertexFaces(self) -> list[VertexFaces]:
        """各要素の :meth:`~mlib.components.face.Face.getVertexFaces` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getUVs(self) -> list[UVs]:
        """各要素の :meth:`~mlib.components.face.Face.getUVs` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def isOnBoundary(self) -> list[bool]:
        """各要素の :meth:`~mlib.components.face.Face.isOnBoundary` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def isPlanar(self) -> list[bool]:
        """各要素の :meth:`~mlib.components.face.Face.isPlanar` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def isConvex(self) -> list[bool]:
        """各要素の :meth:`~mlib.components.face.Face.isConvex` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def isLamina(self) -> list[bool]:
        """各要素の :meth:`~mlib.components.face.Face.isLamina` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def isHoled(self) -> list[bool]:
        """各要素の :meth:`~mlib.components.face.Face.isHoled` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def isZeroArea(self, tolerance: float = ...) -> list[bool]:
        """各要素の :meth:`~mlib.components.face.Face.isZeroArea` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getTriangleCount(self) -> list[int]:
        """各要素の :meth:`~mlib.components.face.Face.getTriangleCount` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def getFullName(self) -> list[str]:
        """各要素の :meth:`~mlib.components.component.Component.getFullName` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
    def asString(self) -> list[str]:
        """各要素の :meth:`~mlib.core.object.Object.asString` を同じ引数で保持順に呼び、戻り値を保持順のリストで返す。"""
        ...
