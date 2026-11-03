"""Mesh の Edge とコレクション。"""

import maya.api.OpenMaya as om2

from .component import Component, Components
from .vertex import Vertices


class Edge(Component):
    """Mesh の単一コンポーネント。"""

    shape_type = "mesh"
    component_type = "e"
    count_attribute = "getNumEdges"

    def getVertices(self):
        """接続する頂点群を取得する。

        Returns:
            Vertices: Maya の接続順の頂点群。
        """
        self._require_valid()
        return Vertices(self.shape, self.shape._geometry_fn().getEdgeVertices(self.index))

    def getLoop(self):
        """このエッジを通るエッジのループを取得する。

        :meth:`Edges.getLoop` と同じ規則。

        Returns:
            Edges: 自身を先頭に、たどった順のエッジ。
        """
        return Edges(self.shape, [self.index]).getLoop()

    def getRing(self):
        """このエッジを通るエッジのリングを取得する。

        :meth:`Edges.getRing` と同じ規則。

        Returns:
            Edges: 自身を先頭に、たどった順のエッジ。
        """
        return Edges(self.shape, [self.index]).getRing()


_EDGE_GET_VERTICES = Edge.getVertices


class Edges(Components):
    """同一 Mesh の Edge 群。"""

    component_class = Edge

    def getVertices(self):
        """接続する頂点群を取得する。

        Returns:
            Vertices: 保持順に集め、重複を除いた頂点群。
        """
        if not (self._uses_standard_iteration(Edge) and self._uses_standard_vertices()
                and Edge.getVertices is _EDGE_GET_VERTICES):
            return Vertices(self.shape, (v.index for item in self for v in item.getVertices()))
        indices = self._mesh_vertex_indices("numEdges", "getEdgeVertices")
        return Vertices(self.shape, indices)

    def getLoop(self):
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
        self._require_valid()
        topology = _Topology(self.shape)
        found = []
        for edge in self._indices:
            found.extend(topology.loop(edge))
        return Edges(self.shape, found)

    def getRing(self):
        """保持しているエッジを通るエッジのリングを取得する。選択は変えない。

        四角形のフェースを横切り、今のエッジと頂点を共有しない向かいのエッジへ進む。
        四角形でないフェース・メッシュの縁と、一周して戻った所で止まる。

        Returns:
            Edges: 保持順に各エッジのリングを両方向へたどった順のエッジ(重複なし)。

        Raises:
            IndexError: トポロジーの変更で保持番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        self._require_valid()
        topology = _Topology(self.shape)
        found = []
        for edge in self._indices:
            found.extend(topology.ring(edge))
        return Edges(self.shape, found)


class _Topology:
    """エッジ・頂点・フェースのつながりを、必要な要素だけ OpenMaya の反復子で照会して覚える。

    Args:
        mesh (Mesh): 照会するメッシュ。
    """

    def __init__(self, mesh):
        path = mesh.mpath()
        self._edge_iterator = om2.MItMeshEdge(path)
        self._vertex_iterator = om2.MItMeshVertex(path)
        self._face_iterator = om2.MItMeshPolygon(path)
        self._edge_vertices = {}
        self._edge_faces = {}
        self._vertex_edges = {}
        self._face_edges = {}

    def edge_vertices(self, edge):
        """エッジの両端の頂点番号を返す。"""
        if edge not in self._edge_vertices:
            self._edge_iterator.setIndex(edge)
            self._edge_vertices[edge] = (self._edge_iterator.vertexId(0), self._edge_iterator.vertexId(1))
        return self._edge_vertices[edge]

    def edge_faces(self, edge):
        """エッジに接するフェース番号を返す。"""
        if edge not in self._edge_faces:
            self._edge_iterator.setIndex(edge)
            self._edge_faces[edge] = tuple(self._edge_iterator.getConnectedFaces())
        return self._edge_faces[edge]

    def vertex_edges(self, vertex):
        """頂点に集まるエッジ番号を返す。"""
        if vertex not in self._vertex_edges:
            self._vertex_iterator.setIndex(vertex)
            self._vertex_edges[vertex] = tuple(self._vertex_iterator.getConnectedEdges())
        return self._vertex_edges[vertex]

    def face_edges(self, face):
        """フェースのエッジ番号を返す。"""
        if face not in self._face_edges:
            self._face_iterator.setIndex(face)
            self._face_edges[face] = tuple(self._face_iterator.getEdges())
        return self._face_edges[face]

    def loop(self, edge):
        """エッジのループを、始めのエッジから両方向へたどった順で返す。

        Args:
            edge (int): 始めのエッジ。

        Returns:
            list[int]: ループのエッジ(始めのエッジを含む)。
        """
        result = [edge]
        seen = {edge}
        for pivot in self.edge_vertices(edge):
            current = edge
            while True:
                following = self._loop_next(current, pivot)
                if following is None or following in seen:
                    break
                seen.add(following)
                result.append(following)
                start, end = self.edge_vertices(following)
                current, pivot = following, (end if start == pivot else start)
        return result

    def ring(self, edge):
        """エッジのリングを、始めのエッジから両方向へたどった順で返す。

        Args:
            edge (int): 始めのエッジ。

        Returns:
            list[int]: リングのエッジ(始めのエッジを含む)。
        """
        result = [edge]
        seen = {edge}
        for face in self.edge_faces(edge):
            current, crossing = edge, face
            while True:
                face_edges = self.face_edges(crossing)
                if len(face_edges) != 4:
                    break
                ends = set(self.edge_vertices(current))
                opposite = [other for other in face_edges if not ends.intersection(self.edge_vertices(other))]
                if len(opposite) != 1 or opposite[0] in seen:
                    break
                current = opposite[0]
                seen.add(current)
                result.append(current)
                following = [other for other in self.edge_faces(current) if other != crossing]
                if not following:
                    break
                crossing = following[0]
        return result

    def _loop_next(self, current, pivot):
        """ループで、頂点 pivot の先へ続くエッジを返す。続かなければ None。"""
        edges = self.vertex_edges(pivot)
        faces = set(self.edge_faces(current))
        if len(faces) != 2 or len(edges) != 4:
            return None
        # 向かいのエッジは、今のエッジとフェースを共有しないエッジ。
        following = [other for other in edges if other != current and not faces.intersection(self.edge_faces(other))]

        return following[0] if len(following) == 1 else None
