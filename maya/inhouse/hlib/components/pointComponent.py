"""XYZ 座標を持つコンポーネントと要素群の座標操作。"""

from ..decorators._fast import fast_edit, is_fast
from .._core import fastGeometry as fast_geometry

import math

import maya.cmds as cmds

from ..decorators.undo import undo_chunk
from .component import Component, Components


class PointComponent(Component):
    """XYZ 座標を持つ頂点または CV。座標はシーンの現在値を参照する。"""

    def get_position(self, ws=False):
        """現在の座標を取得する。

        Args:
            ws (bool): True はワールド、False はオブジェクト空間。

        Returns:
            tuple[float, float, float]: Maya の現在の距離単位による XYZ 座標。

        Raises:
            ValueError: ws が bool でない場合。
        """
        if not isinstance(ws, bool):
            raise ValueError("ws must be a bool")
        if is_fast():
            self._validate()
            return fast_geometry.positions(self.shape, [self.index], ws)[0]
        # MFnMesh.getPoint/MFnNurbsCurve.cvPosition への置き換えを検討したが、
        # 周期(periodic)カーブでは MFnNurbsCurve.numCVs が cmds の cv[] で
        # アドレス可能な数(重複ラップ分を除いた実編集可能数)より多く、
        # ラップ側のインデックスで cmds.xform の書き込みと食い違う実挙動が
        # あるため、cmds.xform のまま維持する(set_position の書き込み経路と
        # 読み取り単位・アドレッシングを一致させるため)。
        space = {"worldSpace": True} if ws else {"objectSpace": True}
        return tuple(cmds.xform(self.full_name(), query=True, translation=True, **space))

    @fast_edit
    @undo_chunk("hlibComponentPosition")
    def set_position(self, value, ws=False, *, fast=False):
        """座標を設定する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Iterable[float]): 現在の距離単位での有限な XYZ 座標。
            ws (bool): True はワールド、False はオブジェクト空間。

        Returns:
            PointComponent: 編集した自身。

        Raises:
            ValueError: 座標または ws が不正な場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        fastで入力履歴付き形状・周期カーブを編集するとNotImplementedError。
        """
        if not isinstance(ws, bool):
            raise ValueError("ws must be a bool")
        value = self._finite_coordinates(value, 3)
        if is_fast():
            self._validate()
            fast_geometry.set_positions(self.shape, [self.index], [value], ws)
            return self
        space = {"worldSpace": True} if ws else {"objectSpace": True}
        cmds.xform(self.full_name(), absolute=True, translation=value, **space)
        return self

    def get_x(self, ws=False):
        """X成分の現在値を取得する。

        Args:
            ws (bool): Trueはワールド、Falseはオブジェクト空間。距離は現在のUI単位。
        Returns:
            float: 座標値。
        """
        return self._get_coordinate(0, ws=ws)

    @fast_edit
    def set_x(self, value, ws=False, *, fast=False):
        """X成分だけを設定し、他の成分を維持する。

        Args:
            value (float): 有限な座標。
            ws (bool): Trueはワールド、Falseはオブジェクト空間。距離は現在のUI単位。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
        Returns:
            PointComponent: 更新した自身。
        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        return self._set_coordinate(0, value, ws=ws)

    def get_y(self, ws=False):
        """Y成分の現在値を取得する。

        Args:
            ws (bool): Trueはワールド、Falseはオブジェクト空間。距離は現在のUI単位。
        Returns:
            float: 座標値。
        """
        return self._get_coordinate(1, ws=ws)

    @fast_edit
    def set_y(self, value, ws=False, *, fast=False):
        """Y成分だけを設定し、他の成分を維持する。

        Args:
            value (float): 有限な座標。
            ws (bool): Trueはワールド、Falseはオブジェクト空間。距離は現在のUI単位。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
        Returns:
            PointComponent: 更新した自身。
        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        return self._set_coordinate(1, value, ws=ws)

    def get_z(self, ws=False):
        """Z成分の現在値を取得する。

        Args:
            ws (bool): Trueはワールド、Falseはオブジェクト空間。距離は現在のUI単位。
        Returns:
            float: 座標値。
        """
        return self._get_coordinate(2, ws=ws)

    @fast_edit
    def set_z(self, value, ws=False, *, fast=False):
        """Z成分だけを設定し、他の成分を維持する。

        Args:
            value (float): 有限な座標。
            ws (bool): Trueはワールド、Falseはオブジェクト空間。距離は現在のUI単位。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
        Returns:
            PointComponent: 更新した自身。
        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        return self._set_coordinate(2, value, ws=ws)


class PointComponents(Components):
    """XYZ 座標を持つコンポーネント群。"""

    @fast_edit
    def set_position(self, value, ws=False, *, fast=False):
        """全要素を同じ座標へ設定する。要素別にはset_positionsを使う。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Iterable[float]): 有限のXYZ座標。
            ws (bool): Trueはワールド、Falseはオブジェクト空間。
        Returns:
            PointComponents: 自身。全要素が同じ位置に集まる。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        fastで入力履歴付き形状・周期カーブを編集するとNotImplementedError。
        """
        point = Component._finite_coordinates(value, 3)
        return self.set_positions([point] * len(self), ws=ws)

    @fast_edit
    @undo_chunk("hlibComponentsSetPositions")
    def set_positions(self, values, ws=False, *, fast=False):
        """保持順の座標列を設定する。全件の座標・対象を検証してから書き込む。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            values (Iterable[Iterable[float]]): 要素数と同じ数のXYZ座標。
            ws (bool): Trueはワールド、Falseはオブジェクト空間。
        Returns:
            PointComponents: 自身。空集合と空座標列は何もしない。
        Raises:
            ValueError: 件数・座標・wsが不正な場合。
            RuntimeError: Mayaが編集を拒否した場合。完了済み変更は自動で戻さない。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        fastで入力履歴付き形状・周期カーブを編集するとNotImplementedError。
        """
        if not isinstance(ws, bool):
            raise ValueError("ws must be a bool")
        rows = self._coordinate_rows(values, 3)
        components = list(self)
        if is_fast():
            fast_geometry.set_positions(self._shape, [c.index for c in components], rows, ws)
            return self
        for component, point in zip(components, rows):
            component.set_position(point, ws=ws)
        return self

    def get_x(self, ws=False):
        """X成分の現在値を取得する。

        Args:
            ws (bool): Trueはワールド、Falseはオブジェクト空間。距離は現在のUI単位。
        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(0, ws=ws)

    @fast_edit
    def set_x(self, value, ws=False, *, fast=False):
        """X成分だけを設定し、他の成分を維持する。

        Args:
            value (float | Iterable[float]): 同値スカラーまたは保持順の値列。
            ws (bool): Trueはワールド、Falseはオブジェクト空間。距離は現在のUI単位。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
        Returns:
            PointComponents: 更新した自身。
        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        return self._set_coordinate(0, value, ws=ws)

    def get_y(self, ws=False):
        """Y成分の現在値を取得する。

        Args:
            ws (bool): Trueはワールド、Falseはオブジェクト空間。距離は現在のUI単位。
        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(1, ws=ws)

    @fast_edit
    def set_y(self, value, ws=False, *, fast=False):
        """Y成分だけを設定し、他の成分を維持する。

        Args:
            value (float | Iterable[float]): 同値スカラーまたは保持順の値列。
            ws (bool): Trueはワールド、Falseはオブジェクト空間。距離は現在のUI単位。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
        Returns:
            PointComponents: 更新した自身。
        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        return self._set_coordinate(1, value, ws=ws)

    def get_z(self, ws=False):
        """Z成分の現在値を取得する。

        Args:
            ws (bool): Trueはワールド、Falseはオブジェクト空間。距離は現在のUI単位。
        Returns:
            list[float]: 保持順の座標値。
        """
        return self._get_coordinate(2, ws=ws)

    @fast_edit
    def set_z(self, value, ws=False, *, fast=False):
        """Z成分だけを設定し、他の成分を維持する。

        Args:
            value (float | Iterable[float]): 同値スカラーまたは保持順の値列。
            ws (bool): Trueはワールド、Falseはオブジェクト空間。距離は現在のUI単位。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
        Returns:
            PointComponents: 更新した自身。
        Raises:
            ValueError: 座標・空間指定または要素数が不正な場合。
            TypeError: fastがboolでない場合。
            RuntimeError: 対象が無効、またはMayaが更新を拒否した場合。
            NotImplementedError: fast更新で未対応の形状の場合。
        """
        return self._set_coordinate(2, value, ws=ws)

    def get_position(self, ws=False):
        """保持順に現在の座標を取得する。

        Args:
            ws (bool): True はワールド、False はオブジェクト空間。

        Returns:
            list[tuple[float, float, float]]: Maya の現在の距離単位での座標列。

        Raises:
            ValueError: ws が bool でない場合。
        """
        if not isinstance(ws, bool):
            raise ValueError("ws must be a bool")
        if is_fast():
            return fast_geometry.positions(self._shape, [c.index for c in self], ws)
        return [component.get_position(ws) for component in self]

    @fast_edit
    @undo_chunk("hlibComponentsMirror")
    def mirror(self, axis="x", ws=False, pivot=(0.0, 0.0, 0.0), *, fast=False):
        """保持している頂点または CV をまとめてミラーする。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            axis (str): x、y、z または重複のない組み合わせ。大文字も可。
            ws (bool): True はワールド、False はオブジェクト空間。
            pivot (Iterable[float]): 選択空間の反転中心。現在の距離単位。既定は原点。

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
            matrix = self._shape.dag_path().inclusiveMatrix()
            # Maya はゼロスケールを微小値へ置換するため行列の大きさも考慮する。
            magnitude = max(1.0, *(sum(abs(matrix[row * 4 + col]) for col in range(3)) for row in range(3)))
            if abs(matrix.det4x4()) <= 1e-12 * magnitude ** 3:
                raise ValueError("Cannot mirror in world space with a near-singular transform")
        points = self.get_position(ws)
        mirrored_axes = {"xyz".index(a) for a in axis}
        rows = [[2.0 * pivot[i] - value if i in mirrored_axes else value for i, value in enumerate(point)] for point in points]
        self.set_positions(rows, ws=ws)
        return self
