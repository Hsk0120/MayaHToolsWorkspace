"""Maya のメッシュシェイプを扱う。"""

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
    def mirror(self, axis="x", ws=False, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False):
        """頂点位置をミラーし、自身を更新する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            axis (str): 反転する座標軸。x、y、z、xy、xz、yz、xyz。大文字も可。
                x は pivot.x を通る YZ 平面で反転する。複数軸は同時に反転する。
            ws (bool): True はワールド軸、False はオブジェクト空間の軸。既定は False。
            pivot (Iterable[float]): 指定空間での反転中心。既定はその空間の原点。
                単位は Maya の現在の距離単位。Transform のピボットとは独立する。
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
        """
        self.vertices(indices).mirror(axis=axis, ws=ws, pivot=pivot)
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

    def mesh_fn(self):
        """MFnMesh を取得する。

        Returns:
            om2.MFnMesh: この mesh の function set。
        """
        return om2.MFnMesh(self.dag_path())

    @property
    def num_vertices(self):
        """頂点数を取得する。

        Returns:
            int: mesh の頂点数。
        """
        return self.mesh_fn().numVertices

    @property
    def num_polygons(self):
        """ポリゴン数を取得する。

        Returns:
            int: mesh のポリゴン数。
        """
        return self.mesh_fn().numPolygons

    @property
    def num_edges(self):
        """エッジ数を取得する。

        Returns:
            int: メッシュのエッジ数。
        """
        return self.mesh_fn().numEdges

    def points(self, ws=False):
        """全頂点の位置を取得する。

        Args:
            ws (bool): True はワールド空間、False はオブジェクト空間。

        Returns:
            om2.MPointArray: 頂点番号順の位置。距離は Maya API の内部単位。
        """
        space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
        return self.mesh_fn().getPoints(space)

    def normals(self, ws=False, angle_weighted=False):
        """全頂点の法線を取得する。

        Args:
            ws (bool): True はワールド空間、False はオブジェクト空間。
            angle_weighted (bool): True の場合は隣接面の角度で重み付けした法線を取得する。

        Returns:
            om2.MFloatVectorArray: 頂点番号順の法線。共有頂点は面ごとに異なる
                場合があるため、代表値として最初の面法線を返す(MFnMesh の仕様)。
        """
        space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
        return self.mesh_fn().getVertexNormals(angle_weighted, space)

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

    @property
    def num_uvs(self):
        """現在の UV セットの要素数。

        Returns:
            int: UV 数。
        """
        return self.mesh_fn().numUVs()
