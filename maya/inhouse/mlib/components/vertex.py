"""Mesh の頂点と頂点コレクション。"""

import maya.api.OpenMaya as om2

from ..decorator import _pick_alias, _require_bool
from ..maths.vector import Vector
from ..util import _UNSET, _world_space
from .pointComponent import PointComponent, PointComponents
from .uv import UVs


class Vertex(PointComponent):
    """Mesh 上の単一頂点。番号はゼロ始まり。"""

    shape_type = "mesh"
    component_type = "vtx"
    count_attribute = "getNumVertices"

    def getFaces(self):
        """この頂点に触れている面を取得する。

        :meth:`Vertices.getFaces` と同じ規則。

        Returns:
            Faces: 番号の昇順の面(重複なし)。
        """
        return Vertices(self.shape, [self.index]).getFaces()

    def getEdges(self):
        """この頂点に集まるエッジを取得する。

        ``cmds.polyListComponentConversion(toEdge=True)`` と同じエッジになる。

        Returns:
            Edges: 番号の昇順のエッジ(重複なし)。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        # edge.py が vertex.py を import するため、循環を避けて呼出し時に読む。
        from .edge import Edges
        iterator = self._iterator()
        return Edges(self.shape, sorted(set(iterator.getConnectedEdges())))

    def getConnectedVertices(self):
        """エッジでつながった隣の頂点(自身を含まない)を取得する。

        Returns:
            Vertices: 番号の昇順の頂点(重複なし)。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        iterator = self._iterator()
        return Vertices(self.shape, sorted(set(iterator.getConnectedVertices())))

    def getVertexFaces(self):
        """この頂点の頂点フェース(頂点に触れる各フェースとの組)を取得する。

        Returns:
            VertexFaces: フェース番号の昇順の頂点フェース。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        # vertexFace.py が vertex.py を import するため、循環を避けて呼出し時に読む。
        from .vertexFace import VertexFaces
        faces = sorted(self._iterator().getConnectedFaces())
        return VertexFaces(self.shape, [(self.index, face) for face in faces])

    def getUVs(self):
        """この頂点に割り当てられた、現在のUVセットのUVを取得する。

        UVの境界(シーム)上の頂点は複数のUVを持つ。

        Returns:
            UVs: 番号の昇順のUV(重複なし)。UVが無ければ空。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        iterator = self._iterator()
        uv_set = self.shape._geometry_fn().currentUVSetName()
        return UVs(self.shape, sorted(set(iterator.getUVIndices(uv_set))))

    def isOnBoundary(self):
        """メッシュの縁(接する面が1つだけのエッジ)上の頂点か照会する(``MItMeshVertex.onBoundary``)。

        Returns:
            bool: 縁の上ならTrue。:meth:`Mesh.getBorderVertices <mlib.nodes.mesh.Mesh.getBorderVertices>` に
                含まれる頂点と同じ。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        return self._iterator().onBoundary()

    def getColor(self, colorSet=None):
        """頂点の色を取得する。

        :meth:`Mesh.getVertexColors <mlib.nodes.mesh.Mesh.getVertexColors>` のこの頂点の値と同じ
        (面ごとに違う色を持つ頂点は、その平均)。

        Args:
            colorSet (str | None): カラーセットの名前。Noneは現在のカラーセット。

        Returns:
            tuple[float, float, float, float] | None: (R, G, B, A)。色が無い場合はNone。

        Raises:
            TypeError: colorSetが文字列・None以外の場合。
            ValueError: 指定した名前のカラーセットが無い場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        self._require_valid()
        return self.shape.getVertexColors(colorSet)[self.index]

    def setColor(self, color, colorSet=None, *, fast=False):
        """頂点の色を設定し、自身を返す。

        :meth:`Mesh.setVertexColors <mlib.nodes.mesh.Mesh.setVertexColors>` でこの頂点だけを書く。
        通常は ``cmds.polyColorPerVertex`` で1回のUndoにまとめ、``fast=True`` はUndoに記録しない。
        頂点のすべての頂点フェースの色を同じ色にする。

        Args:
            color (Sequence[float] | om2.MColor): (R, G, B) または (R, G, B, A) の有限な数値(Aの省略は1.0)。
            colorSet (str | None): カラーセットの名前。Noneは現在のカラーセット(無ければMayaが
                ``colorSet1`` を作る)。名前を指定した場合は既にある必要がある。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Vertex: 自身。

        Raises:
            TypeError: fastがbool以外、colorSetが文字列・None以外、または色の型が不正な場合。
            ValueError: 成分の数が3・4以外か有限でない、またはカラーセットが無い場合。
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、inMeshへの入力(コンストラクションヒストリ)がある場合。
        """
        self._require_valid()
        self.shape.setVertexColors([color], [self.index], colorSet=colorSet, fast=fast)
        return self

    def getNormal(self, worldSpace=_UNSET, angleWeighted=False, *, ws=_UNSET):
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
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        space = om2.MSpace.kWorld if _world_space(worldSpace) else om2.MSpace.kObject
        _require_bool(angleWeighted, "angleWeighted")
        self._require_valid()
        return Vector(self.shape._geometry_fn().getVertexNormal(self.index, angleWeighted, space)).normal()

    def _iterator(self):
        """番号を検証し、この頂点へ移した ``om2.MItMeshVertex`` を返す。

        Returns:
            om2.MItMeshVertex: この頂点を指す反復子。
        """
        self._require_valid()
        iterator = om2.MItMeshVertex(self.shape.mpath())
        iterator.setIndex(self.index)
        return iterator


