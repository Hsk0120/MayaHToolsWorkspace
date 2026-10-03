"""XYZ 座標を持つコンポーネントと要素群の座標操作。"""
from maya.api.OpenMaya import MSpace
from .._core.space import world_space

from ..decorators._fast import fast_edit
from .._core import geometryEdit as geometry_edit

import math


from ..decorators.undo import undoChunk
from .component import Component, Components


class PointComponent(Component):
    """XYZ 座標を持つ頂点または CV。座標はシーンの現在値を参照する。"""

    def getPosition(self, space=MSpace.kObject):
        """現在の座標を取得する。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            tuple[float, float, float]: cm単位の XYZ 座標。

        Raises:
            ValueError: spaceが対応するMSpace定数でない場合。
        """
        ws = world_space(space)
        if not isinstance(ws, bool):
            raise ValueError("ws must be a bool")
        self._validate()
        return geometry_edit.positions(self.shape, [self.index], ws)[0]

    @fast_edit
    @undoChunk("hlibComponentPosition")
    def setPosition(self, value, space=MSpace.kObject, *, fast=False):
        """座標を設定する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Iterable[float]): cm単位での有限な XYZ 座標。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            PointComponent: 編集した自身。

        Raises:
            ValueError: 座標またはspace が不正な場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        fastで入力履歴付き形状・周期カーブを編集するとNotImplementedError。
        """
        ws = world_space(space)
        if not isinstance(ws, bool):
            raise ValueError("ws must be a bool")
        value = self._finite_coordinates(value, 3)
        self._validate()
        geometry_edit.setPositions(self.shape, [self.index], [value], ws)
        return self

    def getX(self, space=MSpace.kObject):
        """X成分の現在値を取得する。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
        Returns:
            float: 座標値。
        """
        ws = world_space(space)
        return self._get_coordinate(0, space=space)

    @fast_edit
    def setX(self, value, space=MSpace.kObject, *, fast=False):
        """X成分だけを設定し、他の成分を維持する。

        Args:
            value (float): 有限な座標。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
        Returns:
            PointComponent: 更新した自身。
        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        ws = world_space(space)
        return self._set_coordinate(0, value, space=space)

    def getY(self, space=MSpace.kObject):
        """Y成分の現在値を取得する。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
        Returns:
            float: 座標値。
        """
        ws = world_space(space)
        return self._get_coordinate(1, space=space)

    @fast_edit
    def setY(self, value, space=MSpace.kObject, *, fast=False):
        """Y成分だけを設定し、他の成分を維持する。

        Args:
            value (float): 有限な座標。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
        Returns:
            PointComponent: 更新した自身。
        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        ws = world_space(space)
        return self._set_coordinate(1, value, space=space)

    def getZ(self, space=MSpace.kObject):
        """Z成分の現在値を取得する。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
        Returns:
            float: 座標値。
        """
        ws = world_space(space)
        return self._get_coordinate(2, space=space)

    @fast_edit
    def setZ(self, value, space=MSpace.kObject, *, fast=False):
        """Z成分だけを設定し、他の成分を維持する。

        Args:
            value (float): 有限な座標。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
        Returns:
            PointComponent: 更新した自身。
        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        ws = world_space(space)
        return self._set_coordinate(2, value, space=space)


class PointComponents(Components):
    """XYZ 座標を持つコンポーネント群。"""

    @fast_edit
    def setPosition(self, value, space=MSpace.kObject, *, fast=False):
        """全要素を同じ座標へ設定する。要素別にはsetPositionsを使う。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Iterable[float]): 有限のXYZ座標。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
        Returns:
            PointComponents: 自身。全要素が同じ位置に集まる。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        fastで入力履歴付き形状・周期カーブを編集するとNotImplementedError。
        """
        ws = world_space(space)
        point = Component._finite_coordinates(value, 3)
        return self.setPositions([point] * len(self), space=MSpace.kWorld if ws else MSpace.kObject)

    @fast_edit
    @undoChunk("hlibComponentsSetPositions")
    def setPositions(self, values, space=MSpace.kObject, *, fast=False):
        """保持順の座標列を設定する。全件の座標・対象を検証してから書き込む。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            values (Iterable[Iterable[float]]): 要素数と同じ数のXYZ座標。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
        Returns:
            PointComponents: 自身。空集合と空座標列は何もしない。
        Raises:
            ValueError: 件数・座標・spaceが不正な場合。
            RuntimeError: Mayaが編集を拒否した場合。完了済み変更は自動で戻さない。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        fastで入力履歴付き形状・周期カーブを編集するとNotImplementedError。
        """
        ws = world_space(space)
        if not isinstance(ws, bool):
            raise ValueError("ws must be a bool")
        rows = self._coordinate_rows(values, 3)
        if not self._indices:
            return self
        self._validate()
        geometry_edit.setPositions(self._shape, self._indices, rows, ws)
        return self

    def getX(self, space=MSpace.kObject):
        """X成分の現在値を取得する。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
        Returns:
            list[float]: 保持順の座標値。
        """
        ws = world_space(space)
        return self._get_coordinate(0, space=space)

    @fast_edit
    def setX(self, value, space=MSpace.kObject, *, fast=False):
        """X成分だけを設定し、他の成分を維持する。

        Args:
            value (float | Iterable[float]): 同値スカラーまたは保持順の値列。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
        Returns:
            PointComponents: 更新した自身。
        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        ws = world_space(space)
        return self._set_coordinate(0, value, space=space)

    def getY(self, space=MSpace.kObject):
        """Y成分の現在値を取得する。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
        Returns:
            list[float]: 保持順の座標値。
        """
        ws = world_space(space)
        return self._get_coordinate(1, space=space)

    @fast_edit
    def setY(self, value, space=MSpace.kObject, *, fast=False):
        """Y成分だけを設定し、他の成分を維持する。

        Args:
            value (float | Iterable[float]): 同値スカラーまたは保持順の値列。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
        Returns:
            PointComponents: 更新した自身。
        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        ws = world_space(space)
        return self._set_coordinate(1, value, space=space)

    def getZ(self, space=MSpace.kObject):
        """Z成分の現在値を取得する。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
        Returns:
            list[float]: 保持順の座標値。
        """
        ws = world_space(space)
        return self._get_coordinate(2, space=space)

    @fast_edit
    def setZ(self, value, space=MSpace.kObject, *, fast=False):
        """Z成分だけを設定し、他の成分を維持する。

        Args:
            value (float | Iterable[float]): 同値スカラーまたは保持順の値列。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
        Returns:
            PointComponents: 更新した自身。
        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        ws = world_space(space)
        return self._set_coordinate(2, value, space=space)

    def getPosition(self, space=MSpace.kObject):
        """保持順に現在の座標を取得する。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            list[tuple[float, float, float]]: cm単位の座標列。

        Raises:
            ValueError: spaceが対応するMSpace定数でない場合。
        """
        ws = world_space(space)
        if not isinstance(ws, bool):
            raise ValueError("ws must be a bool")
        if not self._indices:
            return []
        self._validate()
        return geometry_edit.positions(self._shape, self._indices, ws)

    @fast_edit
    @undoChunk("hlibComponentsMirror")
    def mirror(self, axis="x", space=MSpace.kObject, pivot=(0.0, 0.0, 0.0), *, fast=False):
        """保持している頂点または CV をまとめてミラーする。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            axis (str): x、y、z または重複のない組み合わせ。大文字も可。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
            pivot (Iterable[float]): 選択空間の反転中心。cm単位。既定は原点。

        Returns:
            PointComponents: 編集したコレクション自身。

        Raises:
            ValueError: 軸・空間・中心が不正、またはワールド変換がほぼ特異な場合。
            IndexError: トポロジー変更などで保持番号が範囲外になった場合。
            RuntimeError: シェイプが無効、または Maya が編集を拒否した場合。

        1回の Undo で戻せる。全座標を読んでから書き込むが、書き込み途中の失敗を
        自動ロールバックしない。複製・結合・法線反転は行わず、共有形状の編集は
        全インスタンスに影響する。周期 CV は Maya の連動規則に従う。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        fastで入力履歴付き形状・周期カーブを編集するとNotImplementedError。
        """
        ws = world_space(space)
        if not isinstance(axis, str) or not axis or any(a not in "xyz" for a in axis.lower()):
            raise ValueError("axis must contain x, y, or z")
        axis = axis.lower()
        if len(set(axis)) != len(axis):
            raise ValueError("axis must not contain duplicates")
        if not isinstance(ws, bool):
            raise ValueError("ws must be a bool")
        try:
            pivot = tuple(float(value) for value in pivot)
        except (TypeError, ValueError) as error:
            raise ValueError("pivot must contain three finite numbers") from error
        if len(pivot) != 3 or not all(math.isfinite(value) for value in pivot):
            raise ValueError("pivot must contain three finite numbers")
        components = list(self)
        if not components:
            return self
        if ws:
            matrix = self._shape.dagPath().inclusiveMatrix()
            # Maya はゼロスケールを微小値へ置換するため行列の大きさも考慮する。
            magnitude = max(1.0, *(sum(abs(matrix[row * 4 + col]) for col in range(3)) for row in range(3)))
            if abs(matrix.det4x4()) <= 1e-12 * magnitude ** 3:
                raise ValueError("Cannot mirror in world space with a near-singular transform")
        points = self.getPosition(MSpace.kWorld if ws else MSpace.kObject)
        mirrored_axes = {"xyz".index(a) for a in axis}
        rows = [[2.0 * pivot[i] - value if i in mirrored_axes else value for i, value in enumerate(point)] for point in points]
        self.setPositions(rows, space=MSpace.kWorld if ws else MSpace.kObject)
        return self
