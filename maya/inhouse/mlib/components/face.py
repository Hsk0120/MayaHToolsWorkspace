"""Mesh の Face とコレクション。"""

import maya.api.OpenMaya as om2

from ..decorator import _pick_alias
from ..maths.vector import Vector, _vectors_of_points
from ..util import _UNSET, _checked_tolerance, _world_space
from .component import Component, Components
from .uv import UVs
from .vertex import Vertices


class Face(Component):
    """Mesh の単一コンポーネント。"""

    shape_type = "mesh"
    component_type = "f"
    count_attribute = "getNumPolygons"

    def getShadingEngine(self):
        """このインスタンスのフェースに割り当てられたセット。

        Returns:
            ShadingEngine | None: このインスタンスのフェースに割り当てられたセット。
        """
        self._require_valid()
        return self.shape.getFaceShadingEngines()[self.index]

    def getMaterial(self):
        """割り当てられたサーフェスシェーダー。

        Returns:
            Node | None: 割り当てられたサーフェスシェーダー。
        """
        group = self.getShadingEngine()
        return group.getShader() if group is not None else None

    def getVertices(self):
        """接続する頂点群を取得する。

        Returns:
            Vertices: Maya の接続順の頂点群。
        """
        self._require_valid()
        return Vertices(self.shape, self.shape._geometry_fn().getPolygonVertices(self.index))

    def getEdges(self):
        """この面のエッジを取得する。

        :meth:`Faces.getEdges` と同じ規則。

        Returns:
            Edges: 番号の昇順のエッジ(重複なし)。
        """
        return Faces(self.shape, [self.index]).getEdges()

    def getCenter(self, worldSpace=_UNSET, *, ws=_UNSET):
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
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        space = om2.MSpace.kWorld if _world_space(worldSpace) else om2.MSpace.kObject
        self._require_valid()
        it = om2.MItMeshPolygon(self.shape.mpath())
        it.setIndex(self.index)
        return _vectors_of_points([it.center(space)])[0]

    def getNormal(self, worldSpace=_UNSET, *, ws=_UNSET):
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
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        space = om2.MSpace.kWorld if _world_space(worldSpace) else om2.MSpace.kObject
        self._require_valid()
        return Vector(self.shape._geometry_fn().getPolygonNormal(self.index, space)).normal()

    def getArea(self, worldSpace=_UNSET, *, ws=_UNSET):
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
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        space = om2.MSpace.kWorld if _world_space(worldSpace) else om2.MSpace.kObject
        self._require_valid()
        it = om2.MItMeshPolygon(self.shape.mpath())
        it.setIndex(self.index)
        return it.getArea(space)

    def getConnectedFaces(self):
        """このフェースとエッジを共有するフェース(自身を含まない)を取得する(``MItMeshPolygon.getConnectedFaces``)。

        Returns:
            Faces: 番号の昇順のフェース(重複なし)。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        return Faces(self.shape, sorted(set(self._iterator().getConnectedFaces())))

    def getVertexFaces(self):
        """このフェースの頂点フェースを、フェースの頂点の順に取得する。

        Returns:
            VertexFaces: フェースの頂点の巡回順の頂点フェース。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        # vertexFace.py が face.py を import するため、循環を避けて呼出し時に読む。
        from .vertexFace import VertexFaces
        self._require_valid()
        vertices = self.shape._geometry_fn().getPolygonVertices(self.index)
        return VertexFaces(self.shape, [(vertex, self.index) for vertex in vertices])

    def getUVs(self):
        """このフェースの、現在のUVセットのUVを取得する。

        Returns:
            UVs: フェースの頂点の巡回順のUV(重複なし)。UVの無いフェースは空。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        iterator = self._iterator()
        uv_set = self.shape._geometry_fn().currentUVSetName()
        indices = []
        if iterator.hasUVs(uv_set):
            indices = [iterator.getUVIndex(local, uv_set) for local in range(iterator.polygonVertexCount())]
        return UVs(self.shape, indices)

    def isOnBoundary(self):
        """メッシュの縁(接する面が1つだけのエッジ)に接するフェースか照会する(``MItMeshPolygon.onBoundary``)。

        Returns:
            bool: 縁のエッジを持てばTrue。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        return self._iterator().onBoundary()

    def isPlanar(self):
        """フェースの頂点が同一平面上にあるか照会する(``MItMeshPolygon.isPlanar``)。

        Returns:
            bool: 平面ならTrue。三角形は常にTrue。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        return self._iterator().isPlanar()

    def isConvex(self):
        """凸多角形のフェースか照会する(``MItMeshPolygon.isConvex``)。

        Returns:
            bool: 凸ならTrue。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        return self._iterator().isConvex()

    def isLamina(self):
        """ラミナフェース(別のフェースとすべてのエッジを共有する重なったフェース)か照会する
        (``MItMeshPolygon.isLamina``)。

        Returns:
            bool: ラミナフェースならTrue。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        return self._iterator().isLamina()

    def isHoled(self):
        """穴を持つフェースか照会する(``MItMeshPolygon.isHoled``)。

        Returns:
            bool: 穴があればTrue。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        return self._iterator().isHoled()

    def isZeroArea(self, tolerance=1e-10):
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
        limit = _checked_tolerance(tolerance)
        return self._iterator().getArea() <= limit

    def getTriangleCount(self):
        """フェースを三角形に分割したときの三角形の数を取得する(``MItMeshPolygon.numTriangles``)。

        Returns:
            int: 三角形の数(``cmds.polyEvaluate(triangle=True)`` のフェース単位の値)。

        Raises:
            IndexError: 番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効な場合。
        """
        return self._iterator().numTriangles()

    def _iterator(self):
        """番号を検証し、このフェースへ移した ``om2.MItMeshPolygon`` を返す。

        Returns:
            om2.MItMeshPolygon: このフェースを指す反復子。
        """
        self._require_valid()
        iterator = om2.MItMeshPolygon(self.shape.mpath())
        iterator.setIndex(self.index)
        return iterator


