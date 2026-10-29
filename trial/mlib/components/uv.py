"""Mesh の現在の UV セットを参照する UV 型。"""

from .component import Component, Components


class UV(Component):
    """Mesh参照とUV番号を保持し、現在のUVセットのU/V座標を照会する。

    UVセット名は固定して保持しない。切替後は同じ番号で切替先のセットを参照する。
    U/Vは無次元で、0〜1に制限しない。
    """

    shape_type = "mesh"
    component_type = "map"
    count_attribute = "getNumUVs"

    def getPosition(self):
        """現在のUVセットから、保持番号のU/V座標を取得する。

        Returns:
            tuple[float, float]: 新しい無次元の(U, V)値。UI距離単位やobject/ワールド空間とは無関係。

        Raises:
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshまたは現在のUVセットを参照できない場合。
        """
        self._require_valid()
        mesh_fn = self.shape._geometry_fn()
        return tuple(mesh_fn.getUV(self._index, uvSet=mesh_fn.currentUVSetName()))

    def getU(self):
        """U成分の現在値を取得する。

        Returns:
            float: 座標値。
        """
        return self._get_coordinate(0)

    def getV(self):
        """V成分の現在値を取得する。

        Returns:
            float: 座標値。
        """
        return self._get_coordinate(1)


_UV_GET_POSITION = UV.getPosition


class UVs(Components):
    """同一MeshのUV番号列を保持し、現在のUVセットの座標を保持順に扱う。

    セット名や座標値は保持せず、セット切替後は切替先の同じ番号を使う。
    """

    component_class = UV

    def getU(self):
        """U成分の現在値を取得する。

        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(0)

    def getV(self):
        """V成分の現在値を取得する。

        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(1)

    def getPosition(self):
        """現在のUVセットのU/V座標を、保持番号の順に取得する。

        標準実装は同じMFnMeshと現在UVセット名を使って各番号を問い合わせる。
        単数参照や反復が拡張されている場合は、各要素のgetPositionへ委譲する。

        Returns:
            list[tuple[float, float]]: 新しい無次元のU/V値リスト。座標への書換え可能な参照ではない。
                標準実装の空集合は、Shapeを再照会せず空リストを返す。

        Raises:
            IndexError: 保持番号が現在のUVセットの範囲外の場合。
            RuntimeError: Meshまたは現在のUVセットを参照できない場合。
        """
        if not (self._uses_standard_iteration(UV) and UV.getPosition is _UV_GET_POSITION):
            return [item.getPosition() for item in self]
        if not self._indices:
            return []
        Component._validate_shape(self._shape, UV.shape_type)
        mesh_fn = self._shape._geometry_fn()
        count = mesh_fn.numUVs()
        uv_set = mesh_fn.currentUVSetName()
        result = []
        for index in self._indices:
            Component._require_index_range(index, count)
            result.append(tuple(mesh_fn.getUV(index, uvSet=uv_set)))
        return result
