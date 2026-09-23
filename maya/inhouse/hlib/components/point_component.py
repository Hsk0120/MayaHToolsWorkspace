"""XYZ 座標を持つコンポーネントと要素群の座標操作。"""

import math

import maya.cmds as cmds

from ..decorators.undo import undoable
from .component import Component, Components


class PointComponent(Component):
    """XYZ 座標を持つ頂点または CV。座標はシーンの現在値を参照する。"""

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
        # MFnMesh.getPoint/MFnNurbsCurve.cvPosition への置き換えを検討したが、
        # 周期(periodic)カーブでは MFnNurbsCurve.numCVs が cmds の cv[] で
        # アドレス可能な数(重複ラップ分を除いた実編集可能数)より多く、
        # ラップ側のインデックスで cmds.xform の書き込みと食い違う実挙動が
        # あるため、cmds.xform のまま維持する(set_position の書き込み経路と
        # 読み取り単位・アドレッシングを一致させるため)。
        space = {"worldSpace": True} if ws else {"objectSpace": True}
        return tuple(cmds.xform(self.full_name, query=True, translation=True, **space))

    @undoable("hlibComponentPosition")
    def set_position(self, value, ws=False):
        """座標を設定する。

        Args:
            value (Iterable[float]): 現在の距離単位での有限な XYZ 座標。
            ws (bool): True はワールド、False はオブジェクト空間。

        Returns:
            PointComponent: 編集した自身。

        Raises:
            ValueError: 座標または ws が不正な場合。
        """
        if not isinstance(ws, bool):
            raise ValueError("ws must be a bool")
        value = self._finite_coordinates(value, 3)
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

    def positions(self, ws=False):
        """保持順に現在の座標を取得する。

        Args:
            ws (bool): True はワールド、False はオブジェクト空間。

        Returns:
            list[tuple[float, float, float]]: Maya の現在の距離単位での座標列。
        """
        if not isinstance(ws, bool):
            raise ValueError("ws must be a bool")
        return [component.position(ws) for component in self]

    @undoable("hlibComponentsMirror")
    def mirror(self, axis="x", ws=False, pivot=(0.0, 0.0, 0.0)):
        """保持している頂点または CV をまとめてミラーする。

        Args:
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
        points = [component.position(ws) for component in components]
        mirrored_axes = {"xyz".index(a) for a in axis}
        space = {"worldSpace": True} if ws else {"objectSpace": True}
        for component, point in zip(components, points):
            result = [2.0 * pivot[i] - value if i in mirrored_axes else value for i, value in enumerate(point)]
            cmds.xform(component.full_name, absolute=True, translation=result, **space)
        return self
