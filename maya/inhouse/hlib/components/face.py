"""Mesh の Face とコレクション。"""

from .component import Component, Components
from .vertex import Vertices


class Face(Component):
    """Mesh の単一コンポーネント。"""

    shape_type = "mesh"
    component_type = "f"
    count_attribute = "numPolygons"

    def shadingEngine(self):
        """このインスタンスのフェースに割り当てられたセット。

        Returns:
            ShadingEngine | None: このインスタンスのフェースに割り当てられたセット。
        """
        self._validate()
        return self.shape.faceShadingEngines()[self.index]

    def material(self):
        """割り当てられたサーフェスシェーダー。

        Returns:
            Node | None: 割り当てられたサーフェスシェーダー。
        """
        group = self.shadingEngine()
        return group.getShader() if group is not None else None

    def vertices(self):
        """接続する頂点群を取得する。

        Returns:
            Vertices: Maya の接続順の頂点群。
        """
        self._validate()
        return Vertices(self.shape, self.shape.meshFn().getPolygonVertices(self.index))


class Faces(Components):
    """同一 Mesh の Face 群。"""

    component_class = Face

    def shadingEngines(self):
        """対象フェースの割り当てを重複なしで返す。

        Returns:
            list[ShadingEngine]: 対象フェースの割り当てを重複なしで返す。
        """
        result = []
        assignments = self.shape.faceShadingEngines()
        for face in self:
            face._validate()
            group = assignments[face.index]
            if group is not None and group not in result:
                result.append(group)
        return result

    def materials(self):
        """対象フェースのマテリアルを重複なしで返す。

        Returns:
            list[Node]: 対象フェースのマテリアルを重複なしで返す。
        """
        result = []
        for group in self.shadingEngines():
            material = group.getShader()
            if material is not None and material not in result:
                result.append(material)
        return result

    def vertices(self):
        """接続する頂点群を取得する。

        Returns:
            Vertices: 保持順に集め、重複を除いた頂点群。
        """
        return Vertices(self.shape, (v.index for item in self for v in item.vertices()))