class Vertices(PointComponents):
    """同一 Mesh の頂点群。座標取得・部分列取得・ミラーに対応する。"""

    component_class = Vertex

    def grow(self):
        """辺でつながった隣の頂点を加えた頂点群を取得する。選択は変えない。

        Returns:
            Vertices: 保持順の頂点のあとに、加えた頂点を番号の昇順で続けた新しい頂点群。

        Raises:
            IndexError: トポロジーの変更で保持番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        neighbors = self._neighbor_indices()
        added = sorted({index for indices in neighbors.values() for index in indices}.difference(self._indices))
        return Vertices(self.shape, list(self._indices) + added)

    def shrink(self):
        """保持していない頂点と辺でつながる頂点(縁)を除いた頂点群を取得する。選択は変えない。

        Returns:
            Vertices: 保持順を保った新しい頂点群。全てが縁なら空。

        Raises:
            IndexError: トポロジーの変更で保持番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        neighbors = self._neighbor_indices()
        kept = set(self._indices)
        return Vertices(self.shape, [index for index in self._indices if kept.issuperset(neighbors[index])])

    def getFaces(self):
        """保持している頂点のどれかに触れている面を取得する。選択は変えない。

        ``cmds.polyListComponentConversion(toFace=True)`` と同じ面になる。

        Returns:
            Faces: 番号の昇順の面(重複なし)。頂点が空なら空。

        Raises:
            IndexError: トポロジーの変更で保持番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        # face.py が vertex.py を import するため、循環を避けて呼出し時に読む。
        from .face import Faces
        self._require_valid()
        iterator = om2.MItMeshVertex(self.shape.mpath())
        found = set()
        for index in self._indices:
            iterator.setIndex(index)
            found.update(iterator.getConnectedFaces())
        return Faces(self.shape, sorted(found))

    def _neighbor_indices(self):
        """保持している頂点ごとに、辺でつながった頂点番号を返す。

        Returns:
            dict[int, list[int]]: {頂点番号: 隣の頂点番号}。
        """
        self._require_valid()
        iterator = om2.MItMeshVertex(self.shape.mpath())
        neighbors = {}
        for index in self._indices:
            iterator.setIndex(index)
            neighbors[index] = list(iterator.getConnectedVertices())
        return neighbors
