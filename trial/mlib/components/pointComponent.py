"""XYZ 座標を持つコンポーネントと要素群の座標操作。"""

from ..core import geometryEdit as geometry_edit
from ..util import _world_space
from .component import Component, Components


class PointComponent(Component):
    """Shape参照と頂点/CV番号を保持し、現在のXYZ座標を照会する。

    座標をキャッシュせず、取得ごとにMayaへ問い合わせる。XYZの距離単位はcmで、
    既定はShapeのオブジェクト空間。ワールド空間では保持ShapeのDAGパスを使う。
    CVはAPIの制御点位置を扱い、カーブ上のパラメータ位置を取得する処理ではない。
    """

    def getPosition(self, worldSpace=False):
        """頂点またはカーブCVの現在のXYZ座標をcmで取得する。

        Shapeと番号を検証してOpenMayaへ問い合わせる。UIの距離単位には換算しない。

        Args:
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。

        Returns:
            tuple[float, float, float]: 新しいXYZ値。シーン内座標への書換え可能な参照ではない。

        Raises:
            TypeError: worldSpaceがbool以外の場合。
            IndexError: 番号が現在の要素数の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが座標取得を拒否した場合。
        """
        ws = _world_space(worldSpace)
        self._require_valid()
        return geometry_edit.positions(self.shape, [self.index], ws)[0]

    def getPositionX(self, worldSpace=False):
        """X成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。

        Returns:
            float: 座標値。
        """
        return self._get_coordinate(0, worldSpace=_world_space(worldSpace))

    def getPositionY(self, worldSpace=False):
        """Y成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。

        Returns:
            float: 座標値。
        """
        return self._get_coordinate(1, worldSpace=_world_space(worldSpace))

    def getPositionZ(self, worldSpace=False):
        """Z成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。

        Returns:
            float: 座標値。
        """
        return self._get_coordinate(2, worldSpace=_world_space(worldSpace))


class PointComponents(Components):
    """同一Shapeの頂点/CV番号列を保持し、保持順にXYZ座標を照会する。

    座標値は保持せず、getPositionで現在値を取得する。XYZはcm単位。
    """

    def getPositionX(self, worldSpace=False):
        """X成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。

        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(0, worldSpace=_world_space(worldSpace))

    def getPositionY(self, worldSpace=False):
        """Y成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。

        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(1, worldSpace=_world_space(worldSpace))

    def getPositionZ(self, worldSpace=False):
        """Z成分の現在値を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、FalseはShapeのオブジェクト空間。

        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(2, worldSpace=_world_space(worldSpace))

    def getPosition(self, worldSpace=False):
        """保持番号の順に、頂点/CVの現在のXYZ座標をcmで取得する。

        UIの距離単位には換算せず、座標の取得に伴うMayaの評価が発生し得る。

        Args:
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。

        Returns:
            list[tuple[float, float, float]]: 新しい座標値のリスト。シーンを変更する参照ではない。
                空集合はShapeを再照会せず空リストを返す。

        Raises:
            TypeError: worldSpaceがbool以外の場合。空集合でも検証する。
            IndexError: 保持番号が現在の範囲外の場合。
            RuntimeError: Shapeが無効、またはMayaが座標取得を拒否した場合。
        """
        ws = _world_space(worldSpace)
        if not self._indices:
            return []
        self._require_valid()
        return geometry_edit.positions(self._shape, self._indices, ws)