_FACE_GET_VERTICES = Face.getVertices


class Faces(Components):
    """同一 Mesh の Face 群。"""

    component_class = Face

    def getShadingEngines(self):
        """対象フェースの割り当てを重複なしで返す。

        Returns:
            list[ShadingEngine]: 対象フェースの割り当てを重複なしで返す。
        """
        result = []
        assignments = self.shape.getFaceShadingEngines()
        for face in self:
            face._require_valid()
            group = assignments[face.index]
            if group is not None and group not in result:
                result.append(group)
        return result

    def getMaterials(self):
        """対象フェースのマテリアルを重複なしで返す。

        Returns:
            list[Node]: 対象フェースのマテリアルを重複なしで返す。
        """
        result = []
        for group in self.getShadingEngines():
            material = group.getShader()
            if material is not None and material not in result:
                result.append(material)
        return result

    def getVertices(self):
        """接続する頂点群を取得する。

        Returns:
            Vertices: 保持順に集め、重複を除いた頂点群。
        """
        if not (self._uses_standard_iteration(Face) and self._uses_standard_vertices()
                and Face.getVertices is _FACE_GET_VERTICES):
            return Vertices(self.shape, (v.index for item in self for v in item.getVertices()))
        indices = self._mesh_vertex_indices("numPolygons", "getPolygonVertices")
        return Vertices(self.shape, indices)

    def getEdges(self):
        """保持している面のエッジを取得する。選択は変えない。

        ``cmds.polyListComponentConversion(toEdge=True)`` と同じエッジになる。

        Returns:
            Edges: 番号の昇順のエッジ(重複なし)。面が空なら空。

        Raises:
            IndexError: トポロジーの変更で保持番号が範囲外になった場合。
            RuntimeError: シェイプが無効な場合。
        """
        # edge.py が face.py を import するため、循環を避けて呼出し時に読む。
        from .edge import Edges
        self._require_valid()
        iterator = om2.MItMeshPolygon(self.shape.mpath())
        found = set()
        for index in self._indices:
            iterator.setIndex(index)
            found.update(iterator.getEdges())
        return Edges(self.shape, sorted(found))
