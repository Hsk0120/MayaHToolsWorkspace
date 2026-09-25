"""Maya の NURBS カーブシェイプを扱う。"""

from ..decorators._fast import fast_edit

import maya.api.OpenMaya as om2

from .._core.registry import node_wrapper
from ..components.cv import CV, CVs
from .shape import Shape


@node_wrapper("nurbsCurve")
class NurbsCurve(Shape):
    """NURBS カーブの形状情報を提供するシェイプラッパー。"""

    @fast_edit
    def mirror(self, axis="x", ws=False, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False):
        """CV の位置をミラーし、自身を更新する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            axis (str): 反転する座標軸。x、y、z、xy、xz、yz、xyz。大文字も可。
                x は pivot.x を通る YZ 平面で反転する。複数軸は同時に反転する。
            ws (bool): True はワールド軸、False はオブジェクト空間の軸。既定は False。
            pivot (Iterable[float]): 指定空間での反転中心。既定はその空間の原点。
                単位は Maya の現在の距離単位。Transform のピボットとは独立する。
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
        self.cvs(indices).mirror(axis=axis, ws=ws, pivot=pivot)
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

    def curve_fn(self):
        """カーブの関数セットを取得する。

        Returns:
            om2.MFnNurbsCurve: 保持する DAG パスの関数セット。
        """
        return om2.MFnNurbsCurve(self.dag_path())

    def num_cvs(self):
        """CV 数を取得する。

        Returns:
            int: カーブの CV 数。
        """
        return self.curve_fn().numCVs

    def num_spans(self):
        """スパン数を取得する。

        Returns:
            int: カーブのスパン数。
        """
        return self.curve_fn().numSpans

    def degree(self):
        """カーブの次数を取得する。

        Returns:
            int: NURBS カーブの次数。
        """
        return self.curve_fn().degree

    def form(self):
        """カーブの開閉形式を取得する。

        Returns:
            int: MFnNurbsCurve の kOpen、kClosed、kPeriodic のいずれか。
        """
        return self.curve_fn().form

    def length(self, tolerance=1e-6):
        """オブジェクト空間の弧長を取得する。

        Args:
            tolerance (float): 弧長計算の許容誤差。正の値を指定する。

        Returns:
            float: Maya API の内部距離単位での弧長。親のスケールは含めない。

        Raises:
            ValueError: tolerance が正の値でない場合。
        """
        if not tolerance > 0:
            raise ValueError("tolerance must be positive")
        return self.curve_fn().length(tolerance)

    def cv_positions(self, ws=False):
        """CV の位置を取得する。

        Args:
            ws (bool): True はワールド空間、False はオブジェクト空間。

        Returns:
            om2.MPointArray: CV 順の位置。距離は Maya API の内部単位。
        """
        space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
        return self.curve_fn().cvPositions(space)

    def get_collocated_cv_groups(self, tolerance=1e-6, ws=False):
        """ほぼ同じ位置にある CV をグループ化して取得する。

        周期カーブの重複 CV や、クリーンアップ前のカーブの検証などに使う。

        Args:
            tolerance (float): 同一位置とみなす距離の許容誤差（Maya API の
                内部距離単位）。正の値を指定する。
            ws (bool): True はワールド空間、False はオブジェクト空間で比較する。

        Returns:
            list[list[int]]: 2個以上の CV が重なっているグループのみを、
                各グループ内は番号昇順、グループ間は先頭番号の昇順で返す。
                重なりのない単独の CV は含まない。

        Raises:
            ValueError: tolerance が正の値でない場合。
        """
        if not tolerance > 0:
            raise ValueError("tolerance must be positive")
        positions = self.cv_positions(ws=ws)
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
