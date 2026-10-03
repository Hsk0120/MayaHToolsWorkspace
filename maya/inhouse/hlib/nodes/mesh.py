"""Maya のメッシュシェイプを扱う。"""
from maya.api.OpenMaya import MSpace
from .._core.space import world_space

from ..decorators._fast import fast_edit

import maya.api.OpenMaya as om2

from .._core.registry import node_wrapper
from ..components.vertex import Vertex, Vertices
from ..components.edge import Edge, Edges
from ..components.face import Face, Faces
from ..components.uv import UV, UVs
from .shape import Shape


@node_wrapper("mesh")
class Mesh(Shape):
    """Maya mesh shape ノードのラッパー。"""

    @fast_edit
    def mirror(self, axis="x", space=MSpace.kObject, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False):
        """頂点位置をミラーし、自身を更新する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            axis (str): 反転する座標軸。x、y、z、xy、xz、yz、xyz。大文字も可。
                x は pivot.x を通る YZ 平面で反転する。複数軸は同時に反転する。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
            pivot (Iterable[float]): 指定空間での反転中心。既定はその空間の原点。
                単位は 内部距離単位cm。Transform のピボットとは独立する。
            indices (Iterable[int] | None): 頂点番号。None は全頂点、空列は変更なし。
                重複は1回だけ処理し、負の番号は許容しない。

        Returns:
            Mesh: 編集した自身。

        Raises:
            ValueError: 軸・空間・中心が不正、またはワールド変換が数値的にほぼ特異な場合。
            TypeError: 頂点番号が整数でない場合。
            IndexError: 頂点番号が範囲外の場合。
            RuntimeError: Maya が形状の取得・編集を拒否した場合。

        頂点だけを編集し、Transform、頂点番号、面の接続・頂点順は維持する。
        複製・結合・片側からの対称化・法線反転は行わない。奇数軸で反転すると
        面の向きが反転するため、必要な法線処理は別途行う。1回の Undo で戻せる。
        インスタンス形状はデータを共有する全インスタンスへ影響する。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        fastで入力履歴付き形状を編集するとNotImplementedError。
        """
        ws = world_space(space)
        self.vertices(indices).mirror(axis=axis, space=MSpace.kWorld if ws else MSpace.kObject, pivot=pivot)
        return self

    def vertex(self, index):
        """頂点番号から単体ラッパーを取得する。

        Args:
            index (int): ゼロ始まりの頂点番号。

        Returns:
            Vertex: シーン上の頂点を参照するラッパー。

        Raises:
            IndexError: 頂点番号が範囲外の場合。
        """
        return Vertex(self, index)

    def vertices(self, indices=None):
        """指定した頂点群を取得する。

        Args:
            indices (Iterable[int] | None): 頂点番号。None は現在の全頂点。

        Returns:
            Vertices: 番号順を維持し、重複を除いたコレクション。
        """
        return Vertices(self, indices)

    def shadingEngines(self):
        """このDAGインスタンスのフェースへ割り当てられたShadingEngineを返す。

        Returns:
            list[ShadingEngine]: 使用中のセット。未割り当ては除外する。
        """
        from .shadingEngine import ShadingEngine
        groups, indices = self.meshFn().getConnectedShaders(self.dagPath().instanceNumber())
        return [ShadingEngine(groups[i]) for i in sorted(set(indices)) if i >= 0]

    def faceShadingEngines(self):
        """面番号順の割り当てを取得する。

        Returns:
            list[ShadingEngine | None]: 全フェースの割り当て。未割り当てはNone。
        """
        from .shadingEngine import ShadingEngine
        groups, indices = self.meshFn().getConnectedShaders(self.dagPath().instanceNumber())
        wrapped = [ShadingEngine(group) for group in groups]
        return [wrapped[i] if i >= 0 else None for i in indices]

    def meshFn(self):
        """MFnMesh を取得する。

        Returns:
            om2.MFnMesh: この mesh の function set。
        """
        return om2.MFnMesh(self.dagPath())

    def numVertices(self):
        """頂点数を取得する。

        Returns:
            int: mesh の頂点数。
        """
        return self.meshFn().numVertices

    def numPolygons(self):
        """ポリゴン数を取得する。

        Returns:
            int: mesh のポリゴン数。
        """
        return self.meshFn().numPolygons

    def numEdges(self):
        """エッジ数を取得する。

        Returns:
            int: メッシュのエッジ数。
        """
        return self.meshFn().numEdges

    def getPoints(self, space=MSpace.kObject):
        """全頂点の位置を取得する。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            om2.MPointArray: 頂点番号順の位置。距離は Maya API の内部単位。
        """
        ws = world_space(space)
        space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
        return self.meshFn().getPoints(space)

    def getNormals(self, space=MSpace.kObject, angle_weighted=False):
        """各頂点に接する面頂点法線を平均し、頂点ごとの法線を取得する。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
            angle_weighted (bool): True の場合は隣接面の角度で重み付けした法線を取得する。

        Returns:
            om2.MFloatVectorArray: 頂点番号順の平均法線。angle_weighted=False では
                角度による重み付けを行わない。MFnMesh.getVertexNormals() を使用する。
        """
        ws = world_space(space)
        space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
        return self.meshFn().getVertexNormals(angle_weighted, space)

    def edge(self, index):
        """番号から Edge を取得する。

        Args:
            index (int): ゼロ始まりの番号。

        Returns:
            Edge: シーンを参照する単体ラッパー。
        """
        return Edge(self, index)

    def edges(self, indices=None):
        """指定した Edge 群を取得する。

        Args:
            indices (Iterable[int] | None): 番号列。None は現在の全要素。

        Returns:
            Edges: 重複を除いたコレクション。
        """
        return Edges(self, indices)

    def face(self, index):
        """番号から Face を取得する。

        Args:
            index (int): ゼロ始まりの番号。

        Returns:
            Face: シーンを参照する単体ラッパー。
        """
        return Face(self, index)

    def faces(self, indices=None):
        """指定した Face 群を取得する。

        Args:
            indices (Iterable[int] | None): 番号列。None は現在の全要素。

        Returns:
            Faces: 重複を除いたコレクション。
        """
        return Faces(self, indices)

    def uv(self, index):
        """番号から UV を取得する。

        Args:
            index (int): ゼロ始まりの番号。

        Returns:
            UV: シーンを参照する単体ラッパー。
        """
        return UV(self, index)

    def uvs(self, indices=None):
        """指定した UV 群を取得する。

        Args:
            indices (Iterable[int] | None): 番号列。None は現在の全要素。

        Returns:
            UVs: 重複を除いたコレクション。
        """
        return UVs(self, indices)

    def numUVs(self):
        """現在の UV セットの要素数。

        Returns:
            int: UV 数。
        """
        return self.meshFn().numUVs()
