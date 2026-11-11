"""Maya の NURBS カーブシェイプを扱う。"""

import math
import numbers

import maya.api.OpenMaya as om2
from maya.api.OpenMaya import MSpace

from ..components.cv import CV, CVs
from ..components.pointComponent import _mirror_plan, _write_points
from ..core import geometryEdit as geometry_edit
from ..decorator import _edit_context, _pick_alias, _require_bool
from ..maths.matrix import Matrix
from ..maths.vector import Vector, _vectors_of_points
from ..util import _UNSET, _finite, _world_space
from .shape import Shape

#: aimAxis・upAxis の名前と (軸番号, 符号)。
_AXES = {"x": (0, 1.0), "y": (1, 1.0), "z": (2, 1.0), "-x": (0, -1.0), "-y": (1, -1.0), "-z": (2, -1.0)}
#: 方向を定義できないとみなすベクトルの長さ。
_DEGENERATE = 1e-10
#: 平行移動で向きを運ぶときの、全長あたりの最少の分割数。
_TRANSPORT_STEPS = 128


class _OwnedCurve(om2.MFnNurbsCurve):
    """メモリ内の形状データ(``data``)を保持する ``om2.MFnNurbsCurve``。"""


def _require_count(value):
    """点の数を検証する。

    Args:
        value (int): 点の数。boolは受け付けない。

    Returns:
        int: 検証済みの点の数。

    Raises:
        TypeError: int以外(boolを含む)の場合。
        ValueError: 1未満の場合。
    """
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise TypeError("count must be an int")
    value = int(value)
    if value < 1:
        raise ValueError(f"count must be positive: {value}")
    return value


def _require_axis(value, name):
    """軸の名前を検証する。

    Args:
        value (str): "x"・"y"・"z"・"-x"・"-y"・"-z" のいずれか。
        name (str): 例外メッセージに使う引数名。

    Returns:
        tuple[int, float]: 軸番号(0〜2)と符号。

    Raises:
        TypeError: str以外の場合。
        ValueError: 未対応の名前の場合。
    """
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str")
    try:
        return _AXES[value]
    except KeyError:
        raise ValueError(f"{name} must be one of x, y, z, -x, -y, -z: {value!r}") from None


def _perpendicular(vector, aim):
    """vector から aim 方向の成分を除いて正規化する。

    Args:
        vector (om2.MVector): 元の方向。
        aim (om2.MVector): 正規化済みの基準方向。

    Returns:
        om2.MVector | None: aim に直交する単位ベクトル。平行で定義できない場合は None。
    """
    result = vector - aim * (vector * aim)
    length = result.length()
    if length < _DEGENERATE:
        return None
    return result / length


def _initial_up(aim):
    """平行移動の最初の上方向を、aim に最も直交する主軸から作る。

    Args:
        aim (om2.MVector): 正規化済みの最初の接線。

    Returns:
        om2.MVector: aim に直交する単位ベクトル。同程度なら Y→Z→X の順に選ぶ。
    """
    candidates = (om2.MVector(0, 1, 0), om2.MVector(0, 0, 1), om2.MVector(1, 0, 0))
    best = min(candidates, key=lambda axis: abs(axis * aim))
    return _perpendicular(best, aim)


def _transport(up, start, end, start_aim, end_aim):
    """二重反射法(rotation minimizing frame)で上方向を次の点へ運ぶ。

    Args:
        up (om2.MVector): start での上方向(start_aim に直交する単位ベクトル)。
        start (om2.MPoint): 現在の点。
        end (om2.MPoint): 次の点。
        start_aim (om2.MVector): 現在の点の単位接線。
        end_aim (om2.MVector): 次の点の単位接線。

    Returns:
        om2.MVector: end_aim に直交する単位ベクトル。
    """
    step = om2.MVector(end - start)
    squared = step * step
    reflected_up = up
    reflected_aim = start_aim
    if squared > _DEGENERATE:
        reflected_up = up - step * (2.0 / squared * (step * up))
        reflected_aim = start_aim - step * (2.0 / squared * (step * start_aim))
    second = end_aim - reflected_aim
    squared = second * second
    if squared > _DEGENERATE:
        reflected_up = reflected_up - second * (2.0 / squared * (second * reflected_up))
    result = _perpendicular(reflected_up, end_aim)
    if result is None:
        return _initial_up(end_aim)
    return result


