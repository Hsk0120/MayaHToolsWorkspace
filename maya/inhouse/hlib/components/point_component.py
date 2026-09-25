"""XYZ 座標を持つコンポーネントと要素群の座標操作。"""

from ..decorators._fast import fast_edit, is_fast
from .._core import fast_geometry

import math

import maya.cmds as cmds

from ..decorators.undo import undo_chunk
from .component import Component, Components


class PointComponent(Component):
    """XYZ 座標を持つ頂点または CV。座標はシーンの現在値を参照する。"""

    def get_position(self, ws=False):
        """tuple[float, float, float]: position(ws)と同じ。wsはワールド空間指定。"""
        return self.position(ws=ws)

    def position(self, ws=False):
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
        return tuple(cmds.xform(self.full_name, query=True, translation=True, **space))

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
        cmds.xform(self.full_name, absolute=True, translation=value, **space)
        return self

    @property
    def x(self):
        """オブジェクト空間の X 座標。

        Returns:
            float: Maya の現在の距離単位による座標。
        """
        return self.position()[0]

    @x.setter
    def x(self, value):
        """X 座標だけを更新する。

        Args:
            value (float): 現在の距離単位での座標。

        Returns:
            None: 値を返さない。
        """
        position = list(self.position())
        position[0] = value
        self.set_position(position)

    @property
    def y(self):
        """オブジェクト空間の Y 座標。

        Returns:
            float: Maya の現在の距離単位による座標。
        """
        return self.position()[1]

    @y.setter
    def y(self, value):
        """Y 座標だけを更新する。

        Args:
            value (float): 現在の距離単位での座標。

        Returns:
            None: 値を返さない。
        """
        position = list(self.position())
        position[1] = value
        self.set_position(position)

    @property
    def z(self):
        """オブジェクト空間の Z 座標。

        Returns:
            float: Maya の現在の距離単位による座標。
        """
        return self.position()[2]

    @z.setter
    def z(self, value):
        """Z 座標だけを更新する。

        Args:
            value (float): 現在の距離単位での座標。

        Returns:
            None: 値を返さない。
        """
        position = list(self.position())
        position[2] = value
        self.set_position(position)


class PointComponents(Components):
    """XYZ 座標を持つコンポーネント群。"""

    def get_position(self, ws=False):
        """list[tuple[float, float, float]]: 保持順の座標列。wsはワールド空間指定。"""
        return self.positions(ws=ws)

    def position(self, ws=False):
        """list[tuple[float, float, float]]: 単体と同名の座標取得。平均位置ではない。"""
        return self.positions(ws=ws)

    def get_positions(self, ws=False):
        """list[tuple[float, float, float]]: positions(ws)と同じ。"""
        return self.positions(ws=ws)

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

    @property
    def x(self):
        """list[float]: 保持順のオブジェクト空間X座標。"""
        return [p[0] for p in self.positions()]

    @x.setter
    def x(self, value):
        """Xだけを更新する。スカラーは全要素、数値列は保持順へ適用する。"""
        self.set_positions(self._axis_rows(self.positions(), 0, value))

    @property
    def y(self):
        """list[float]: 保持順のオブジェクト空間Y座標。"""
        return [p[1] for p in self.positions()]

    @y.setter
    def y(self, value):
        """Yだけを更新する。スカラーは全要素、数値列は保持順へ適用する。"""
        self.set_positions(self._axis_rows(self.positions(), 1, value))

    @property
    def z(self):
        """list[float]: 保持順のオブジェクト空間Z座標。"""
        return [p[2] for p in self.positions()]

    @z.setter
    def z(self, value):
        """Zだけを更新する。スカラーは全要素、数値列は保持順へ適用する。"""
        self.set_positions(self._axis_rows(self.positions(), 2, value))

    def positions(self, ws=False):
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
        return [component.position(ws) for component in self]

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
        points = self.positions(ws)
        mirrored_axes = {"xyz".index(a) for a in axis}
        rows = [[2.0 * pivot[i] - value if i in mirrored_axes else value for i, value in enumerate(point)] for point in points]
        self.set_positions(rows, ws=ws)
        return self
