# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mesh の Edge とコレクション。"""

import maya.api.OpenMaya as om2
from .component import Component, Components
from .face import Faces
from .vertex import Vertices
from typing import Any, Iterator
from typing import overload



class Edge(Component):
    """Mesh の単一コンポーネント。"""
    shape_type: str
    component_type: str
    count_attribute: str
    def getVertices(self) -> Vertices:
        """接続する頂点群を取得する。

        Returns:
            Vertices: Maya の接続順の頂点群。
        """
        ...
    def getFaces(self) -> Faces:
        """このエッジに接する面を取得する。

        :meth:`Edges.getFaces` と同じ規則。

        Returns:
            Faces: 番号の昇順の面(重複なし)。
        """
        ...
    def getLoop(self) -> Edges:
        """このエッジを通るエッジのループを取得する。

        :meth:`Edges.getLoop` と同じ規則。

        Returns:
            Edges: 自身を先頭に、たどった順のエッジ。
        """
        ...
    def getRing(self) -> Edges:
        """このエッジを通るエッジのリングを取得する。

        :meth:`Edges.getRing` と同じ規則。

        Returns:
            Edges: 自身を先頭に、たどった順のエッジ。
        """
        ...
_EDGE_GET_VERTICES: Any


class Edges(Components):
    """同一 Mesh の Edge 群。"""
    def __iter__(self) -> Iterator[Edge]: ...
    @overload
    def __getitem__(self, index: int) -> Edge: ...
    @overload
    def __getitem__(self, index: slice) -> Edges: ...
    component_class: Any
    def getVertices(self) -> Vertices:
        """接続する頂点群を取得する。

        Returns:
            Vertices: 保持順に集め、重複を除いた頂点群。
        """
        ...
    def getFaces(self) -> Faces:
        """保持しているエッジのどれかに接する面を取得する。選択は変えない。

        ``cmds.polyListComponentConversion(toFace=True)`` と同じ面になる。

        Returns:
            Faces: 番号の昇順の面(重複なし)。エッジが空なら空。

        Raises:
            IndexError: トポロジーの変更で保持番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    def getLoop(self) -> Edges:
        """保持しているエッジを通るエッジのループを取得する。選択は変えない。

        4本のエッジが集まる頂点で、今のエッジとフェースを共有しない向かいのエッジへ進む
        (``cmds.polySelect(edgeLoop=...)`` と同じ規則)。それ以外の頂点(極)・メッシュの縁のエッジと、
        一周して戻った所で止まる。

        Returns:
            Edges: 保持順に各エッジのループを両方向へたどった順のエッジ(重複なし)。

        Raises:
            IndexError: トポロジーの変更で保持番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...
    def getRing(self) -> Edges:
        """保持しているエッジを通るエッジのリングを取得する。選択は変えない。

        四角形のフェースを横切り、今のエッジと頂点を共有しない向かいのエッジへ進む。
        四角形でないフェース・メッシュの縁と、一周して戻った所で止まる。

        Returns:
            Edges: 保持順に各エッジのリングを両方向へたどった順のエッジ(重複なし)。

        Raises:
            IndexError: トポロジーの変更で保持番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        ...


class _Topology:
    """エッジ・頂点・フェースのつながりを、必要な要素だけ OpenMaya の反復子で照会して覚える。

    Args:
        mesh (Mesh): 照会するメッシュ。
    """
    def __init__(self, mesh) -> None: ...
    def edge_vertices(self, edge):
        """エッジの両端の頂点番号を返す。"""
        ...
    def edge_faces(self, edge):
        """エッジに接するフェース番号を返す。"""
        ...
    def vertex_edges(self, vertex):
        """頂点に集まるエッジ番号を返す。"""
        ...
    def face_edges(self, face):
        """フェースのエッジ番号を返す。"""
        ...
    def loop(self, edge: int) -> list[int]:
        """エッジのループを、始めのエッジから両方向へたどった順で返す。

        Args:
            edge (int): 始めのエッジ。

        Returns:
            list[int]: ループのエッジ(始めのエッジを含む)。
        """
        ...
    def ring(self, edge: int) -> list[int]:
        """エッジのリングを、始めのエッジから両方向へたどった順で返す。

        Args:
            edge (int): 始めのエッジ。

        Returns:
            list[int]: リングのエッジ(始めのエッジを含む)。
        """
        ...
    def _loop_next(self, current, pivot):
        """ループで、頂点 pivot の先へ続くエッジを返す。続かなければ None。"""
        ...
