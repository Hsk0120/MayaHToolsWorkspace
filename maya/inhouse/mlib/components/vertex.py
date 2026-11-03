"""Mesh の頂点と頂点コレクション。"""

import maya.api.OpenMaya as om2

from .pointComponent import PointComponent, PointComponents


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
