"""Maya の NURBS カーブシェイプを扱う。"""

import math

import maya.api.OpenMaya as om2
from maya.api.OpenMaya import MSpace

from ..components.cv import CV, CVs
from ..util import _world_space
from ..util import _ArgumentError, _UNSET
from .shape import Shape


class NurbsCurve(Shape):
    """NURBS カーブの形状情報を提供するシェイプラッパー。"""

    def mirror(self, axis="x", worldSpace=_UNSET, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False, ws=_UNSET):
        """CV座標を反転する。Transform・次数・ノット・CV順序・wは保持する。

        周期カーブの通常更新は、API末尾の重複CVを対応する独立CVへ写し、Mayaの連動規則に従う。
        共有Shapeの全インスタンスへ影響し、複製やパラメータ方向の反転は行わない。

        Args:
            axis (str): 重複しないx/y/zの組合せ。大文字も可。
            worldSpace (bool): Trueは保持パスのworld、既定FalseはShapeのobject空間。短縮名ws。
            pivot (Iterable[float]): 指定空間の反転中心XYZ（cm）。既定は原点で、Transformのピボットとは独立。
            indices (Iterable[int] | None): OpenMayaのCV番号。Noneは全CV、空列は変更なし。重複は1回だけ処理する。
            fast (bool): TrueはUndoなし。既定FalseはUndo有効時に1回で戻せる通常更新。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            NurbsCurve: 自身。

        Raises:
            ValueError: 軸・空間・中心が不正、またはworld変換が数値的にほぼ特異な場合。
            TypeError: 番号型・fastが不正、または長短名を同時指定した場合。
            IndexError: CV番号が負または範囲外の場合。
            RuntimeError: Mayaが形状の取得・更新を拒否した場合。
            NotImplementedError: fastで入力履歴付きShapeまたは周期カーブを編集する場合。

        Note:
            途中失敗で完了済みの変更は自動で戻さない。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        ws = _world_space(worldSpace)
        self.getCVs(indices).mirror(axis=axis, ws=ws, pivot=pivot, fast=fast)
        return self

    def getCV(self, index=_UNSET, *, idx=_UNSET):
        """CV 番号から単体ラッパーを取得する。

        Args:
            index (int): ゼロ始まりの CV 番号。 別名 ``idx`` も使用可能。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            CV: シーン上の CV を参照するラッパー。

        Raises:
            IndexError: CV 番号が範囲外の場合。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
        return CV(self, index)

    def getCVs(self, indices=None):
        """OpenMayaのCV番号を入力の初出順に保持するコレクションを取得する。

        Args:
            indices (Iterable[int] | None): APIのCV番号。Noneは現在の全CVを昇順で取得し、空列は空集合。
                負数とboolは拒否する。

        Returns:
            CVs: 同じShapeを共有し、重複を除いた新しいコレクション。
                周期末尾の重複CVもAPI番号で保持するが、cmds用の名前では対応する独立CVへ写す。
        """
        return CVs(self, indices)

    def mfn(self):
        """このカーブで最も具体的な om2 function set を、呼び出すたびに新しく作って返す。

        形状データを持つ場合は ``om2.MFnNurbsCurve``。``mlib.createNode("nurbsCurve")`` 直後のように形状データを
        持たない空のシェイプは ``om2.MFnNurbsCurve`` が使えない(Maya 2027 では作成時に ValueError、
        版により作成後の照会で RuntimeError)ため、``om2.MFnDagNode`` を返す。DagNode 共通の照会
        (中間オブジェクト判定・親の列挙等)は空のシェイプでも使える。

        Returns:
            om2.MFnNurbsCurve | om2.MFnDagNode: このカーブの function set。空のシェイプでは MFnDagNode。

        Raises:
            RuntimeError: 保持する DAG パスが無効な場合。
        """
        path = self.mpath()
        try:
            fn = om2.MFnNurbsCurve(path)
            # 版により作成は通り照会で失敗するため、形状データの有無を作成直後に確かめる。
            fn.typeId
        except (RuntimeError, ValueError):
            return om2.MFnDagNode(path)
        return fn

    def getNumCVs(self):
        """CV 数を取得する。

        Returns:
            int: カーブの CV 数。
        """
        return self._geometry_fn().numCVs

    def getNumSpans(self):
        """スパン数を取得する。

        Returns:
            int: カーブのスパン数。
        """
        return self._geometry_fn().numSpans

    def getDegree(self):
        """カーブの次数を取得する。

        Returns:
            int: NURBS カーブの次数。
        """
        return self._geometry_fn().degree

    def getForm(self):
        """カーブの開閉形式を取得する。

        Returns:
            int: MFnNurbsCurve の kOpen、kClosed、kPeriodic のいずれか。
        """
        return self._geometry_fn().form

    def getLength(self, tolerance=1e-6, *, worldSpace=_UNSET, unit="cm", ws=_UNSET):
        """指定空間のカーブ長を取得する。シーンに計算ノードを作成しない。

        Args:
            tolerance (float): 弧長計算の許容誤差。内部距離単位で正の有限値。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            unit (str | None): 出力単位。既定はcm。Noneは現在の距離UI単位。
                mm/cm/m/km/in/ft/yd/mi、またはMayaの長名。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            float: 指定単位での弧長。単位省略時はcm。
                ws=Trueは親の非均等スケール・シアーとインスタンスの変換を含む。

        Raises:
            ValueError: toleranceが正の有限値でない、worldSpaceがboolでない、または単位名が未対応の場合。
            TypeError: 単位の型が不正な場合。
            RuntimeError: 無効なカーブ、またはMayaが評価を拒否した場合。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        ws = _world_space(worldSpace)
        from ..common import units
        # 単位は毎回照会する。係数を使うためシーンの単位設定は変更しない。
        factor = units.convertDistance(1.0, fromUnit="cm", toUnit=unit)
        tolerance = float(tolerance)
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("tolerance must be positive and finite")
        if type(ws) is not bool:
            raise TypeError("ws must be a bool")
        if not ws:
            return self._geometry_fn().length(tolerance) * factor
        # lengthはオブジェクト空間で計算するため、メモリ内のコピーだけを
        # ワールド座標へ変換する。元のCV・履歴・Undoキューは変更しない。
        # copyにより次数・ノット・有理カーブのウェイトも維持する。
        source = self._geometry_fn()
        data = om2.MFnNurbsCurveData().create()
        copied = om2.MFnNurbsCurve().copy(source.object(), data)
        curve = om2.MFnNurbsCurve(copied)
        curve.setCVPositions(source.cvPositions(om2.MSpace.kWorld))
        curve.updateCurve()
        return curve.length(tolerance) * factor

    def getCvPositions(self, worldSpace=_UNSET, *, ws=_UNSET):
        """CV の位置を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            om2.MPointArray: CV 順の位置。距離は Maya API の内部単位。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        ws = _world_space(worldSpace)
        space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
        return self._geometry_fn().cvPositions(space)

    def getCollocatedCVGroups(self, tolerance=1e-6, worldSpace=_UNSET, *, ws=_UNSET):
        """ほぼ同じ位置にある CV をグループ化して取得する。

        周期カーブの重複 CV や、クリーンアップ前のカーブの検証などに使う。

        Args:
            tolerance (float): 同一位置とみなす距離の許容誤差（Maya API の
                内部距離単位）。正の値を指定する。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。短縮名ws。
            ws (bool): worldSpaceの別名。同時指定は不可。

        Returns:
            list[list[int]]: 2個以上の CV が重なっているグループのみを、
                各グループ内は番号昇順、グループ間は先頭番号の昇順で返す。
                重なりのない単独の CV は含まない。

        Raises:
            ValueError: tolerance が正の値でない場合。
        """
        if ws is not _UNSET:
            if worldSpace is not _UNSET:
                raise _ArgumentError("Specify only one of 'worldSpace' and 'ws'")
            worldSpace = ws
        if worldSpace is _UNSET:
            worldSpace = False
        ws = _world_space(worldSpace)
        if not tolerance > 0:
            raise ValueError("tolerance must be positive")
        positions = self.getCvPositions(ws=ws)
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

    def _geometry_fn(self):
        """形状データを要する照会用に ``om2.MFnNurbsCurve`` を返す。

        Returns:
            om2.MFnNurbsCurve: このカーブの function set。

        Raises:
            RuntimeError: 保持する DAG パスが無効、または形状データを持たない空のシェイプの場合。
        """
        fn = self.mfn()
        if not isinstance(fn, om2.MFnNurbsCurve):
            raise RuntimeError("nurbsCurve has no geometry data: %s" % self.getFullName())
        return fn
