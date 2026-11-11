# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya のメッシュシェイプを扱う。"""

import math
from collections import Counter, defaultdict
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace
from ..components.edge import Edge, Edges
from ..components.face import Face, Faces
from ..components.pointComponent import _mirror_plan, _write_points
from ..components.uv import UV, UVs
from ..components.vertex import Vertex, Vertices
from ..components.vertexFace import VertexFaces
from ..core import geometryEdit as geometry_edit
from ..core.fastWrite import require_writable
from ..decorator import _edit_context, _pick_alias, _require_bool, undoChunk, undoTransaction
from ..maths.vector import Vector, _vector_of, _vectors_of_points
from ..util import _PointGrid, _UNSET, _checked_tolerance, _finite_vector, _mirror_axis, _world_space
from .shape import Shape
from typing import Any, Iterable, Sequence
from mlib.components.component import Component
from mlib.components.component import Components
from mlib.nodes.node import Node
from mlib.nodes.shadingEngine import ShadingEngine

_NO_DISTANCE_LIMIT: float
_INTERSECT_MERGE: float
_UNSET_COLOR_VALUES: tuple
_UNSET_COLOR: Any


class Mesh(Shape):
    """Maya mesh shape ノードのラッパー。"""
    def reorderVertices(self, reference: Mesh | Node | str, uvSet: str = ..., tolerance: float = ..., *, fast: bool = ..., match: str = ..., worldSpace: bool = ..., ws: bool = ...) -> Mesh:
        """UVまたは頂点位置の一意な対応で、対象の頂点番号を基準メッシュへ合わせる。

        頂点位置・面順/向き・UV・法線・面マテリアルは保持する。エッジ番号は変わり得る。
        スキン等の番号依存データは移し替えず、既存Component参照は処理後に取り直す。
        UVシームは各頂点の面頂点UV群で照合し、曖昧な対応は変更前に拒否する。

        Args:
            reference (Mesh | Node | str): 基準Meshまたは単一メッシュTransform。
            uvSet (str): UV照合のセット名。位置照合では使わない。
            tolerance (float): 非負有限値。UVは成分差、位置はcm距離の許容誤差。
            fast (bool): TrueはUndoなしで再構築し、非ゼロtweakを現在位置へベイクする。
                既定FalseはUndo有効が必須で、非ゼロtweakは未対応。
            match (str): 既定uv、またはposition。
            worldSpace (bool): 位置照合でTrueはワールド空間、Falseは各Shapeのオブジェクト空間。UV照合では使わない。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Mesh: 自身。番号対応が既に同一なら再構築せず返し、再構築用の制限検査にも進まない。

        Raises:
            TypeError: 入力型・fast/worldSpaceが不正な場合、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 対応が曖昧/不完全、トポロジー/面の向きが一致しない、または再構築時に
                入出力履歴・インスタンス・参照・色セット・クリース等がある場合。
            RuntimeError: 再構築時にロック、または通常処理でUndoが無効の場合。
            NotImplementedError: 通常経路で頂点のtweakがある法線の並べ替えの場合。
        """
        ...
    def getVertex(self, index: int) -> Vertex:
        """頂点番号から単体ラッパーを取得する。

        Args:
            index (int): ゼロ始まりの頂点番号。

        Returns:
            Vertex: シーン上の頂点を参照するラッパー。

        Raises:
            IndexError: 頂点番号が範囲外の場合。
        """
        ...
    def getVertices(self, indices: Iterable[int] | None = ...) -> Vertices:
        """指定した頂点群を取得する。

        Args:
            indices (Iterable[int] | None): 頂点番号。None は現在の全頂点。

        Returns:
            Vertices: 番号順を維持し、重複を除いたコレクション。
        """
        ...
    def getVertexFaces(self, indices: Iterable[int | tuple[int, int]] | None = ...) -> VertexFaces:
        """指定した頂点フェース(``vtxFace[v][f]``)を取得する。

        Args:
            indices (Iterable[int | tuple[int, int]] | None): 平坦な番号か ``(頂点番号, フェース番号)``。
                None は現在の全頂点フェース。

        Returns:
            VertexFaces: 番号順を維持し、重複を除いたコレクション。

        Raises:
            IndexError: 頂点がフェースに含まれない、または番号が範囲外の場合。
        """
        ...
    def getShadingEngines(self) -> list[ShadingEngine]:
        """このDAGインスタンスのフェースへ割り当てられたShadingEngineを取得する。

        Returns:
            list[ShadingEngine]: 使用中のセット。未割り当ては除外する。
        """
        ...
    def getFaceShadingEngines(self) -> list[ShadingEngine | None]:
        """面番号順の割り当てを取得する。

        Returns:
            list[ShadingEngine | None]: 全フェースの割り当て。未割り当てはNone。
        """
        ...
    def mfn(self) -> om2.MFnMesh | om2.MFnDagNode:
        """この mesh で最も具体的な om2 function set を、呼び出すたびに新しく作って返す。

        形状データを持つ場合は ``om2.MFnMesh``。``mlib.createNode("mesh")`` 直後のように形状データを
        持たない空のシェイプは ``om2.MFnMesh`` が使えない(Maya 2027 では作成時に ValueError、
        版により作成後の照会で RuntimeError)ため、``om2.MFnDagNode`` を返す。DagNode 共通の照会
        (中間オブジェクト判定・親の列挙等)は空のシェイプでも使える。

        Returns:
            om2.MFnMesh | om2.MFnDagNode: この mesh の function set。空のシェイプでは MFnDagNode。

        Raises:
            RuntimeError: 保持する DAG パスが無効な場合。
        """
        ...
    def getNumVertices(self) -> int:
        """頂点数を取得する。

        Returns:
            int: mesh の頂点数。
        """
        ...
    def getNumPolygons(self) -> int:
        """ポリゴン数を取得する。

        Returns:
            int: mesh のポリゴン数。
        """
        ...
    def getNumEdges(self) -> int:
        """エッジ数を取得する。

        Returns:
            int: メッシュのエッジ数。
        """
        ...
    def getPoints(self, worldSpace: bool = ..., *, ws: bool = ...) -> list[Vector]:
        """全頂点の位置を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[Vector]: 頂点番号順の位置(:class:`~mlib.maths.vector.Vector`)。距離は Maya API の
                内部単位(cm)。そのまま :meth:`setPoints` へ渡せる。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
        """
        ...
    def setPoints(self, points: Iterable[Sequence[float] | om2.MPoint | om2.MVector], worldSpace: bool = ..., *, fast: bool = ..., ws: bool = ...) -> Mesh:
        """全頂点の位置を一度に書き込み、自身を返す。

        :meth:`getPoints` と同じ並び・単位(内部単位cm)の点列を受け付け、通常は ``cmds.xform`` で
        書き込んで1回のUndoにまとめる。``fast=True`` は ``MFnMesh.setPoints`` で全頂点を1回で書き込み、
        Undoに記録しない。頂点数・トポロジー・UVは変更しない。
        :meth:`NurbsCurve.setCvPositions <mlib.nodes.nurbsCurve.NurbsCurve.setCvPositions>` と同じ形の入口。

        Args:
            points (Iterable[Sequence[float] | om2.MPoint | om2.MVector]): 頂点番号順の位置。
                :meth:`getPoints` の結果(list[Vector])・3個の数値のtupleの列・``om2.MPointArray`` を
                そのまま受け付ける。各点は3個の有限な数値。MPointはwで割らずにXYZを使う。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、点の型・成分が不正な場合、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 点の数が頂点数と合わない、または成分が有限でない場合。
            RuntimeError: 形状データが無い・無効なシェイプ、またはロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力(コンストラクションヒストリ)がある場合。

        Note:
            現在と同じ位置の頂点は書き込まない(``getPoints()`` の結果を一部だけ変えて戻す使い方では、
            変えた頂点だけを書き込む)。書き込む頂点ごとに ``cmds.xform`` を呼ぶため(``setCvPositions``
            と同じ)、多数の頂点を動かす場合は頂点数に比例して時間がかかる(目安は1頂点あたり約1ms)。
            ``fast=True`` は全頂点をまとめて書くため、頂点数が多いほど差が大きい。
        """
        ...
    def mirror(self, axis: str | int = ..., worldSpace: bool = ..., pivot: Iterable[float] = ..., indices: Iterable[int] | None = ..., *, fast: bool = ..., ws: bool = ...) -> Mesh:
        """頂点座標を、指定空間の中心pivotに対して反転する(``2 * pivot - 現在座標``)。

        Transform・トポロジー(頂点番号・面の接続と頂点順)は変更しない。共有Shapeの全インスタンスへ影響する。
        複製・結合・片側からの対称化・法線の反転は行わない(奇数軸の反転で面の向きが裏返る)。
        入力をすべて検証してから書き込み、通常は ``cmds.xform`` を頂点ごとに呼んで1回のUndoにまとめる
        (目安は1頂点あたり約0.2ms)。``fast=True`` は ``MFnMesh.setPoints`` で全頂点を1回で書く。
        :meth:`Vertices.mirror <mlib.components.pointComponent.PointComponents.mirror>` と同じ処理。

        Args:
            axis (str | int): 反転する軸 ``"x"``・``"y"``・``"z"``、またはミラー面 ``"YZ"``・``"XZ"``・``"XY"``
                (x⇔YZ、y⇔XZ、z⇔XY。文字の順序・大文字小文字は問わない)、または0/1/2。
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            pivot (Iterable[float]): 指定空間の反転中心XYZ(cm)。既定は原点で、Transformのピボットとは独立。
            indices (Iterable[int] | None): 頂点番号。Noneは全頂点、空列は変更なし。重複は1回だけ処理する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、axisが文字列・int以外、番号の型が不正な場合、またはworldSpaceとwsを同時に指定した場合。
            ValueError: axis・pivotが不正、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: 頂点番号が負または範囲外の場合。
            RuntimeError: 形状データが無い・無効なシェイプ、またはロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力(コンストラクションヒストリ)がある場合。
        """
        ...
    def getVertexNormals(self, worldSpace: bool = ..., angleWeighted: bool = ..., *, ws: bool = ...) -> list[Vector]:
        """各頂点に接する面頂点法線を平均し、頂点ごとの法線を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            angleWeighted (bool): True の場合は隣接面の角度でウェイト付けした法線を取得する。

        Returns:
            list[Vector]: 頂点番号順の平均法線。angleWeighted=False では
                角度によるウェイト付けを行わない。MFnMesh.getVertexNormals() を使用する。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
        """
        ...
    def getVertexAdjacency(self, worldSpace: bool = ..., *, ws: bool = ...) -> list[list[tuple[int, float]]]:
        """頂点IDごとの隣接頂点とエッジ長を照会する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[list[tuple[int, float]]]: 頂点ID順の隣接リスト。
            各要素は隣接頂点IDとcm単位の距離で、エッジID順に格納する。
            孤立頂点は空リスト、重複エッジは別々に保持する。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
        """
        ...
    def getShells(self) -> list[Vertices]:
        """辺でつながった頂点のまとまり(シェル)を取得する。

        Returns:
            list[Vertices]: シェルごとの頂点(番号の昇順)。シェルは最小の頂点番号の順に並ぶ。
                孤立した頂点は1頂点のシェルになる。
        """
        ...
    def getUVShells(self, uvSet: str | None = ...) -> list[list[int]]:
        """UVでつながったUVのまとまり(UVシェル)を取得する(``MFnMesh.getUvShellsIds``)。

        形状のシェル(:meth:`getShells`)と違い、UVの切れ目で分かれる。

        Args:
            uvSet (str | None): UVセットの名前。Noneは現在のUVセット。

        Returns:
            list[list[int]]: シェルごとのUV番号(昇順)。シェルは最小のUV番号の順に並ぶ。UVが無ければ空。
                番号は指定したUVセットのもの(:class:`~mlib.components.uv.UVs` は現在のUVセットを参照するため、
                別のUVセットの番号は番号のlistで返す)。

        Raises:
            TypeError: uvSetが文字列・None以外の場合。
            ValueError: 名前が空、そのUVセットが無い、またはメッシュにUVセットが無い場合。
        """
        ...
    def getTriangles(self) -> list[tuple[int, int, int]]:
        """Maya の三角形分割で、ポリゴンを三角形に分けた頂点の組を取得する。

        Returns:
            list[tuple[int, int, int]]: 三角形ごとの頂点番号。フェース番号の順で、各フェース内は Maya の分割順。
        """
        ...
    def getMirrorVertexMap(self, axis: str | int = ..., tolerance: float = ..., worldSpace: bool = ..., *, ws: bool = ...) -> dict[int, int]:
        """頂点ごとに、位置を軸で反転した反対側の頂点を取得する。

        反転した位置から ``tolerance`` 以内で最も近い頂点を反対側とする。トポロジーは見ない。

        Args:
            axis (str | int): 反転する軸 ``"x"``・``"y"``・``"z"``、ミラー面 ``"YZ"``・``"XZ"``・``"XY"``、または0/1/2。既定 ``"x"``。
            tolerance (float): 反転した位置と頂点の距離の許容量(cm)。正の有限値。既定0.01。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            dict[int, int]: {頂点番号: 反対側の頂点番号}。反対側が見つからない頂点は含めない。
                軸の上の頂点は自身へ対応する(キーと値が同じ)。

        Raises:
            TypeError: axisが文字列・int以外、toleranceが実数以外、worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            ValueError: axisが不正、またはtoleranceが正の有限値でない場合。
        """
        ...
    def getClosestVertex(self, point: Sequence[float] | om2.MPoint | om2.MVector, worldSpace: bool = ..., *, ws: bool = ...) -> Vertex:
        """指定した位置に最も近い頂点を取得する。

        頂点の位置だけで比べる(面の上の最近点ではない)。多数の点を調べるなら :meth:`getClosestVertices` を使う。

        Args:
            point (Sequence[float] | om2.MPoint | om2.MVector): 位置(cm)。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vertex: 最も近い頂点。

        Raises:
            TypeError: 点の型・成分が不正、worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 成分の数が3でない・有限でない、またはメッシュに頂点が無い場合。
            RuntimeError: 形状データを持たない空のシェイプ(``mlib.createNode("mesh")`` の直後等)の場合。
        """
        ...
    def getClosestVertices(self, points: Iterable[Sequence[float] | om2.MPoint | om2.MVector], worldSpace: bool = ..., *, ws: bool = ...) -> list[int]:
        """点ごとに、最も近い頂点の番号を取得する。

        頂点の位置に一様な格子を作って探す(面の上の最近点ではない)。

        Args:
            points (Iterable[Sequence[float] | om2.MPoint | om2.MVector]): 位置(cm)の並び。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[int]: 点の順の、最も近い頂点の番号。

        Raises:
            TypeError: 点列・点の型・成分が不正、worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 成分の数が3でない・有限でない、またはメッシュに頂点が無い場合。
            RuntimeError: 形状データを持たない空のシェイプ(``mlib.createNode("mesh")`` の直後等)の場合。
        """
        ...
    def getEdge(self, index: int) -> Edge:
        """番号から Edge を取得する。

        Args:
            index (int): ゼロ始まりの番号。

        Returns:
            Edge: シーンを参照する単体ラッパー。
        """
        ...
    def getEdges(self, indices: Iterable[int] | None = ...) -> Edges:
        """指定した Edge 群を取得する。

        Args:
            indices (Iterable[int] | None): 番号列。None は現在の全要素。

        Returns:
            Edges: 重複を除いたコレクション。
        """
        ...
    def getFace(self, index: int) -> Face:
        """番号から Face を取得する。

        Args:
            index (int): ゼロ始まりの番号。

        Returns:
            Face: シーンを参照する単体ラッパー。
        """
        ...
    def getFaces(self, indices: Iterable[int] | None = ...) -> Faces:
        """指定した Face 群を取得する。

        Args:
            indices (Iterable[int] | None): 番号列。None は現在の全要素。

        Returns:
            Faces: 重複を除いたコレクション。
        """
        ...
    def getUV(self, index: int) -> UV:
        """番号から UV を取得する。

        Args:
            index (int): ゼロ始まりの番号。

        Returns:
            UV: シーンを参照する単体ラッパー。
        """
        ...
    def getUVs(self, indices: Iterable[int] | None = ...) -> UVs:
        """指定した UV 群を取得する。

        Args:
            indices (Iterable[int] | None): 番号列。None は現在の全要素。

        Returns:
            UVs: 重複を除いたコレクション。
        """
        ...
    def getNumUVs(self) -> int:
        """現在の UV セットの要素数。

        Returns:
            int: UV 数。
        """
        ...
    def getClosestPoint(self, point: Sequence[float] | om2.MPoint | om2.MVector, worldSpace: bool = ..., *, ws: bool = ...) -> tuple[Vector, int]:
        """指定した位置に最も近い、メッシュの面の上の点を取得する。

        ``MFnMesh.getClosestPoint`` を使う。頂点だけを比べる :meth:`getClosestVertex` と違い、
        面の内部・エッジの上の点も返す。

        Args:
            point (Sequence[float] | om2.MPoint | om2.MVector): 位置(cm)。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。入力と戻り値の空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            tuple[Vector, int]: 面の上の最も近い点(cm)と、その点を含む面の番号。

        Raises:
            TypeError: 点の型・成分が不正、worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 成分の数が3でない・有限でない、またはメッシュに面が無い場合。
            RuntimeError: 形状データを持たない空のシェイプ(``mlib.createNode("mesh")`` の直後等)の場合。
        """
        ...
    def getClosestNormal(self, point: Sequence[float] | om2.MPoint | om2.MVector, worldSpace: bool = ..., *, ws: bool = ...) -> Vector:
        """指定した位置に最も近い面の上の点で、補間した法線を取得する。

        最も近い点を含む三角形の3つの面頂点法線(ハード/ソフトエッジを反映した、表示に使う法線)を、
        その点の重心座標で補間して長さ1にする。``MFnMesh.getClosestNormal`` が返す面法線ではない。
        ハードエッジだけのメッシュ(立方体等)では面法線と同じ向きになる。

        Args:
            point (Sequence[float] | om2.MPoint | om2.MVector): 位置(cm)。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。入力と戻り値の空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector: 長さ1の法線。ワールド空間ではオブジェクト空間の法線をマトリクスの逆転置で変換する。

        Raises:
            TypeError: 点の型・成分が不正、worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 成分の数が3でない・有限でない、またはメッシュに面が無い場合。
            RuntimeError: 形状データを持たない空のシェイプ(``mlib.createNode("mesh")`` の直後等)の場合。

        Note:
            最も近い点はオブジェクト空間で探す(``MMeshIntersector``)。非一様なスケールを持つ
            メッシュのワールド空間では、:meth:`getClosestPoint` と違う面の点になることがある。
        """
        ...
    def intersect(self, origin: Sequence[float] | om2.MPoint | om2.MVector, direction: Sequence[float] | om2.MVector, *, maxDistance: float | None = ..., worldSpace: bool = ..., ws: bool = ...) -> list[tuple[Vector, int, float]]:
        """半直線とメッシュの交点を、近い順に取得する。

        ``MFnMesh.allIntersections`` を使い、``origin`` から ``direction`` の向きへだけ調べる(逆向きは調べない)。
        面の向き(法線)に関係なく、表からでも裏からでも当たる(両面)。

        Args:
            origin (Sequence[float] | om2.MPoint | om2.MVector): 半直線の始点(cm)。
            direction (Sequence[float] | om2.MVector): 向き。長さは問わない(内部で長さ1にする)。
            maxDistance (float | None): 始点からの最大距離(cm)。正の有限値。Noneは制限なし。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。入力と戻り値の空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[tuple[Vector, int, float]]: (交点、面の番号、始点からの距離cm)の距離の昇順。
                当たらなければ空。同じ面を三角形の境目で2回当てた結果は1つにまとめる。
                面と面の境目のエッジに当たった場合は、それぞれの面を別の要素で返す。

        Raises:
            TypeError: 点・向きの型・成分が不正、maxDistanceが数値・None以外、worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 成分が有限でない、directionの長さが0、またはmaxDistanceが正の有限値でない場合。

        Note:
            Mayaの交差判定は単精度(float)で計算するため、交点と距離は1e-5程度の誤差を含む。
        """
        ...
    def getUVAtPoint(self, point: Sequence[float] | om2.MPoint | om2.MVector, uvSet: str | None = ..., worldSpace: bool = ..., *, ws: bool = ...) -> tuple[float, float]:
        """指定した位置に最も近い面の上の点の UV を取得する。

        位置が面の上に無ければ、最も近い面の上の点の UV になる。最も近い点を含む三角形の3つの面頂点UVを、
        その点の重心座標で補間する(``closestPointOnMesh`` ノードの ``parameterU/V`` と同じ値)。
        ``MFnMesh.getUVAtPoint`` は面の境目の近くで隣の面のUVを返すことがあるため使わない。

        Args:
            point (Sequence[float] | om2.MPoint | om2.MVector): 位置(cm)。
            uvSet (str | None): UVセットの名前。Noneは現在のUVセット。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            tuple[float, float]: (u, v)。

        Raises:
            TypeError: 点の型・成分が不正、uvSetが文字列・None以外、worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            ValueError: 成分が有限でない、UVセットが無い、またはメッシュに面が無い場合。
            RuntimeError: 最も近い面にUVが割り当てられていない場合。

        Note:
            最も近い点は :meth:`getClosestNormal` と同じくオブジェクト空間で探す。
        """
        ...
    def getPointAtUV(self, u: float, v: float, uvSet: str | None = ..., worldSpace: bool = ..., *, ws: bool = ...) -> Vector | None:
        """UV の位置に対応する、面の上の点を取得する。

        面番号の順に、UVの範囲に (u, v) を含む面を ``MFnMesh.getPointAtUV`` で調べ、最初に見つかった面の点を返す。
        UVが重なっていて複数の面に当たる場合も、番号の最も小さい面の点になる。

        Args:
            u (float): U座標。
            v (float): V座標。
            uvSet (str | None): UVセットの名前。Noneは現在のUVセット。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector | None: 面の上の点(cm)。どの面のUVにも含まれない位置ならNone。

        Raises:
            TypeError: u・vが数値以外、uvSetが文字列・None以外、worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            ValueError: u・vが有限でない、またはUVセットが無い場合。
        """
        ...
    def getVertexColors(self, colorSet: str | None = ...) -> list[tuple[float, float, float, float] | None]:
        """頂点ごとの色を取得する。

        ``MFnMesh.getVertexColors`` を使う。面ごとに違う色を持つ頂点(面頂点の色)は、その平均になる。

        Args:
            colorSet (str | None): カラーセットの名前。Noneは現在のカラーセット。

        Returns:
            list[tuple[float, float, float, float] | None]: 頂点番号順の(R, G, B, A)。
                色の無い頂点はNone。Noneを指定してカラーセットが1つも無い場合は全てNone。

        Raises:
            TypeError: colorSetが文字列・None以外の場合。
            ValueError: 指定した名前のカラーセットが無い場合。
        """
        ...
    def setVertexColors(self, colors: Iterable[Sequence[float] | om2.MColor], vertices: Component | Components | Iterable[int] | None = ..., *, colorSet: str | None = ..., fast: bool = ...) -> Mesh:
        """頂点ごとの色を設定し、自身を返す。

        通常は ``cmds.polyColorPerVertex`` で、同じ色の頂点をまとめて1回ずつ書き、1回のUndoにまとめる。
        色の数が多いと時間がかかる(目安は1色あたり約1ms)。``fast=True`` は ``MFnMesh.setVertexColors`` で
        1回で書き、Undoに記録しない。頂点のすべての面頂点の色を同じ色にする。

        Args:
            colors (Iterable[Sequence[float] | om2.MColor]): 頂点の色。各色は (R, G, B) または (R, G, B, A) の
                有限な数値(Aを省略すると1.0)。vertices と同じ数(None なら頂点数)。
            vertices (Component | Components | Iterable[int] | None): 書き込む頂点の番号。None は全頂点。
                重複は不可。指定した順に colors と対応する。
            colorSet (str | None): カラーセットの名前。Noneは現在のカラーセット(無ければMayaが
                ``colorSet1`` を作る)。名前を指定した場合は既にある必要があり、現在のカラーセットは変えない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: fastがbool以外、colorSetが文字列・None以外、または色・頂点の型が不正な場合。
            ValueError: 色の数が頂点の数と合わない、成分の数が3・4以外か有限でない、頂点が重複している、
                別のメッシュの頂点を渡した、またはカラーセットが無い場合。
            IndexError: 頂点番号が範囲外の場合。
            RuntimeError: シェイプのロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力(コンストラクションヒストリ)がある場合。

        Note:
            通常経路は、コンストラクションヒストリのあるメッシュでは ``polyColorPerVertex`` ノードを履歴へ足す。
        """
        ...
    def getUVSetNames(self) -> list[str]:
        """UVセットの名前を取得する。

        Returns:
            list[str]: Mayaの並び順のUVセットの名前。先頭が既定のUVセット(``uvSet[0]``)。
        """
        ...
    def getCurrentUVSet(self) -> str:
        """現在のUVセットの名前を取得する。

        Returns:
            str: 現在のUVセットの名前。
        """
        ...
    def setCurrentUVSet(self, name: str) -> Mesh:
        """現在のUVセットを設定し、自身を返す。

        ``cmds.polyUVSet(currentUVSet=True)`` で設定し、1回のUndoで戻る。

        Args:
            name (str): 既にあるUVセットの名前。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: nameが空、またはそのUVセットが無い場合。
        """
        ...
    def createUVSet(self, name: str) -> Mesh:
        """空のUVセットを作り、自身を返す。

        ``cmds.polyUVSet(create=True)`` で作り、1回のUndoで戻る。現在のUVセットは変えない。
        コンストラクションヒストリのあるメッシュでは ``createUVSet`` ノードを履歴へ足す。

        Args:
            name (str): 新しいUVセットの名前。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: nameが空、または同じ名前のUVセットが既にある場合。
        """
        ...
    def copyUVSet(self, source: str, target: str) -> Mesh:
        """UVセットを新しい名前へ複製し、自身を返す。

        ``cmds.polyUVSet(copy=True)`` で複製し、1回のUndoで戻る。現在のUVセットは変えない。

        Args:
            source (str): 複製元のUVセットの名前。
            target (str): 新しいUVセットの名前。既にある名前は不可(上書きしない)。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: source・targetが文字列以外の場合。
            ValueError: 名前が空、sourceが無い、またはtargetが既にある場合。
        """
        ...
    def renameUVSet(self, name: str, newName: str) -> Mesh:
        """UVセットの名前を変え、自身を返す。

        ``cmds.polyUVSet(rename=True)`` で変え、1回のUndoで戻る。現在のUVセットの名前を変えた場合は、
        新しい名前が現在のUVセットになる。

        Args:
            name (str): 既にあるUVセットの名前。
            newName (str): 新しい名前。既にある名前は不可。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: name・newNameが文字列以外の場合。
            ValueError: 名前が空、nameが無い、またはnewNameが既にある場合。
        """
        ...
    def deleteUVSet(self, name: str) -> Mesh:
        """UVセットを削除し、自身を返す。

        ``cmds.polyUVSet(delete=True)`` で削除し、1回のUndoで戻る。現在のUVセットを削除すると、
        Mayaは既定のUVセット(:meth:`getUVSetNames` の先頭)を現在のUVセットにする。

        Args:
            name (str): 既にあるUVセットの名前。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: nameが空、そのUVセットが無い、または既定のUVセット(``uvSet[0]``。通常 ``map1``)の場合。
                Mayaは既定のUVセットを削除できない(名前が ``map1`` でなくても同じ)。
        """
        ...
    def getColorSetNames(self) -> list[str]:
        """カラーセットの名前を取得する。

        Returns:
            list[str]: Mayaの並び順のカラーセットの名前。無ければ空。
        """
        ...
    def getCurrentColorSet(self) -> str | None:
        """現在のカラーセットの名前を取得する。

        Returns:
            str | None: 現在のカラーセットの名前。カラーセットが無ければNone。
        """
        ...
    def setCurrentColorSet(self, name: str) -> Mesh:
        """現在のカラーセットを設定し、自身を返す。

        ``cmds.polyColorSet(currentColorSet=True)`` で設定し、1回のUndoで戻る。

        Args:
            name (str): 既にあるカラーセットの名前。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: nameが空、またはそのカラーセットが無い場合。
        """
        ...
    def createColorSet(self, name: str) -> Mesh:
        """空のRGBAのカラーセットを作り、自身を返す。

        ``cmds.polyColorSet(create=True)`` で作り、1回のUndoで戻る。:meth:`createUVSet` と違い、
        Mayaの動作どおり作ったカラーセットが現在のカラーセットになる。
        コンストラクションヒストリのあるメッシュでは ``createColorSet`` ノードを履歴へ足す。

        Args:
            name (str): 新しいカラーセットの名前。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: nameが空、または同じ名前のカラーセットが既にある場合。
        """
        ...
    def copyColorSet(self, source: str, target: str) -> Mesh:
        """カラーセットを新しい名前へ複製し、自身を返す。

        ``cmds.polyColorSet(copy=True)`` で複製し、1回のUndoで戻る。現在のカラーセットは変えない。

        Args:
            source (str): 複製元のカラーセットの名前。
            target (str): 新しいカラーセットの名前。既にある名前は不可(上書きしない)。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: source・targetが文字列以外の場合。
            ValueError: 名前が空、sourceが無い、またはtargetが既にある場合。
        """
        ...
    def renameColorSet(self, name: str, newName: str) -> Mesh:
        """カラーセットの名前を変え、自身を返す。

        ``cmds.polyColorSet(rename=True)`` で変え、1回のUndoで戻る。現在のカラーセットの名前を変えた場合は、
        新しい名前が現在のカラーセットになる。

        Args:
            name (str): 既にあるカラーセットの名前。
            newName (str): 新しい名前。既にある名前は不可。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: name・newNameが文字列以外の場合。
            ValueError: 名前が空、nameが無い、またはnewNameが既にある場合。
        """
        ...
    def deleteColorSet(self, name: str) -> Mesh:
        """カラーセットを削除し、自身を返す。

        ``cmds.polyColorSet(delete=True)`` で削除し、1回のUndoで戻る。現在のカラーセットを削除すると、
        Mayaは残りの先頭のカラーセットを現在のカラーセットにする(残りが無ければ現在のカラーセットは無くなる)。

        Args:
            name (str): 既にあるカラーセットの名前。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: nameが空、またはそのカラーセットが無い場合。
        """
        ...
    def getBorderEdges(self) -> Edges:
        """メッシュの縁(接する面が1つだけ)のエッジを取得する。

        3つ以上の面が接する非多様体のエッジと、面の無いエッジは含めない。

        Returns:
            Edges: 番号の昇順のエッジ。縁が無ければ空。
        """
        ...
    def getBorderVertices(self) -> Vertices:
        """メッシュの縁のエッジ(:meth:`getBorderEdges`)の端の頂点を取得する。

        Returns:
            Vertices: 番号の昇順の頂点。縁が無ければ空。
        """
        ...
    def _raw_points(self, worldSpace: bool) -> om2.MPointArray:
        """全頂点の位置を om2 の点列で返す(Vector へ変換しない照会用)。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。

        Returns:
            om2.MPointArray: 頂点番号順の位置。
        """
        ...
    @staticmethod
    def _position_vertex_mapping(source, target, tolerance, world_space):
        """指定空間で許容距離内の一意な頂点対応を空間セルから求める。"""
        ...
    @staticmethod
    def _uv_vertex_mapping(source, target, uv_set, tolerance):
        """面頂点UV群が一意に一致する旧対象番号→基準番号を求める。"""
        ...
    @staticmethod
    def _face_cycles(counts, connects):
        """面の開始頂点に依存せず、面の向きと頂点接続を比較する。"""
        ...
    def _require_reorder_supported(self, fn, *, fast=...):
        """番号依存の外部接続や未対応のメッシュデータを変更前に拒否する。"""
        ...
    @staticmethod
    def _reordered_mesh_data(fn, counts, connects, remapped, mapping):
        """シーン外のメッシュデータを作り、面順・UVと法線を移す。"""
        ...
    @staticmethod
    def _copy_reorder_details(fn, rebuilt, counts, remapped, mapping):
        """一時メッシュへ全UVセット・エッジの硬軟・固定法線を移す。"""
        ...
    @staticmethod
    def _resolve_query_point(point: Sequence[float] | om2.MPoint | om2.MVector, name: str = ...) -> om2.MPoint:
        """照会に使う位置を検証し、``om2.MPoint`` にする。

        Args:
            point (Sequence[float] | om2.MPoint | om2.MVector): 位置(cm)。
            name (str): 例外メッセージに使う引数名。

        Returns:
            om2.MPoint: XYZを写した点(wは1)。

        Raises:
            TypeError: 点の型・成分が不正な場合。
            ValueError: 成分の数が3でない、または有限でない場合。
        """
        ...
    def _require_faces(self) -> om2.MFnMesh:
        """面のあるメッシュの ``om2.MFnMesh`` を返す。

        Returns:
            om2.MFnMesh: この mesh の function set。

        Raises:
            ValueError: メッシュに面が無い場合。
        """
        ...
    def _closest_triangle(self, point: om2.MPoint, worldSpace: bool) -> tuple[om2.MFnMesh, int, list[tuple[int, float]]]:
        """最も近い面の上の点を含む三角形と、その点の重心座標を返す。

        ``MMeshIntersector`` でオブジェクト空間の最近点を探す。

        Args:
            point (om2.MPoint): 位置(cm)。
            worldSpace (bool): Trueは point をワールド空間とみなし、オブジェクト空間へ変換して探す。

        Returns:
            tuple[om2.MFnMesh, int, list[tuple[int, float]]]: function set・面の番号・三角形の
                (頂点番号, 重心座標のウェイト)の3組。

        Raises:
            ValueError: メッシュに面が無い場合。
        """
        ...
    def _resolve_uv_set(self, uvSet: str | None) -> str:
        """UVセットの指定を、実在する名前にする。

        Args:
            uvSet (str | None): UVセットの名前。Noneは現在のUVセット。

        Returns:
            str: UVセットの名前。

        Raises:
            TypeError: uvSetが文字列・None以外の場合。
            ValueError: 名前が空、そのUVセットが無い、またはメッシュにUVセットが無い場合。
        """
        ...
    def _require_uv_set(self, name: str, label: str, *, exists: bool) -> None:
        """UVセットの名前の型と、その有無を検証する。

        Args:
            name (str): UVセットの名前。
            label (str): 例外メッセージに使う引数名。
            exists (bool): Trueは既にあること、Falseはまだ無いことを求める。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: nameが空、または有無が求める状態と違う場合。
        """
        ...
    def _default_uv_set(self) -> str:
        """既定のUVセット(``uvSet[0]``)の名前を返す。

        Returns:
            str: 既定のUVセットの名前。
        """
        ...
    def _resolve_color_set(self, colorSet: str | None, fn: om2.MFnMesh) -> str | None:
        """カラーセットの指定を、実在する名前にする。

        Args:
            colorSet (str | None): カラーセットの名前。Noneは現在のカラーセット。
            fn (om2.MFnMesh): この mesh の function set。

        Returns:
            str | None: カラーセットの名前。Noneを指定してカラーセットが無ければNone。

        Raises:
            TypeError: colorSetが文字列・None以外の場合。
            ValueError: 名前が空、またはそのカラーセットが無い場合。
        """
        ...
    def _require_color_set(self, name: str, label: str, *, exists: bool) -> None:
        """カラーセットの名前の型と、その有無を検証する。

        Args:
            name (str): カラーセットの名前。
            label (str): 例外メッセージに使う引数名。
            exists (bool): Trueは既にあること、Falseはまだ無いことを求める。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: nameが文字列以外の場合。
            ValueError: nameが空、または有無が求める状態と違う場合。
        """
        ...
    def _resolve_vertex_indices(self, vertices: Component | Components | Iterable[int], count: int) -> list[int]:
        """頂点の指定を、範囲内で重複の無い番号の list にする。

        Args:
            vertices (Component | Components | Iterable[int]): 頂点の参照または番号。
            count (int): 頂点の数。

        Returns:
            list[int]: 指定順の番号。

        Raises:
            TypeError: 番号に変換できない型の場合。
            ValueError: 番号が重複している、または別のメッシュの頂点の場合。
            IndexError: 番号が範囲外の場合。
        """
        ...
    @staticmethod
    def _resolve_colors(colors: Iterable[Sequence[float] | om2.MColor], count: int) -> list[tuple[float, float, float, float]]:
        """色の列を検証し、(R, G, B, A) の float tuple の list にする。

        Args:
            colors (Iterable[Sequence[float] | om2.MColor]): 色の列。
            count (int): 必要な数。

        Returns:
            list[tuple[float, float, float, float]]: 色。Aを省略した色は1.0を補う。

        Raises:
            TypeError: 色の列・色・成分の型が不正な場合。
            ValueError: 数が合わない、成分の数が3・4以外、または有限でない場合。
        """
        ...
    def _set_vertex_colors_cmds(self, color_set: str | None, indices: list[int], values: list[tuple[float, float, float, float]]) -> None:
        """同じ色の頂点をまとめて ``cmds.polyColorPerVertex`` で書く。

        カラーセットを指定した場合は、書く間だけ現在のカラーセットを切り替えて戻す
        (``polyColorPerVertex`` は現在のカラーセットへ書くため)。

        Args:
            color_set (str | None): 書き込むカラーセット。Noneは現在のカラーセット。
            indices (list[int]): 頂点番号。
            values (list[tuple[float, float, float, float]]): indices と同じ順の色。

        Returns:
            None: 値を返さない。
        """
        ...
    def _set_vertex_colors_fast(self, fn: om2.MFnMesh, color_set: str | None, indices: list[int], values: list[tuple[float, float, float, float]]) -> None:
        """``MFnMesh.setVertexColors`` で色をまとめて書く。Undoに記録しない。

        Args:
            fn (om2.MFnMesh): この mesh の function set。
            color_set (str | None): 書き込むカラーセット。Noneは現在のカラーセット(無ければ ``colorSet1`` を作る)。
            indices (list[int]): 頂点番号。
            values (list[tuple[float, float, float, float]]): indices と同じ順の色。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: シェイプがロックされている場合。
            NotImplementedError: inMeshへの入力(コンストラクションヒストリ)がある場合。
        """
        ...
    def _mirror_plan(self, axis: str | int, ws: bool, pivot: Iterable[float], indices: Iterable[int] | None, fast: bool) -> tuple | None:
        """頂点を反転した座標を求め、書込みの計画を返す。シーンは変更しない。

        :meth:`Transform.mirrorGeometry <mlib.nodes.transform.Transform.mirrorGeometry>` が
        全Shapeを検証してから書き込むために使う。

        Args:
            axis (str | int): 反転する軸またはミラー面。
            ws (bool): Trueならワールド空間。検証済み。
            pivot (Iterable[float]): 指定空間の反転中心XYZ(cm)。
            indices (Iterable[int] | None): 頂点番号。Noneは全頂点。
            fast (bool): TrueならOpenMayaで直接書けるかも確かめる。

        Returns:
            tuple | None: ``(shape, indices, rows, ws)``。対象が無ければNone。
        """
        ...
    def _geometry_fn(self) -> om2.MFnMesh:
        """形状データを要する照会用に ``om2.MFnMesh`` を返す。

        Returns:
            om2.MFnMesh: この mesh の function set。

        Raises:
            RuntimeError: 保持する DAG パスが無効、または形状データを持たない空のシェイプの場合。
        """
        ...
