"""Mesh の Edge とコレクション。"""

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from ..decorator import _pick_alias, _require_bool, preservedSelection, undoChunk
from ..maths.vector import _vectors_of_points
from ..util import _UNSET, _world_space
from .component import Component, Components
from .face import Faces
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

    def getFaces(self):
        """このエッジに接する面を取得する。

        :meth:`Edges.getFaces` と同じ規則。

        Returns:
            Faces: 番号の昇順の面(重複なし)。
        """
        return Edges(self.shape, [self.index]).getFaces()

    def getLength(self, worldSpace=_UNSET, *, ws=_UNSET):
        """エッジの長さ(``MItMeshEdge.length``)を cm で取得する。

        Args:
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            float: 長さ(cm)。ワールド空間は親のスケールを含む。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        space = om2.MSpace.kWorld if _world_space(worldSpace) else om2.MSpace.kObject
        self._require_valid()
        it = om2.MItMeshEdge(self.shape.mpath())
        it.setIndex(self.index)
        return it.length(space)

    def getCenter(self, worldSpace=_UNSET, *, ws=_UNSET):
        """エッジの中点(``MItMeshEdge.center``)を取得する。

        Args:
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector: 中点の位置(cm)。

        Raises:
            TypeError: worldSpaceがbool以外、またはworldSpaceとwsを同時に指定した場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        space = om2.MSpace.kWorld if _world_space(worldSpace) else om2.MSpace.kObject
        self._require_valid()
        it = om2.MItMeshEdge(self.shape.mpath())
        it.setIndex(self.index)
        return _vectors_of_points([it.center(space)])[0]

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

    def getConnectedEdges(self):
        """このエッジと頂点を共有するエッジ(自身を含まない)を取得する(``MItMeshEdge.getConnectedEdges``)。

        Returns:
            Edges: 番号の昇順のエッジ(重複なし)。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        return Edges(self.shape, sorted(set(self._iterator().getConnectedEdges())))

    def isOnBoundary(self):
        """メッシュの縁(接する面が1つだけ)のエッジか照会する。

        Returns:
            bool: 縁ならTrue。:meth:`Mesh.getBorderEdges <mlib.nodes.mesh.Mesh.getBorderEdges>` と同じ判定。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        return self._iterator().numConnectedFaces() == 1

    def isSmooth(self):
        """ソフトエッジ(スムーズ)か照会する(``MFnMesh.isEdgeSmooth``)。

        Returns:
            bool: ソフトエッジならTrue、ハードエッジならFalse。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        self._require_valid()
        return self.shape._geometry_fn().isEdgeSmooth(self.index)

    def setSmooth(self, value=True):
        """ソフトエッジ(True)・ハードエッジ(False)を設定し、自身を返す。

        ``cmds.polySoftEdge`` (角度180または0)で書き込み、1回のUndoにまとめる。選択は変えない。コンストラクションヒストリの
        あるメッシュでは ``polySoftEdge`` ノードを履歴へ足し、無いメッシュは履歴を作らずに直接書く。

        Args:
            value (bool): Trueはソフトエッジ、Falseはハードエッジ。

        Returns:
            Edge: 自身。

        Raises:
            TypeError: valueがbool以外の場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはロック等でMayaが書込みを拒否した場合。
        """
        _require_bool(value, "value")
        self._require_valid()
        history = om2.MFnDependencyNode(self.shape.mnode()).findPlug("inMesh", False).isDestination
        # polySoftEdgeは対象のエッジを選択するため、選択を戻す処理も同じUndoに含める(Redoでも選択が変わらない)。
        with undoChunk("mlibEdgeSetSmooth"), preservedSelection():
            cmds.polySoftEdge(self.getFullName(), angle=180 if value else 0, constructionHistory=history)
        return self

    def _iterator(self):
        """番号を検証し、このエッジへ移した ``om2.MItMeshEdge`` を返す。

        Returns:
            om2.MItMeshEdge: このエッジを指す反復子。
        """
        self._require_valid()
        iterator = om2.MItMeshEdge(self.shape.mpath())
        iterator.setIndex(self.index)
        return iterator


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

    def getFaces(self):
        """保持しているエッジのどれかに接する面を取得する。選択は変えない。

        ``cmds.polyListComponentConversion(toFace=True)`` と同じ面になる。

        Returns:
            Faces: 番号の昇順の面(重複なし)。エッジが空なら空。

        Raises:
            IndexError: トポロジーの変更で保持番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        self._require_valid()
        topology = _Topology(self.shape)
        found = set()
        for edge in self._indices:
            found.update(topology.edge_faces(edge))
        return Faces(self.shape, sorted(found))

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
