"""Mesh の Face とコレクション。"""

import maya.api.OpenMaya as om2

from ..decorator import _pick_alias
from ..maths.vector import Vector, _vectors_of_points
from ..util import _UNSET, _world_space
from .component import Component, Components
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
