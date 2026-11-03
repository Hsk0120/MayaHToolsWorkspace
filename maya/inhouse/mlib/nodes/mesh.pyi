# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya のメッシュシェイプを扱う。"""

import math
from collections import Counter, defaultdict
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from maya.api.OpenMaya import MSpace
from ..components.edge import Edge, Edges
from ..components.face import Face, Faces
from ..components.uv import UV, UVs
from ..components.vertex import Vertex, Vertices
from ..core import geometryEdit as geometry_edit
from ..core.fastWrite import require_writable
from ..decorator import _edit_context, _require_bool, undoTransaction
from ..maths.vector import Vector, _vector_of, _vectors_of_points
from ..util import _PointGrid, _checked_tolerance, _mirror_axis, _world_space
from .shape import Shape
from typing import Iterable, Sequence
from mlib.nodes.node import Node
from mlib.nodes.shadingEngine import ShadingEngine



class Mesh(Shape):
    """Maya mesh shape ノードのラッパー。"""
    def reorderVertices(self, reference: Mesh | Node | str, uvSet: str = ..., tolerance: float = ..., *, fast: bool = ..., match: str = ..., worldSpace: bool = ...) -> Mesh:
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

        Returns:
            Mesh: 自身。番号対応が既に同一なら再構築せず返し、再構築用の制限検査にも進まない。

        Raises:
            TypeError: 入力型・fast/worldSpaceが不正な場合。
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
    def getPoints(self, worldSpace: bool = ...) -> list[Vector]:
        """全頂点の位置を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。

        Returns:
            list[Vector]: 頂点番号順の位置(:class:`~mlib.maths.vector.Vector`)。距離は Maya API の
                内部単位(cm)。そのまま :meth:`setPoints` へ渡せる。
        """
        ...
    def setPoints(self, points: Iterable[Sequence[float] | om2.MPoint | om2.MVector], worldSpace: bool = ..., *, fast: bool = ...) -> Mesh:
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
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Mesh: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、または点の型・成分が不正な場合。
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
    def getVertexNormals(self, worldSpace: bool = ..., angleWeighted: bool = ...) -> list[Vector]:
        """各頂点に接する面頂点法線を平均し、頂点ごとの法線を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            angleWeighted (bool): True の場合は隣接面の角度でウェイト付けした法線を取得する。

        Returns:
            list[Vector]: 頂点番号順の平均法線。angleWeighted=False では
                角度によるウェイト付けを行わない。MFnMesh.getVertexNormals() を使用する。
        """
        ...
    def getVertexAdjacency(self, worldSpace: bool = ...) -> list[list[tuple[int, float]]]:
        """頂点IDごとの隣接頂点とエッジ長を照会する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。

        Returns:
            list[list[tuple[int, float]]]: 頂点ID順の隣接リスト。
            各要素は隣接頂点IDとcm単位の距離で、エッジID順に格納する。
            孤立頂点は空リスト、重複エッジは別々に保持する。
        """
        ...
    def getShells(self) -> list[Vertices]:
        """辺でつながった頂点のまとまり(シェル)を取得する。

        Returns:
            list[Vertices]: シェルごとの頂点(番号の昇順)。シェルは最小の頂点番号の順に並ぶ。
                孤立した頂点は1頂点のシェルになる。
        """
        ...
    def getTriangles(self) -> list[tuple[int, int, int]]:
        """Maya の三角形分割で、ポリゴンを三角形に分けた頂点の組を取得する。

        Returns:
            list[tuple[int, int, int]]: 三角形ごとの頂点番号。フェース番号の順で、各フェース内は Maya の分割順。
        """
        ...
    def getMirrorVertexMap(self, axis: str | int = ..., tolerance: float = ..., worldSpace: bool = ...) -> dict[int, int]:
        """頂点ごとに、位置を軸で反転した反対側の頂点を取得する。

        反転した位置から ``tolerance`` 以内で最も近い頂点を反対側とする。トポロジーは見ない。

        Args:
            axis (str | int): 反転する軸 ``"x"``・``"y"``・``"z"``、ミラー面 ``"YZ"``・``"XZ"``・``"XY"``、または0/1/2。既定 ``"x"``。
            tolerance (float): 反転した位置と頂点の距離の許容量(cm)。正の有限値。既定0.01。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。

        Returns:
            dict[int, int]: {頂点番号: 反対側の頂点番号}。反対側が見つからない頂点は含めない。
                軸の上の頂点は自身へ対応する(キーと値が同じ)。

        Raises:
            TypeError: axisが文字列・int以外、toleranceが実数以外、またはworldSpaceがbool以外の場合。
            ValueError: axisが不正、またはtoleranceが正の有限値でない場合。
        """
        ...
    def getClosestVertex(self, point: Sequence[float] | om2.MPoint | om2.MVector, worldSpace: bool = ...) -> Vertex:
        """指定した位置に最も近い頂点を取得する。

        頂点の位置だけで比べる(面の上の最近点ではない)。多数の点を調べるなら :meth:`getClosestVertices` を使う。

        Args:
            point (Sequence[float] | om2.MPoint | om2.MVector): 位置(cm)。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。

        Returns:
            Vertex: 最も近い頂点。

        Raises:
            TypeError: 点の型・成分が不正、またはworldSpaceがbool以外の場合。
            ValueError: 成分が有限でない、またはメッシュに頂点が無い場合。
        """
        ...
    def getClosestVertices(self, points: Iterable[Sequence[float] | om2.MPoint | om2.MVector], worldSpace: bool = ...) -> list[int]:
        """点ごとに、最も近い頂点の番号を取得する。

        頂点の位置に一様な格子を作って探す(面の上の最近点ではない)。

        Args:
            points (Iterable[Sequence[float] | om2.MPoint | om2.MVector]): 位置(cm)の並び。
            worldSpace (bool): Trueはワールド空間、Falseはオブジェクト空間。

        Returns:
            list[int]: 点の順の、最も近い頂点の番号。

        Raises:
            TypeError: 点列・点の型・成分が不正、またはworldSpaceがbool以外の場合。
            ValueError: 成分が有限でない、またはメッシュに頂点が無い場合。
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
    def _geometry_fn(self) -> om2.MFnMesh:
        """形状データを要する照会用に ``om2.MFnMesh`` を返す。

        Returns:
            om2.MFnMesh: この mesh の function set。

        Raises:
            RuntimeError: 保持する DAG パスが無効、または形状データを持たない空のシェイプの場合。
        """
        ...