def _fill_missing(values):
    """None の要素を直前の値(先頭は最初の有効な値)で埋める。

    Args:
        values (list[object | None]): 埋める並び。

    Returns:
        list[object] | None: 埋めた新しい並び。有効な値が1つも無い場合は None。
    """
    valid = [value for value in values if value is not None]
    if not valid:
        return None
    previous = valid[0]
    result = []
    for value in values:
        if value is not None:
            previous = value
        result.append(previous)
    return result


def _frame_matrix(position, aim, up, aim_axis, up_axis):
    """位置と直交する2方向からマトリクスを組む。

    Args:
        position (om2.MPoint): 平行移動。
        aim (om2.MVector): aim_axis へ向ける単位ベクトル。
        up (om2.MVector): up_axis へ向ける、aim に直交する単位ベクトル。
        aim_axis (tuple[int, float]): aim の軸番号と符号。
        up_axis (tuple[int, float]): up の軸番号と符号。

    Returns:
        Matrix: 行ベクトルの規約(各行が軸、4行目が位置)の右手系マトリクス。
    """
    axes = [None, None, None]
    axes[aim_axis[0]] = aim * aim_axis[1]
    axes[up_axis[0]] = up * up_axis[1]
    other = 3 - aim_axis[0] - up_axis[0]
    axes[other] = axes[(other + 1) % 3] ^ axes[(other + 2) % 3]
    values = []
    for axis in axes:
        values.extend((axis.x, axis.y, axis.z, 0.0))
    values.extend((position.x, position.y, position.z, 1.0))
    return Matrix(values)


