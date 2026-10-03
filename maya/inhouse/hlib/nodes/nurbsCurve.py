"""Maya の NURBS カーブシェイプを扱う。"""
from maya.api.OpenMaya import MSpace
from .._core.space import world_space

from ..decorators._fast import fast_edit

import math
import maya.api.OpenMaya as om2

from .._core.registry import node_wrapper
from ..components.cv import CV, CVs
from .shape import Shape


@node_wrapper("nurbsCurve")
class NurbsCurve(Shape):
    """NURBS カーブの形状情報を提供するシェイプラッパー。"""

    @fast_edit
    def mirror(self, axis="x", space=MSpace.kObject, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False):
        """CV の位置をミラーし、自身を更新する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            axis (str): 反転する座標軸。x、y、z、xy、xz、yz、xyz。大文字も可。
                x は pivot.x を通る YZ 平面で反転する。複数軸は同時に反転する。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
            pivot (Iterable[float]): 指定空間での反転中心。既定はその空間の原点。
                単位は 内部距離単位cm。Transform のピボットとは独立する。
            indices (Iterable[int] | None): CV 番号。None は全 CV、空列は変更なし。
                重複は1回だけ処理し、負の番号は許容しない。

        Returns:
            NurbsCurve: 編集した自身。

        Raises:
            ValueError: 軸・空間・中心が不正、またはワールド変換が数値的にほぼ特異な場合。
            TypeError: CV 番号が整数でない場合。
            IndexError: CV 番号が範囲外の場合。
            RuntimeError: Maya が形状の取得・編集を拒否した場合。

        CV 座標だけを編集し、Transform、次数、ノット、CV 順序を維持する。
        カーブの複製やパラメータ方向の反転は行わない。1回の Undo で戻せる。
        周期カーブの重複 CV は Maya の連動規則に従う。
        インスタンス形状はデータを共有する全インスタンスへ影響する。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        fastで入力履歴付き形状・周期カーブを編集するとNotImplementedError。
        """
        ws = world_space(space)
        self.cvs(indices).mirror(axis=axis, space=MSpace.kWorld if ws else MSpace.kObject, pivot=pivot)
        return self

    def cv(self, index):
        """CV 番号から単体ラッパーを取得する。

        Args:
            index (int): ゼロ始まりの CV 番号。

        Returns:
            CV: シーン上の CV を参照するラッパー。

        Raises:
            IndexError: CV 番号が範囲外の場合。
        """
        return CV(self, index)

    def cvs(self, indices=None):
        """指定した CV 群を取得する。

        Args:
            indices (Iterable[int] | None): CV 番号。None は現在の全 CV。

        Returns:
            CVs: 番号順を維持し、重複を除いたコレクション。
        """
        return CVs(self, indices)

    def curveFn(self):
        """カーブの関数セットを取得する。

        Returns:
            om2.MFnNurbsCurve: 保持する DAG パスの関数セット。
        """
        return om2.MFnNurbsCurve(self.dagPath())

    def numCVs(self):
        """CV 数を取得する。

        Returns:
            int: カーブの CV 数。
        """
        return self.curveFn().numCVs

    def numSpans(self):
        """スパン数を取得する。

        Returns:
            int: カーブのスパン数。
        """
        return self.curveFn().numSpans

    def degree(self):
        """カーブの次数を取得する。

        Returns:
            int: NURBS カーブの次数。
        """
        return self.curveFn().degree

    def form(self):
        """カーブの開閉形式を取得する。

        Returns:
            int: MFnNurbsCurve の kOpen、kClosed、kPeriodic のいずれか。
        """
        return self.curveFn().form

    def length(self, tolerance=1e-6, *, space=MSpace.kObject, unit="cm"):
        """指定空間のカーブ長を取得する。シーンに計算ノードを作成しない。

        Args:
            tolerance (float): 弧長計算の許容誤差。内部距離単位で正の有限値。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。
            unit (str | None): 出力単位。既定はcm。Noneは現在の距離UI単位。
                mm/cm/m/km/in/ft/yd/mi、またはMayaの長名。

        Returns:
            float: 指定単位での弧長。単位省略時はcm。
                space=MSpace.kWorldは親の非均等スケール・シアーとインスタンスの変換を含む。

        Raises:
            ValueError: toleranceが正の有限値でない、または単位名が未対応の場合。
            TypeError: spaceが対応するMSpace定数でない、または単位の型が不正な場合。
            RuntimeError: 無効なカーブ、またはMayaが評価を拒否した場合。
        """
        ws = world_space(space)
        from ..utils import units
        # 単位は毎回照会する。係数を使うためシーンの単位設定は変更しない。
        factor = units.convertDistance(1.0, from_unit="cm", to_unit=unit)
        tolerance = float(tolerance)
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("tolerance must be positive and finite")
        if type(ws) is not bool:
            raise TypeError("ws must be a bool")
        if not ws:
            return self.curveFn().length(tolerance) * factor
        # lengthはオブジェクト空間で計算するため、メモリ内のコピーだけを
        # ワールド座標へ変換する。元のCV・履歴・Undoキューは変更しない。
        # copyにより次数・ノット・有理カーブのウェイトも維持する。
        source = self.curveFn()
        data = om2.MFnNurbsCurveData().create()
        copied = om2.MFnNurbsCurve().copy(source.object(), data)
        curve = om2.MFnNurbsCurve(copied)
        curve.setCVPositions(source.cvPositions(om2.MSpace.kWorld))
        curve.updateCurve()
        return curve.length(tolerance) * factor

    def cvPositions(self, space=MSpace.kObject):
        """CV の位置を取得する。

        Args:
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            om2.MPointArray: CV 順の位置。距離は Maya API の内部単位。
        """
        ws = world_space(space)
        space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
        return self.curveFn().cvPositions(space)

    def getCollocatedCVGroups(self, tolerance=1e-6, space=MSpace.kObject):
        """ほぼ同じ位置にある CV をグループ化して取得する。

        周期カーブの重複 CV や、クリーンアップ前のカーブの検証などに使う。

        Args:
            tolerance (float): 同一位置とみなす距離の許容誤差（Maya API の
                内部距離単位）。正の値を指定する。
            space (int): MSpace.kObject/kTransformはローカル、kWorldはワールド空間。

        Returns:
            list[list[int]]: 2個以上の CV が重なっているグループのみを、
                各グループ内は番号昇順、グループ間は先頭番号の昇順で返す。
                重なりのない単独の CV は含まない。

        Raises:
            ValueError: tolerance が正の値でない場合。
        """
        ws = world_space(space)
        if not tolerance > 0:
            raise ValueError("tolerance must be positive")
        positions = self.cvPositions(space=MSpace.kWorld if ws else MSpace.kObject)
        assigned = [False] * len(positions)
        groups = []
        for i in range(len(positions)):
            if assigned[i]:
                continue
            group = [i]
            for j in range(i + 1, len(positions)):
                if not assigned[j] and positions[i].distanceTo(positions[j]) <= tolerance:
                    group.append(j)
                    assigned[j] = True
            if len(group) > 1:
                assigned[i] = True
                groups.append(group)
        return groups