class NurbsCurve(Shape):
    """NURBS カーブの形状情報を提供するシェイプラッパー。

    点列からの作成は :func:`mlib.createCurve <mlib.cmds.createCurve.createCurve>`、CV位置の一括書込みは :meth:`setCvPositions` を使う。
    CV(:class:`~mlib.components.cv.CV`)の参照からも座標を照会・編集できる。反転は :meth:`mirror`。
    """

    def getCV(self, index):
        """CV 番号から単体ラッパーを取得する。

        Args:
            index (int): ゼロ始まりの CV 番号。

        Returns:
            CV: シーン上の CV を参照するラッパー。

        Raises:
            IndexError: CV 番号が範囲外の場合。
        """
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
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            unit (str | None): 出力単位。既定はcm。Noneは現在の距離UI単位。
                mm/cm/m/km/in/ft/yd/mi、またはMayaの長名。

        Returns:
            float: 指定単位での弧長。単位省略時はcm。
                worldSpace=Trueは親の非均等スケール・シアーとインスタンスの変換を含む。

        Raises:
            TypeError: 単位の型が不正な場合。
            ValueError: toleranceが正の有限値でない、worldSpaceがboolでない、または単位名が未対応の場合。
            RuntimeError: 無効なカーブ、またはMayaが評価を拒否した場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        ws = _world_space(worldSpace)
        from ..common import units
        # 単位は毎回照会する。係数を使うためシーンの単位設定は変更しない。
        factor = units.convertDistance(1.0, fromUnit="cm", toUnit=unit)
        tolerance = float(tolerance)
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("tolerance must be positive and finite")
        return self._space_curve(ws).length(tolerance) * factor

    def getCvPositions(self, worldSpace=_UNSET, *, ws=_UNSET):
        """CV の位置を取得する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[Vector]: CV 順の位置(:class:`~mlib.maths.vector.Vector`)。距離は Maya API の
                内部単位(cm)。有理カーブのウェイト(w)は含まず、wで割らないXYZを返す。
                そのまま :meth:`setCvPositions` へ渡せる。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        ws = _world_space(worldSpace)
        space = om2.MSpace.kWorld if ws else om2.MSpace.kObject
        return _vectors_of_points(self._geometry_fn().cvPositions(space))

    def setCvPositions(self, points, worldSpace=_UNSET, *, fast=False, ws=_UNSET):
        """全CVの位置を一度に書き込み、自身を返す。

        :meth:`getCvPositions` と同じ並び・単位(内部単位cm)の点列を受け付け、通常は ``cmds.xform`` で
        書き込んで1回のUndoにまとめる。``fast=True`` は ``MFnNurbsCurve.setCVPositions`` で全CVを1回で
        書き込み、Undoに記録しない。CVの数・次数・ノット・ウェイトは変更しない。
        周期カーブは、独立CV数(``getNumCVs() - getDegree()``)の点列か、末尾の重複CVを含む
        ``getNumCVs()`` 個の点列(重複CVは先頭の対応CVと同じ位置であること)を受け付ける。

        Args:
            points (Iterable[Sequence[float] | om2.MPoint | om2.MVector]): CV順の位置。各点は3個の
                有限な数値。MPointはwで割らずにXYZを使う。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            NurbsCurve: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、または点の型・成分が不正な場合。
            ValueError: 点の数がCV数と合わない、成分が有限でない、周期カーブの重複CVが先頭の
                CVと一致しない、またはworldSpace=Trueで変換マトリクスが特異な場合。
            RuntimeError: 形状データが無い・無効なシェイプ、またはロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、createへの入力(コンストラクションヒストリ)がある場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        values = geometry_edit.point_list(points)
        fn = self._geometry_fn()
        count = fn.numCVs
        independent = count
        if fn.form == om2.MFnNurbsCurve.kPeriodic:
            independent = count - fn.degree
            if len(values) == count:
                for index in range(independent, count):
                    if values[index] != values[index - independent]:
                        raise ValueError("Overlapping CVs of a periodic curve must match their first CVs")
                values = values[:independent]
        if len(values) != independent:
            if independent != count:
                raise ValueError(f"Expected {independent} or {count} points, got {len(values)}")
            raise ValueError(f"Expected {count} points, got {len(values)}")
        with _edit_context("mlibNurbsCurveSetCvPositions", fast, transaction=True):
            geometry_edit.set_positions(self, list(range(independent)), values, ws, fast=fast)
        return self

    def mirror(self, axis="x", worldSpace=_UNSET, pivot=(0.0, 0.0, 0.0), indices=None, *, fast=False, ws=_UNSET):
        """CV座標を、指定空間の中心pivotに対して反転する(``2 * pivot - 現在座標``)。

        Transform・次数・ノット・CVの順序とウェイト(w)は変更しない。共有Shapeの全インスタンスへ影響し、
        複製やパラメータ方向の反転は行わない。全CVの座標を先に読んでから書くため、周期カーブの
        末尾の重複CVも二重に反転しない(重複CVは先頭の独立CVと同じ位置に揃う)。
        入力をすべて検証してから書き込み、通常は ``cmds.xform`` をCVごとに呼んで1回のUndoにまとめる。
        ``fast=True`` は ``MFnNurbsCurve.setCVPositions`` で全CVを1回で書く。

        Args:
            axis (str | int): 反転する軸 ``"x"``・``"y"``・``"z"``、またはミラー面 ``"YZ"``・``"XZ"``・``"XY"``
                (x⇔YZ、y⇔XZ、z⇔XY。文字の順序・大文字小文字は問わない)、または0/1/2。
            worldSpace (bool): Trueは保持DAGパスのワールド空間、FalseはShapeのオブジェクト空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            pivot (Iterable[float]): 指定空間の反転中心XYZ(cm)。既定は原点で、Transformのピボットとは独立。
            indices (Iterable[int] | None): OpenMayaのCV番号。Noneは全CV、空列は変更なし。重複は1回だけ処理する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            NurbsCurve: 自身。

        Raises:
            TypeError: worldSpace・fastがbool以外、axisが文字列・int以外、または番号の型が不正な場合。
            ValueError: axis・pivotが不正、またはworldSpace=Trueで変換マトリクスがほぼ特異な場合。
            IndexError: CV番号が負または範囲外の場合。
            RuntimeError: 形状データが無い・無効なシェイプ、またはロック等でMayaが書込みを拒否した場合。
            NotImplementedError: fast=Trueで、createへの入力(コンストラクションヒストリ)がある場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        _require_bool(fast, "fast")
        ws = _world_space(worldSpace)
        _write_points([self._mirror_plan(axis, ws, pivot, indices, fast)], fast, "mlibNurbsCurveMirror")
        return self

    def getCollocatedCVGroups(self, tolerance=1e-6, worldSpace=_UNSET, *, ws=_UNSET):
        """ほぼ同じ位置にある CV をグループ化して取得する。

        周期カーブの重複 CV や、クリーンアップ前のカーブの検証などに使う。

        Args:
            tolerance (float): 同一位置とみなす距離の許容誤差(Maya API の
                内部距離単位)。正の値を指定する。
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[list[int]]: 2個以上の CV が重なっているグループのみを、
                各グループ内は番号昇順、グループ間は先頭番号の昇順で返す。
                重なりのない単独の CV は含まない。

        Raises:
            ValueError: tolerance が正の値でない場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        ws = _world_space(worldSpace)
        if not tolerance > 0:
            raise ValueError("tolerance must be positive")
        # 距離の計算には MPoint.distanceTo を使うため、Vector へ変換せずに om2 の点列を読む。
        positions = self._geometry_fn().cvPositions(om2.MSpace.kWorld if ws else om2.MSpace.kObject)
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

    def getParamRange(self):
        """パラメーターの範囲(``MFnNurbsCurve.knotDomain``)を取得する。

        Returns:
            tuple[float, float]: 最小と最大のパラメーター。``minValue``・``maxValue`` アトリビュートと同じ値。

        Raises:
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        start, end = self._geometry_fn().knotDomain
        return start, end

    def getClosestPoint(self, point, worldSpace=_UNSET, *, ws=_UNSET):
        """指定した位置に最も近いカーブ上の点とそのパラメーターを取得する。

        ``nearestPointOnCurve`` ノードの ``result.position``・``result.parameter`` に相当する。
        シーンに計算ノードを作成しない。

        Args:
            point (Sequence[float] | om2.MPoint | om2.MVector): 位置(cm)。worldSpaceと同じ空間で指定する。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            tuple[Vector, float]: 最も近い点(cm)とパラメーター。

        Raises:
            TypeError: 点の型・成分が不正、またはworldSpaceがbool以外の場合。
            ValueError: 成分が有限でない場合。
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        x, y, z = geometry_edit.point_list([point])[0]
        curve = self._space_curve(worldSpace)
        found, param = curve.closestPoint(om2.MPoint(x, y, z), tolerance=1e-7)
        return _vectors_of_points([found])[0], param

    def getPointAtParam(self, param, worldSpace=_UNSET, *, ws=_UNSET):
        """パラメーターの位置を取得する。

        Args:
            param (float): :meth:`getParamRange` の範囲内のパラメーター。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector: 位置(cm)。``pointOnCurveInfo`` の ``position`` と同じ。

        Raises:
            TypeError: paramが数値でない、またはworldSpaceがbool以外の場合。
            ValueError: paramが有限でない、または範囲外の場合。
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        curve = self._space_curve(worldSpace)
        return _vectors_of_points([curve.getPointAtParam(self._require_param(curve, param))])[0]

    def getTangentAtParam(self, param, worldSpace=_UNSET, *, ws=_UNSET):
        """パラメーターの位置の、正規化した接線を取得する。

        Args:
            param (float): :meth:`getParamRange` の範囲内のパラメーター。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector: パラメーターの増える向きの単位ベクトル。``pointOnCurveInfo`` の ``normalizedTangent`` と同じ。

        Raises:
            TypeError: paramが数値でない、またはworldSpaceがbool以外の場合。
            ValueError: paramが有限でない・範囲外、または重なったCVで接線が0になる位置の場合。
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        curve = self._space_curve(worldSpace)
        tangent = self._tangent(curve, self._require_param(curve, param))
        if tangent is None:
            raise ValueError(f"Tangent is undefined at param {param}: {self.getFullName()}")
        return Vector(tangent)

    def getNormalAtParam(self, param, worldSpace=_UNSET, *, ws=_UNSET):
        """パラメーターの位置の、正規化した法線(``MFnNurbsCurve.normal``)を取得する。

        次数2以上は曲率の向き(主法線)、次数1はCVの平均の平面内で接線に直交する向き。
        ``pointOnCurveInfo`` の ``normalizedNormal`` と同じ。

        Args:
            param (float): :meth:`getParamRange` の範囲内のパラメーター。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            Vector: 単位ベクトル。

        Raises:
            TypeError: paramが数値でない、またはworldSpaceがbool以外の場合。
            ValueError: paramが有限でない・範囲外、または法線を定義できない場合(次数2以上で
                曲率が0の位置(直線部分・変曲点)、次数1でCVがすべて一直線上にある場合)。
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        curve = self._space_curve(worldSpace)
        value = self._require_param(curve, param)
        if curve.degree == 1:
            # 次数1の直線にもMayaは任意の直交方向を返すため、CVの一直線を先に拒否する。
            points = curve.cvPositions()
            first = om2.MVector(points[0])
            span = max((om2.MVector(item) - first for item in points), key=lambda item: item.length())
            if span.length() < _DEGENERATE or all(
                    (span ^ (om2.MVector(item) - first)).length() <= 1e-9 * span.length() ** 2 for item in points):
                raise ValueError(f"Normal is undefined on a straight curve: {self.getFullName()}")
        try:
            normal = curve.normal(value)
        except RuntimeError:
            # 曲率が0の位置ではMayaがkInvalidParameterで拒否する。
            normal = om2.MVector()
        length = normal.length()
        if length < _DEGENERATE:
            raise ValueError(f"Normal is undefined at param {param}: {self.getFullName()}")
        return Vector(normal / length)

    def getLengthAtParam(self, param, worldSpace=_UNSET, *, unit="cm", ws=_UNSET):
        """カーブの始点からパラメーターまでの弧長を取得する。

        ``arcLengthDimension`` の ``arcLength`` に相当する。シーンに計算ノードを作成しない。

        Args:
            param (float): :meth:`getParamRange` の範囲内のパラメーター。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            unit (str | None): 出力単位。既定はcm。Noneは現在の距離UI単位。:meth:`getLength` と同じ指定。

        Returns:
            float: 指定単位での弧長。

        Raises:
            TypeError: paramが数値でない、worldSpaceがbool以外、または単位の型が不正な場合。
            ValueError: paramが有限でない・範囲外、または単位名が未対応の場合。
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        curve = self._space_curve(worldSpace)
        factor = self._unit_factor(unit)
        value = self._require_param(curve, param)
        if value <= curve.knotDomain[0]:
            return 0.0
        return curve.findLengthFromParam(value) * factor

    def getParamAtLength(self, length, worldSpace=_UNSET, *, unit="cm", ws=_UNSET):
        """カーブの始点からの弧長に対応するパラメーターを取得する。

        Args:
            length (float): 0から全長(:meth:`getLength`)までの弧長。単位はunit。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
                ワールド空間の弧長は親の非均等スケールを含む。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。
            unit (str | None): lengthの単位。既定はcm。Noneは現在の距離UI単位。:meth:`getLength` と同じ指定。

        Returns:
            float: パラメーター。0は始点、全長は終点のパラメーター。

        Raises:
            TypeError: lengthが数値でない、worldSpaceがbool以外、または単位の型が不正な場合。
            ValueError: lengthが有限でない・0未満・全長を超える、または単位名が未対応の場合。
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        curve = self._space_curve(worldSpace)
        factor = self._unit_factor(unit)
        value = _finite(length, "length") / factor
        return self._param_at_length(curve, value, curve.length(1e-6))

    def getParamsAlong(self, count, worldSpace=_UNSET, *, ws=_UNSET):
        """弧長で等間隔に並ぶパラメーターを取得する。

        開いたカーブ(``getForm()`` が kOpen)は両端を含み、間隔は全長/(count-1)。
        閉じたカーブ・周期カーブ(kClosed・kPeriodic)は終点が始点と重なるため終点を含めず、
        始点から全長/count の間隔で count 個の異なる点を返す。count=1 は始点だけ。

        Args:
            count (int): 点の数。1以上。
            worldSpace (bool): Trueはワールド空間の弧長、Falseはローカル(オブジェクト)空間の弧長で等分する。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[float]: 始点から順のパラメーター。

        Raises:
            TypeError: countがint以外(boolを含む)、またはworldSpaceがbool以外の場合。
            ValueError: countが1未満の場合。
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        count = _require_count(count)
        curve = self._space_curve(worldSpace)
        return self._params_along(curve, count)

    def getMatricesAlong(self, count, up=None, *, aimAxis="x", upAxis="y", worldSpace=_UNSET, ws=_UNSET):
        """弧長で等間隔の各点に、接線を aimAxis へ向けたマトリクスを取得する。

        点の並びは :meth:`getParamsAlong` と同じ。各マトリクスは正規直交の右手系(スケール1)で、
        平行移動はカーブ上の位置(cm)。

        - ``up`` を指定すると、各点で up から接線方向の成分を除いた向きを upAxis へ向ける。
          接線と平行で向きを決められない点は直前の点の向き(先頭なら最初に決められた点の向き)を使う。
        - ``None`` は平行移動(二重反射法による rotation minimizing frame)で、最初の点の向きを
          ねじれを加えずに運ぶ。最初の点の upAxis は、最初の接線に最も直交する主軸(同程度なら
          Y→Z→X)を接線に直交させた向き。点の間を細かく分けて運ぶため、count が少なくても向きは同じ。
          閉じたカーブでは、一周後の向きが最初と一致するとは限らない(ねじれを均す処理はしない)。
        - 重なったCVで接線が0になる点は、直前(先頭なら次)の点の接線を使う。

        Args:
            count (int): 点の数。1以上。
            up (Sequence[float] | om2.MVector | None): upAxis へ向ける方向。worldSpaceと同じ空間で指定する。
            aimAxis (str): 接線へ向ける軸。"x"・"y"・"z"・"-x"・"-y"・"-z"。
            upAxis (str): up へ向ける軸。aimAxis と別の軸。
            worldSpace (bool): Trueはワールド空間、Falseはローカル(オブジェクト)空間。
            ws (bool): worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。

        Returns:
            list[Matrix]: 始点から順のマトリクス。

        Raises:
            TypeError: countがint以外(boolを含む)、upの型・成分、aimAxis・upAxisがstr以外、
                またはworldSpaceがbool以外の場合。
            ValueError: countが1未満、upの成分が有限でない・長さ0、軸名が未対応・aimAxisとupAxisが同じ軸、
                upがすべての点で接線と平行、またはすべての点で接線が0の場合。
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)
        count = _require_count(count)
        aim_axis = _require_axis(aimAxis, "aimAxis")
        up_axis = _require_axis(upAxis, "upAxis")
        if aim_axis[0] == up_axis[0]:
            raise ValueError(f"aimAxis and upAxis must be different axes: {aimAxis!r}, {upAxis!r}")
        up_vector = None
        if up is not None:
            x, y, z = geometry_edit.point_list([up])[0]
            up_vector = om2.MVector(x, y, z)
            if up_vector.length() < _DEGENERATE:
                raise ValueError("up must not be a zero vector")
            up_vector.normalize()
        curve = self._space_curve(worldSpace)
        params = self._params_along(curve, count)
        aims = _fill_missing([self._tangent(curve, param) for param in params])
        if aims is None:
            raise ValueError(f"Tangent is undefined along the curve: {self.getFullName()}")
        positions = [curve.getPointAtParam(param) for param in params]
        if up_vector is not None:
            ups = _fill_missing([_perpendicular(up_vector, aim) for aim in aims])
            if ups is None:
                raise ValueError("up is parallel to the curve tangent at every point")
        else:
            ups = self._transported_ups(curve, params, aims)
        return [_frame_matrix(position, aim, value, aim_axis, up_axis)
                for position, aim, value in zip(positions, aims, ups)]

    def _space_curve(self, worldSpace):
        """指定空間の形状をオブジェクト空間で照会できる ``om2.MFnNurbsCurve`` を返す。

        ワールド空間はメモリ内のコピーのCVだけをワールド座標へ変換する。弧長などオブジェクト空間でしか
        計算できない照会や、非均等スケール下の法線も、変換後の形状として一貫して求められる。
        元のCV・履歴・Undoキューは変更しない。copyにより次数・ノット・有理カーブのウェイトも維持する。

        Args:
            worldSpace (bool): Trueはワールド空間、Falseはローカル空間。

        Returns:
            om2.MFnNurbsCurve: kObject で照会する function set。

        Raises:
            TypeError: worldSpaceがbool以外の場合。
            RuntimeError: 形状データを持たない空のシェイプの場合。
        """
        ws = _world_space(worldSpace)
        source = self._geometry_fn()
        if not ws:
            return source
        data = om2.MFnNurbsCurveData().create()
        curve = _OwnedCurve(om2.MFnNurbsCurve().copy(source.object(), data))
        # 形状データのMObjectが解放されるとfunction setが無効になるため、照会を終えるまで保持する。
        curve.data = data
        curve.setCVPositions(source.cvPositions(om2.MSpace.kWorld))
        curve.updateCurve()
        return curve

    @staticmethod
    def _unit_factor(unit):
        """cmから指定した距離単位への係数を返す。

        Args:
            unit (str | None): 距離単位。Noneは現在の距離UI単位。

        Returns:
            float: 1cmを指定単位で表した値。

        Raises:
            TypeError: 単位の型が不正な場合。
            ValueError: 単位名が未対応の場合。
        """
        # 循環importを避けるため、単位の照会時に読み込む。
        from ..common import units
        return units.convertDistance(1.0, fromUnit="cm", toUnit=unit)

    @staticmethod
    def _require_param(curve, param):
        """パラメーターを検証し、範囲の端へ丸め込んだfloatを返す。

        Args:
            curve (om2.MFnNurbsCurve): 照会するカーブ。
            param (float): パラメーター。範囲外は端からの相対1e-9までを許す。

        Returns:
            float: 検証済みのパラメーター。

        Raises:
            TypeError: 数値でない場合。
            ValueError: 有限でない、または範囲外の場合。
        """
        value = _finite(param, "param")
        start, end = curve.knotDomain
        margin = 1e-9 * max(1.0, end - start)
        if value < start - margin or value > end + margin:
            raise ValueError(f"param {value} is outside the curve range [{start}, {end}]")
        return min(max(value, start), end)

    @staticmethod
    def _tangent(curve, param):
        """正規化した接線を返す。

        Args:
            curve (om2.MFnNurbsCurve): 照会するカーブ。
            param (float): 検証済みのパラメーター。

        Returns:
            om2.MVector | None: 単位ベクトル。接線が0の位置は None。
        """
        # MFnNurbsCurve.tangentは文書と異なり正規化しない微分ベクトルを返す。
        tangent = curve.tangent(param)
        length = tangent.length()
        if length < _DEGENERATE:
            return None
        return tangent / length

    @staticmethod
    def _param_at_length(curve, length, total):
        """弧長を検証し、対応するパラメーターを返す。

        Args:
            curve (om2.MFnNurbsCurve): 照会するカーブ。
            length (float): cmの弧長。
            total (float): カーブの全長(cm)。

        Returns:
            float: パラメーター。

        Raises:
            ValueError: 0未満、または全長を超える場合(相対1e-6までは端へ丸める)。
        """
        margin = 1e-6 * max(1.0, total)
        if length < -margin or length > total + margin:
            raise ValueError(f"length {length} is outside the curve length [0, {total}]")
        start, end = curve.knotDomain
        if length <= 0.0:
            return start
        if length >= total:
            return end
        return min(max(curve.findParamFromLength(length), start), end)

    def _params_along(self, curve, count):
        """弧長で等間隔のパラメーターを返す(:meth:`getParamsAlong` の本体)。

        Args:
            curve (om2.MFnNurbsCurve): 照会するカーブ。
            count (int): 検証済みの点の数。

        Returns:
            list[float]: 始点から順のパラメーター。
        """
        start, end = curve.knotDomain
        if count == 1:
            return [start]
        total = curve.length(1e-6)
        closed = curve.form != om2.MFnNurbsCurve.kOpen
        intervals = count if closed else count - 1
        params = [start]
        for index in range(1, count):
            params.append(self._param_at_length(curve, total * index / intervals, total))
        if not closed:
            params[-1] = end
        return params

    def _transported_ups(self, curve, params, aims):
        """平行移動で運んだ各点の上方向を返す。

        Args:
            curve (om2.MFnNurbsCurve): 照会するカーブ。
            params (list[float]): 出力する点のパラメーター。
            aims (list[om2.MVector]): 各点の単位接線。

        Returns:
            list[om2.MVector]: 各点の、接線に直交する単位ベクトル。
        """
        up = _initial_up(aims[0])
        ups = [up]
        if len(params) == 1:
            return ups
        total_length = curve.length(1e-6)
        steps = max(1, -(-_TRANSPORT_STEPS // (len(params) - 1)))
        point = curve.getPointAtParam(params[0])
        aim = aims[0]
        for index in range(1, len(params)):
            begin = curve.findLengthFromParam(params[index - 1]) if params[index - 1] > params[0] else 0.0
            finish = curve.findLengthFromParam(params[index])
            for step in range(1, steps + 1):
                if step == steps:
                    param = params[index]
                    next_aim = aims[index]
                else:
                    length = begin + (finish - begin) * step / steps
                    param = self._param_at_length(curve, length, total_length)
                    tangent = self._tangent(curve, param)
                    next_aim = aim if tangent is None else tangent
                next_point = curve.getPointAtParam(param)
                up = _transport(up, point, next_point, aim, next_aim)
                point = next_point
                aim = next_aim
            ups.append(up)
        return ups

    def _mirror_plan(self, axis, ws, pivot, indices, fast):
        """CVを反転した座標を求め、書込みの計画を返す。シーンは変更しない。

        :meth:`Transform.mirrorGeometry <mlib.nodes.transform.Transform.mirrorGeometry>` が
        全Shapeを検証してから書き込むために使う。

        Args:
            axis (str | int): 反転する軸またはミラー面。
            ws (bool): Trueならワールド空間。検証済み。
            pivot (Iterable[float]): 指定空間の反転中心XYZ(cm)。
            indices (Iterable[int] | None): CV番号。Noneは全CV。
            fast (bool): TrueならOpenMayaで直接書けるかも確かめる。

        Returns:
            tuple | None: ``(shape, indices, rows, ws)``。対象が無ければNone。
        """
        self._geometry_fn()
        return _mirror_plan(self.getCVs(indices), axis, ws, pivot, fast)

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
