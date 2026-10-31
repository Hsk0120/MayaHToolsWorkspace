"""アニメーションカーブの共通操作。通常編集はUndo、fastはAPI直接更新。"""

import math
from contextlib import contextmanager

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds

from ..common.keyframe import Keyframe, Keyframes
from ..common.units import angleToUi
from ..core.attributeType import _convert_units, _from_seconds, _to_seconds
from ..core.fastWrite import require_writable
from ..core.nodeEdit import delete_nodes
from ..decorator import _edit_context, _require_bool, undoChunk
from ..util import _angle_unit, _from_radians, _time_unit, _to_radians
from .node import Node


#: コマンドの接線名からAPIの接線定数への対応。APIのSmooth等の別表記を外へ出さない。
_TANGENT_TYPES = {
    name: getattr(oma2.MFnAnimCurve, constant)
    for name, constant in (
        ("fixed", "kTangentFixed"),
        ("linear", "kTangentLinear"), ("flat", "kTangentFlat"),
        ("spline", "kTangentSmooth"), ("step", "kTangentStep"),
        ("slow", "kTangentSlow"), ("fast", "kTangentFast"),
        ("clamped", "kTangentClamped"), ("plateau", "kTangentPlateau"),
        ("stepnext", "kTangentStepNext"), ("auto", "kTangentAuto"),
        ("autocustom", "kTangentAutoCustom"), ("autoease", "kTangentAutoEase"),
        ("automix", "kTangentAutoMix"),
    )
    if hasattr(oma2.MFnAnimCurve, constant)
}
#: APIの接線定数からコマンドの接線名への逆引き。
_TANGENT_NAMES = {value: name for name, value in _TANGENT_TYPES.items()}


def _default_tangents():
    """Mayaの設定の既定の接線型(``keyTangent -q -g``)を、fastで使えるAPIの定数で返す。

    Returns:
        tuple[int, int]: 入力・出力の接線型。fastで使えない型(fixed・入力のstep/stepnext等)はautoにする。
    """
    names = cmds.keyTangent(query=True, g=True, inTangentType=True, outTangentType=True) or ["auto", "auto"]
    result = []
    for incoming, name in zip((True, False), names):
        name = str(name).lower()
        if name == "fixed" or name not in _TANGENT_TYPES or (incoming and name in ("step", "stepnext")):
            name = "auto"
        result.append(_TANGENT_TYPES[name])
    return tuple(result)


class AnimCurve(Node):
    """animCurveノードを参照し、8種類のカーブのキー・接線・外挿を編集する。

    入力T型は既定で現在のUI時間単位のフレーム(各メソッドの ``timeUnit="sec"`` で秒)、U型は無次元。
    出力はA型が度(各メソッドの ``unit="rad"`` でラジアン)、L型がcm、T型がフレーム(``timeUnit="sec"`` で秒)、
    U型が無次元。接線の角度も既定で度。T型とA型の両方を持つカーブ(animCurveTA)ではunitとtimeUnitを
    別々に指定する。
    ドライバーPlugの単位変換はDrivenKeyが担当する。
    通常編集はUI単位へ換算してcmdsへ渡し、Undo有効時に一つのチャンクへまとめる。
    fastはUndo設定を変更せずOpenMayaで直接更新する。失敗時の自動復元は保証しない。
    """

    def isTimeInput(self):
        """横軸が時間ならTrue、単位なしならFalse。

        Returns:
            bool: 横軸が時間ならTrue、単位なしならFalse。

        Raises:
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        self._require_valid("access attributes of")
        return self.getType()[9] == "T"

    def getKeyCount(self):
        """キー数。

        Returns:
            int: キー数。
        """
        return self._curve_fn().numKeys

    def getKeyInputs(self, *, timeUnit="frame"):
        """カーブのキー入力をキー番号順で取得する。

        入力T型はtimeUnitの単位(既定は現在のUI時間単位のフレーム)、U型は無次元の入力値を返す。
        U型のドライバーPlugのUI表示値へは変換しない。

        Args:
            timeUnit (str): 入力T型の単位。既定 ``"frame"`` はフレーム、``"sec"`` は秒
                (``"frames"`` / ``"seconds"`` 等の別名も可)。U型では使わない。

        Returns:
            list[float]: 新しい入力値リスト。変更してもカーブへ書き戻さない。

        Raises:
            TypeError: timeUnitが文字列以外の場合。
            ValueError: timeUnitが未対応の単位名の場合。
        """
        time_unit = self._input_time_unit(timeUnit)
        fn = self._curve_fn()
        return [_from_seconds(self._api_number(fn.input(i)), time_unit) for i in range(fn.numKeys)]

    def getKeyValues(self, *, unit="deg", timeUnit="frame"):
        """カーブのキー出力値をキー番号順で取得する。

        角度はunitの単位(既定は度)、距離はcm、時間はtimeUnitの単位(既定はフレーム)、その他は無次元で返す。
        時間出力はMFnAnimCurve.value()の版差を避け、time型のキー値Plugから読む。

        Args:
            unit (str): 角度出力(A型)の単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
                (``"degree"`` 等の別名も可)。他の型では使わない。
            timeUnit (str): 時間出力(TT・UT型)の単位。既定 ``"frame"`` は現在のUI時間単位のフレーム、
                ``"sec"`` は秒。他の型では使わない。

        Returns:
            list[float]: 新しい出力値リスト。変更してもカーブへ書き戻さない。

        Raises:
            TypeError: unit・timeUnitが文字列以外の場合。
            ValueError: unit・timeUnitが未対応の単位名の場合。
        """
        angle_unit = self._output_angle_unit(unit)
        time_unit = _time_unit(timeUnit)
        fn = self._curve_fn()
        if self.getType().endswith("T"):
            return [self.getPlug("ktv")[i][1].get(timeUnit=time_unit) for i in range(fn.numKeys)]
        return [_from_radians(fn.value(i), angle_unit) for i in range(fn.numKeys)]

    def evaluate(self, input, *, unit="deg", timeUnit="frame"):
        """カーブ単体を指定入力で評価する。現在時刻は変更しない。

        接続先の合成結果ではなく、カーブの補間・外挿値を返す。
        時間出力はMaya 2022/2023のAPI版差を補正してから、timeUnitの単位へ揃える。

        Args:
            input (float): T型入力はtimeUnitの単位(既定はフレーム)、U型入力は無次元。
                float()で変換し有限性を検査する。
            unit (str): 角度出力(A型)の戻り値の単位。既定 ``"deg"`` は度、``"rad"`` はラジアン。
            timeUnit (str): T型入力のinputと、時間出力(TT・UT型)の戻り値の単位。既定 ``"frame"`` は
                現在のUI時間単位のフレーム、``"sec"`` は秒。

        Returns:
            float: 出力型に従う度(unit)/cm/フレーム(timeUnit)、または無次元の値。

        Raises:
            TypeError: float()へ変換できない型、またはunit・timeUnitが文字列以外。
            ValueError: 非有限値、float()変換で受理できない値、またはunit・timeUnitが未対応の単位名。
            RuntimeError: 空カーブ、またはMayaの評価失敗。空カーブは入力変換より先に拒否する。
        """
        angle_unit = self._output_angle_unit(unit)
        input_unit, output_unit = self._input_time_unit(timeUnit), self._output_time_unit(timeUnit)
        fn = self._curve_fn()
        if not fn.numKeys:
            raise RuntimeError("Cannot evaluate an empty curve")
        result = fn.evaluate(self._api_input(_to_seconds(self._finite(input), input_unit)))
        if self.getType().endswith("T") and om2.MGlobal.apiVersion() < 20240000:
            # Maya 2022/2023のPython APIは生tick数をUI単位のMTimeとして返す。
            # APIのtick周波数で秒へ戻し、正常な2024以降の返却は補正しない。
            return _from_seconds(result.value / om2.MTime.ticksPerSecond(), output_unit)
        return _from_seconds(_from_radians(self._api_number(result), angle_unit), output_unit)

    def setKey(self, input, value, inTangentType=None, outTangentType=None, *, unit="deg", timeUnit="frame",
               fast=False):
        """キーを追加する。同じ入力位置にキーがあれば値と、指定した接線型を更新する。

        接線型を省略すると ``cmds.setKeyframe`` と同じく、既存のキーは接線型を保ち、新しいキーは
        Mayaの設定(Preferences > Animation の Default tangent、``keyTangent -q -g``)に従う。
        通常はUI単位へ換算してsetKeyframeを呼ぶ。fastの既存キーは値→入力接線型→出力接線型の
        順に更新する。新規キーは両接線型を指定し、時間出力の値は追加後に設定する。
        後続の失敗で先行の変更を自動復元しない。

        Args:
            input (float): T型入力はtimeUnitの単位(既定はフレーム)、U型入力は無次元。
            value (float): 出力型に従う度(unit)/cm/フレーム(timeUnit)、または無次元。inputと共に有限値へ変換する。
            inTangentType (str | None): Mayaの入力接線型。Noneは上記の既定。fastのstepはautoへ補正する。
            outTangentType (str | None): Mayaの出力接線型。Noneは上記の既定。
            unit (str): 角度出力(A型)のvalueの単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
                (``"degree"`` 等の別名も可)。他の型では使わない。
            timeUnit (str): T型入力のinputと、時間出力(TT・UT型)のvalueの単位。既定 ``"frame"`` は
                現在のUI時間単位のフレーム、``"sec"`` は秒(``"seconds"`` 等の別名も可)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            AnimCurve: 自身。fixed接線の角度・ウェイト指定にはsetTangentを使う。

        Raises:
            TypeError: fastがbool以外、unit・timeUnitが文字列以外、または数値へ変換できない型。
            ValueError: 非有限値、不正な数値、未対応のunit・timeUnit、またはfastでfixed/global/未知の接線型を指定した場合。
            RuntimeError: ノードが無効(削除済み)の場合。fastも通常と同じ文言で、編集前に拒否する。
            NotImplementedError: fastの入力接線にstepnextを指定した場合。編集前に拒否する。
        """
        with _edit_context("mlibAnimCurveSetKey", fast):
            angle_unit = self._output_angle_unit(unit)
            input_unit, output_unit = self._input_time_unit(timeUnit), self._output_time_unit(timeUnit)
            input = _to_seconds(self._finite(input), input_unit)
            value = _to_seconds(_to_radians(self._finite(value), angle_unit), output_unit)
            if fast:
                fn = self._curve_fn()
                tangent_in = None if inTangentType is None else \
                    self._tangent_type(inTangentType, incoming=True, key=True)
                tangent_out = None if outTangentType is None else self._tangent_type(outTangentType, key=True)
                at = self._api_input(input)
                self._require_curve_writable()
                index = fn.find(at)
                if index is not None:
                    self._set_api_value(fn, index, value)
                    if tangent_in is not None:
                        fn.setInTangentType(index, tangent_in)
                    if tangent_out is not None:
                        fn.setOutTangentType(index, tangent_out)
                else:
                    default_in, default_out = _default_tangents()
                    tangent_in = default_in if tangent_in is None else tangent_in
                    tangent_out = default_out if tangent_out is None else tangent_out
                    if self.getType().endswith("T"):
                        # 旧Python APIの時間出力addKeyはMTimeの値を生tick扱いする。
                        # 0でキーを確保してtime型Plugへ秒を設定し、版差を避ける。
                        index = fn.addKey(at, om2.MTime(0, om2.MTime.kSeconds), tangent_in, tangent_out)
                        self._set_api_value(fn, index, value)
                    else:
                        fn.addKey(at, value, tangent_in, tangent_out)
                return self
            position = self._unit_value(input)
            value = self._unit_value(value, output=True)
            flags = {"time" if self.isTimeInput() else "float": position}
            if inTangentType is not None:
                flags["inTangentType"] = inTangentType
            if outTangentType is not None:
                flags["outTangentType"] = outTangentType
            cmds.setKeyframe(self.getFullName(), value=value, **flags)
            return self

    def removeKey(self, index=None, *, time=None, timeUnit="frame", keepCurve=True, fast=False):
        """指定番号、または入力の範囲にあるキーを削除する。キークリップボードは変更しない。

        index と time はどちらか一方を指定する。既定(keepCurve=True)では全キーを削除してもカーブを残す
        (:meth:`Plug.removeKey <mlib.plugs.plug.Plug.removeKey>`・``cmds.cutKey`` は空になったカーブを削除する)。

        Args:
            index (int | Sequence[int] | None): 0始まりのキー番号、またはその並び。
            time (float | Sequence[float] | None): 削除する入力の時刻、または両端を含む範囲 ``(start, end)``。
                T型入力はtimeUnitの単位(既定はフレーム)、U型入力は無次元。範囲内にキーが無ければ何もしない。
            timeUnit (str): T型入力のtimeの単位。``"frame"`` / ``"sec"``。
            keepCurve (bool): Trueは全キーを消してもカーブを残す。FalseはMayaと同じく空のカーブを削除する。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            AnimCurve: 自身。keepCurve=Falseでカーブを削除した場合、この参照は無効になる。

        Raises:
            TypeError: indexとtimeの両方・どちらも指定しない場合、timeが数値・2つの数値の並び以外、
                またはkeepCurve・fastがbool以外の場合。
            ValueError: timeが有限でない、範囲の開始が終了より大きい、またはtimeUnitが未対応の単位名の場合。
            IndexError: indexが範囲外の場合。
        """
        if (index is None) == (time is None):
            raise TypeError("Specify exactly one of index and time")
        _require_bool(keepCurve, "keepCurve")
        with _edit_context("mlibAnimCurveRemoveKey", fast):
            ranges = self._key_ranges(index, time, timeUnit)
            if not ranges:
                return self
            emptied = sum(end - start + 1 for start, end in ranges) == self.getKeyCount()
            if fast:
                self._require_curve_writable()
                fn = self._curve_fn()
                for start, end in reversed(ranges):
                    for key in range(end, start - 1, -1):
                        fn.remove(key)
                if emptied and not keepCurve:
                    # 同じ呼出しの中で MDGModifier を直接使って消すと、後の keyTangent 等でMayaが異常終了するため、
                    # mlib.delete(fast=True) と同じ削除の処理に任せる。
                    del fn
                    delete_nodes([self], fast=True)
            elif keepCurve and emptied:
                with self._kept_curve():
                    cmds.cutKey(self.getFullName(), index=ranges, clear=True, animation="objects")
            else:
                cmds.cutKey(self.getFullName(), index=ranges, clear=True, animation="objects")
            return self

    def replaceKeys(self, keys, *, unit="deg", timeUnit="frame"):
        """カーブを残したまま、全キーを指定したキーへ置き換える(1回のUndo)。

        ``keys`` の各要素は ``(入力, 値)`` または ``(入力, 値, 入力接線型, 出力接線型)``。接線型の省略・None・
        空文字列(:meth:`getTangent` が未登録の型に返す値)はMayaの設定(Default tangent)に従う。同じ入力が重なった場合は後の要素で上書きする。空の並びは
        全キーを消して空のカーブを残す。全要素を検査してからカーブを変える。fast引数は持たない。

        Args:
            keys (Iterable[Sequence]): 新しいキーの並び。入力・値の単位は :meth:`setKey` と同じ。
            unit (str): 角度出力(A型)の値の単位。``"deg"`` / ``"rad"``。
            timeUnit (str): T型入力と、時間出力の値の単位。``"frame"`` / ``"sec"``。

        Returns:
            AnimCurve: 自身。

        Raises:
            TypeError: 要素が2つ・4つの並びでない、または数値へ変換できない型の場合。
            ValueError: 非有限値、未知の接線型・fixed(角度・ウェイトは :meth:`setTangent` で書く)、
                またはunit・timeUnitが未対応の単位名の場合。
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        _angle_unit(unit)
        _time_unit(timeUnit)
        entries = []
        for key in keys:
            if not isinstance(key, (list, tuple)) or len(key) not in (2, 4):
                raise TypeError("Each key must be (input, value) or (input, value, inTangentType, outTangentType)")
            # getTangent が未登録の型に返す空文字列は、省略(Mayaの設定)と同じに扱う。
            tangents = tuple(name or None for name in key[2:]) if len(key) == 4 else (None, None)
            for name in tangents:
                if name is not None:
                    # cmds.setKeyframe も fixed を受け付けない(角度・ウェイトは setTangent で書く)。
                    self._tangent_type(name, key=True)
            entries.append((self._finite(key[0]), self._finite(key[1])) + tangents)
        with undoChunk("mlibAnimCurveReplaceKeys"):
            self._require_valid("set keys on")
            count = self.getKeyCount()
            if count:
                with self._kept_curve():
                    cmds.cutKey(self.getFullName(), index=(0, count - 1), clear=True, animation="objects")
            for input, value, tangent_in, tangent_out in entries:
                self.setKey(input, value, tangent_in, tangent_out, unit=unit, timeUnit=timeUnit)
            # カーブ名へ直接キーを打つと、Mayaは出力先を再評価しないことがあるため、出力を更新し直させる。
            cmds.dgdirty(self.getFullName())
            return self

    def getTangent(self, index, *, unit="deg"):
        """指定キーの入力/出力接線型、角度、ウェイトとロック状態を取得する。

        角度はMAngleからunitの単位(既定は度)へ変換する。接線ウェイトはgetTangentAngleWeight()の
        返却値をそのまま使い、一律の距離単位などへ追加変換しない(``keyTangent`` の照会と同じく、
        T型入力のウェイトは現在のUI時間単位に依存する)。時間の単位の引数(timeUnit)は持たない。
        lock/weightLockはキー単位、weightedTangentsはカーブ全体の状態である。

        Args:
            index (int): 0始まりの既存キー番号。
            unit (str): inAngle/outAngleの単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
                (``"degree"`` 等の別名も可)。

        Returns:
            dict: inTangentType/outTangentType、inAngle/outAngle、inWeight/outWeight、
                lock、weightLock、weightedTangentsの新しい辞書。型名はMayaコマンド表記で、
                未登録のAPI接線型は空文字列。辞書を変更してもカーブは更新しない。

        Raises:
            IndexError: bool、非int、負値、またはキー数以上の番号の場合。
            TypeError: unitが文字列以外の場合。
            ValueError: unitが未対応の単位名の場合。
        """
        angle_unit = _angle_unit(unit)
        self._index(index)
        fn = self._curve_fn()
        incoming = fn.getTangentAngleWeight(index, True)
        outgoing = fn.getTangentAngleWeight(index, False)
        return {"inTangentType": self._tangent_name(fn.inTangentType(index)),
                "outTangentType": self._tangent_name(fn.outTangentType(index)),
                "inAngle": _from_radians(incoming[0].asRadians(), angle_unit),
                "outAngle": _from_radians(outgoing[0].asRadians(), angle_unit),
                "inWeight": incoming[1], "outWeight": outgoing[1],
                "lock": fn.tangentsLocked(index), "weightLock": fn.weightsLocked(index),
                "weightedTangents": fn.isWeighted}

    def setTangent(self, index, *, unit="deg", fast=False, **kwargs):
        """指定キーの接線をMayaの接線ロック規則に従って変更する。

        weightedTangentsを指定した場合はカーブ全体のウェイト付き接線モードだけを適用し、
        同時指定したキー別フラグは適用しない。fastでも同時指定値の検証は省略しない。
        通常はkeyTangentへ角度をUI単位に換算して渡す。fastはlock、weightLock、
        入力側、出力側の順に更新し、後半の失敗による先行変更を自動復元しない。

        Args:
            index (int): 0始まりの既存キー番号。
            unit (str): inAngle/outAngleの単位。既定 ``"deg"`` は度、``"rad"`` はラジアン
                (``"degree"`` 等の別名も可)。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            **kwargs: getTangent()の辞書と同じ9種類の長名フラグ。角度はunitの単位、
                接線ウェイトはAPIの値を使う。fastでは角度/ウェイトをfloat()で有限性検査し、
                負のウェイトを拒否する。fastの型名は大文字小文字を区別せず、spline表記を使う。
                入力stepはautoへ補正する。ロックは自動解除しない。

        Returns:
            AnimCurve: 自身。

        Raises:
            ValueError: フラグが空/未知、unitが未対応、またはfastで不正値やglobal/未知の接線型を指定した場合。
            TypeError: unitが文字列以外の場合。
            IndexError: キー番号が不正な場合。
            NotImplementedError: fastで入力接線にstepnextを指定した場合。
                ロック・ウェイトを含む更新より前に拒否する。
        """
        with _edit_context("mlibAnimCurveSetTangent", fast):
            allowed = {"inTangentType", "outTangentType", "inAngle", "outAngle", "inWeight",
                       "outWeight", "lock", "weightLock", "weightedTangents"}
            if not kwargs or set(kwargs) - allowed:
                raise ValueError("Specify supported tangent flags")
            angle_unit = _angle_unit(unit)
            self._index(index)
            if fast:
                values = dict(kwargs)
                for flag in ("inTangentType", "outTangentType"):
                    if flag in values:
                        values[flag] = self._tangent_type(values[flag], incoming=flag == "inTangentType")
                for flag in ("inAngle", "outAngle", "inWeight", "outWeight"):
                    if flag in values:
                        values[flag] = self._finite(values[flag])
                if any(values.get(flag, 0) < 0 for flag in ("inWeight", "outWeight")):
                    raise ValueError("Tangent weights cannot be negative")
                self._require_curve_writable()
                fn = self._curve_fn()
                if "weightedTangents" in values:
                    # keyTangentはこの全体モード指定がある場合、同時のキー別旗を適用しない。
                    fn.setIsWeighted(bool(values["weightedTangents"]))
                    return self
                if "lock" in values:
                    fn.setTangentsLocked(index, bool(values["lock"]))
                if "weightLock" in values:
                    fn.setWeightsLocked(index, bool(values["weightLock"]))
                for side, incoming, setter in (("in", True, fn.setInTangentType), ("out", False, fn.setOutTangentType)):
                    if side + "TangentType" in values:
                        setter(index, values[side + "TangentType"])
                    if side + "Angle" in values or side + "Weight" in values:
                        angle, weight = fn.getTangentAngleWeight(index, incoming)
                        if side + "Angle" in values:
                            angle = om2.MAngle(_to_radians(values[side + "Angle"], angle_unit), om2.MAngle.kRadians)
                        fn.setTangent(index, angle, values.get(side + "Weight", weight), incoming)
                return self
            kwargs = dict(kwargs)
            for flag in ("inAngle", "outAngle"):
                if flag in kwargs:
                    kwargs[flag] = angleToUi(kwargs[flag], unit=angle_unit)
            cmds.keyTangent(self.getFullName(), edit=True, index=self._index(index), animation="objects", **kwargs)
            return self

    def getInfinity(self):
        """pre/postをキーとした外挿方法名。

        Returns:
            dict: pre/postをキーとした外挿方法名。
        """
        names = {0: "constant", 1: "linear", 3: "cycle", 4: "cycleRelative", 5: "oscillate"}
        return {key: names[self.getPlug(key + "Infinity").get()]
                for key in ("pre", "post")}

    def setInfinity(self, *, pre=None, post=None, fast=False):
        """指定した側だけ外挿方法を変更する。省略した側は維持する。

        Args:
            pre (str | None): constant/linear/cycle/cycleRelative/oscillate。
                Noneは変更しない。
            post (str | None): preと同じ選択肢。Noneは変更しない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            AnimCurve: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 指定した外挿方法が不正な場合。両側を変更前に検証する。
            RuntimeError: ノードが無効、または更新先がロック・接続などで書込み不可の場合。
        """
        with _edit_context("mlibAnimCurveSetInfinity", fast):
            allowed = {"constant": 0, "linear": 1, "cycle": 3, "cycleRelative": 4, "oscillate": 5}
            values = {key: value for key, value in (("pre", pre), ("post", post)) if value is not None}
            if any(not isinstance(value, str) or value not in allowed for value in values.values()):
                raise ValueError("Unsupported infinity type")
            targets = [(self.getPlug(key + "Infinity"), allowed[value]) for key, value in values.items()]
            if fast:
                # 片側を書いた後にもう片側のロック・接続で失敗しないよう先に確認する。
                for plug, value in targets:
                    plug._require_writable()
            for plug, value in targets:
                plug.set(value, fast=fast)
            return self

    def moveKey(self, index=None, *, time=None, timeOffset=0, valueOffset=0, unit="deg", timeUnit="frame"):
        """キーの入力(時刻)と値をずらす。index・timeを両方省略すると全キーを動かす。

        Mayaの ``keyframe -edit -relative`` と同じく、入力をずらしたキーは対象でない隣のキーを越えない
        (越える量は隣のキーの直前で止まる)。fast引数は持たない(範囲を1回で処理するcmds.keyframeの方が、
        キーごとにOpenMayaで書くより速い)。

        Args:
            index (int | Sequence[int] | None): 0始まりのキー番号、またはその並び。
            time (float | Sequence[float] | None): 動かすキーの入力の時刻、または両端を含む範囲
                ``(start, end)``。T型入力はtimeUnitの単位、U型入力は無次元。indexとは同時に指定できない。
            timeOffset (float): 入力の移動量。T型入力はtimeUnitの単位(既定はフレーム)、U型は無次元。
            valueOffset (float): 値の移動量。角度はunitの単位(既定は度)、距離cm、時間はtimeUnitの単位。
            unit (str): 角度出力(A型)のvalueOffsetの単位。``"deg"`` / ``"rad"``。
            timeUnit (str): T型入力のtime・timeOffsetと、時間出力のvalueOffsetの単位。``"frame"`` / ``"sec"``。

        Returns:
            AnimCurve: 自身。対象のキーが無ければ変更しない。

        Raises:
            TypeError: indexとtimeの両方を指定した、unit・timeUnitが文字列以外、または数値へ変換できない型の場合。
            ValueError: 非有限値、範囲の開始が終了より大きい、またはunit・timeUnitが未対応の単位名の場合。
            IndexError: indexが範囲外の場合。
        """
        if index is not None and time is not None:
            raise TypeError("Specify at most one of index and time")
        with undoChunk("mlibAnimCurveMoveKey"):
            angle_unit = self._output_angle_unit(unit)
            input_unit, output_unit = self._input_time_unit(timeUnit), self._output_time_unit(timeUnit)
            timeOffset = _to_seconds(self._finite(timeOffset), input_unit)
            valueOffset = _to_seconds(_to_radians(self._finite(valueOffset), angle_unit), output_unit)
            x = self._unit_value(timeOffset)
            y = self._unit_value(valueOffset, output=True)
            ranges = self._key_ranges(index, time, timeUnit)
            if ranges:
                flag = "timeChange" if self.isTimeInput() else "floatChange"
                # 範囲を省くと、キーが1つだけのカーブをMayaが動かさないため、キーを番号で指定する。
                cmds.keyframe(self.getFullName(), edit=True, relative=True, animation="objects",
                              index=ranges, valueChange=y, **{flag: x})
            return self

    def scaleKey(self, inputScale=1, valueScale=1, inputPivot=0, valuePivot=0, *, index=None, time=None,
                 unit="deg", timeUnit="frame"):
        """キーを基準値のまわりで拡縮する。index・timeを両方省略すると全キー。接線処理はMayaのscaleKeyに従う。

        fast引数は持たない(:meth:`moveKey` と同じ理由)。

        Args:
            inputScale (float): 横軸倍率(単位なし)。0はキーが重なるためValueError。
            valueScale (float): 縦軸倍率(単位なし)。
            inputPivot (float): 横軸の基準値。T型入力はtimeUnitの単位(既定はフレーム)、U型は無次元。
            valuePivot (float): 縦軸の基準値。角度出力(A型)はunitの単位(既定は度)、時間出力はtimeUnitの単位。
            index (int | Sequence[int] | None): 0始まりのキー番号、またはその並び。
            time (float | Sequence[float] | None): 拡縮するキーの入力の時刻、または両端を含む範囲。
                indexとは同時に指定できない。
            unit (str): 角度出力のvaluePivotの単位。``"deg"`` / ``"rad"``。
            timeUnit (str): T型入力のtime・inputPivotと、時間出力のvaluePivotの単位。``"frame"`` / ``"sec"``。

        Returns:
            AnimCurve: 自身。

        Raises:
            TypeError: indexとtimeの両方を指定した、unit・timeUnitが文字列以外、または数値へ変換できない型の場合。
            ValueError: inputScaleが0、非有限値、またはunit・timeUnitが未対応の単位名の場合。
            IndexError: indexが範囲外の場合。
        """
        if index is not None and time is not None:
            raise TypeError("Specify at most one of index and time")
        with undoChunk("mlibAnimCurveScaleKey"):
            angle_unit = self._output_angle_unit(unit)
            input_unit, output_unit = self._input_time_unit(timeUnit), self._output_time_unit(timeUnit)
            x, y, px, py = map(self._finite, (inputScale, valueScale, inputPivot, valuePivot))
            px = _to_seconds(px, input_unit)
            py = _to_seconds(_to_radians(py, angle_unit), output_unit)
            if not x:
                raise ValueError("Input scale cannot be zero")
            px, py = self._unit_value(px), self._unit_value(py, output=True)
            ranges = self._key_ranges(index, time, timeUnit)
            if ranges:
                prefix = "time" if self.isTimeInput() else "float"
                # moveKey と同じく、キーが1つだけのカーブも拡縮するようキーを番号で指定する。
                cmds.scaleKey(self.getFullName(), animation="objects", index=ranges, valueScale=y,
                              valuePivot=py, **{prefix + "Scale": x, prefix + "Pivot": px})
            return self

    def mirror(self, input=False, value=True, inputPivot=0, valuePivot=0, *, index=None, time=None, unit="deg",
               timeUnit="frame"):
        """入力軸・出力軸を反転する。内部のscaleKeyでUndoをまとめる。fast引数は持たない(:meth:`scaleKey` と同じ)。

        Args:
            input (bool): 横軸を反転するか。
            value (bool): 縦軸を反転するか。
            inputPivot (float): 横軸の反転中心。T型入力はtimeUnitの単位(既定はフレーム)、U型は無次元。
            valuePivot (float): 縦軸の反転中心。角度出力(A型)はunitの単位(既定は度)、時間出力はtimeUnitの単位。
            index (int | Sequence[int] | None): 反転するキーの番号。index・timeの両方の省略は全キー。
            time (float | Sequence[float] | None): 反転するキーの入力の時刻、または両端を含む範囲。
            unit (str): 角度出力のvaluePivotの単位。``"deg"`` / ``"rad"``。
            timeUnit (str): T型入力のinputPivotと、時間出力のvaluePivotの単位。``"frame"`` / ``"sec"``。

        Returns:
            AnimCurve: 自身。
        """
        return self.scaleKey(-1 if input else 1, -1 if value else 1, inputPivot, valuePivot, index=index,
                             time=time, unit=unit, timeUnit=timeUnit)

    def getDrivenPlugs(self):
        """このカーブが動かしているアトリビュート(unitConversion等の変換ノードを飛ばした先)を返す。

        Returns:
            list[Plug]: ``output`` の出力先。つながっていなければ空リスト。

        Raises:
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        self._require_valid("access attributes of")
        return list(self.getPlug("output").getDestinations(skipConversionNodes=True))

    def getKeyframe(self, index):
        """指定番号のキーの参照を返す。

        Args:
            index (int): 0始まりの既存キー番号。

        Returns:
            Keyframe: このカーブと番号を保つ参照。

        Raises:
            IndexError: bool、非int、負値、またはキー数以上の番号の場合。
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        self._require_valid("access attributes of")
        self._index(index)
        return Keyframe(self, index)

    def getKeyframes(self, indices=None):
        """キーの参照の集まりを返す。

        Args:
            indices (Iterable[int] | None): 0始まりのキー番号の並び。Noneは全キー。

        Returns:
            Keyframes: このカーブのキーの集まり(番号の昇順、重複なし)。

        Raises:
            IndexError: 範囲外の番号を含む場合。
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        self._require_valid("access attributes of")
        if indices is None:
            indices = range(self.getKeyCount())
        indices = list(indices)
        for index in indices:
            self._index(index)
        return Keyframes([Keyframe(self, index) for index in indices])

    def _set_key_values(self, indices, value, *, unit="deg", timeUnit="frame", fast=False):
        """指定番号のキーの値を、接線型を保ったまま変える(:class:`~mlib.common.keyframe.Keyframe` の入口)。

        Args:
            indices (int | Sequence[int]): 0始まりのキー番号。
            value (float): 新しい値。単位は :meth:`setKey` と同じ。
            unit (str): 角度出力(A型)の値の単位。
            timeUnit (str): 時間出力の値の単位。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            AnimCurve: 自身。
        """
        with _edit_context("mlibAnimCurveSetKeyValue", fast):
            angle_unit = self._output_angle_unit(unit)
            output_unit = self._output_time_unit(timeUnit)
            value = _to_seconds(_to_radians(self._finite(value), angle_unit), output_unit)
            ranges = self._key_ranges(indices, None, timeUnit)
            if not ranges:
                return self
            if fast:
                self._require_curve_writable()
                fn = self._curve_fn()
                for start, end in ranges:
                    for key in range(start, end + 1):
                        self._set_api_value(fn, key, value)
                return self
            cmds.keyframe(self.getFullName(), edit=True, absolute=True, animation="objects", index=ranges,
                          valueChange=self._unit_value(value, output=True))
            return self

    @contextmanager
    def _kept_curve(self):
        """全キーの削除でMayaがカーブを消さないよう、その間だけノードをロックする。

        ``cmds.cutKey`` は空になったカーブ(つながっていないものも)を削除するが、ロックしたノードは
        削除しない。ロックの変更もUndoへ記録され、呼び出し側のチャンクにまとまる。
        """
        name = self.getFullName()
        locked = cmds.lockNode(name, query=True, lock=True)[0]
        if not locked:
            cmds.lockNode(name, lock=True)
        try:
            yield
        finally:
            if not locked:
                cmds.lockNode(name, lock=False)

    def _set_api_value(self, fn, index, value):
        """キー値を直接更新し、時間出力の秒をMTimeで保持する。

        Args:
            fn (oma2.MFnAnimCurve): 更新対象カーブ。
            index (int): キー番号。
            value (float): 内部単位の値。

        Returns:
            None: 値を返さない。
        """
        if self.getType().endswith("T"):
            # MFnAnimCurve.setValueは時間出力をdoubleで正しく更新できない。
            # Maya標準のtime型keyValueへ書き、既存の接線・ロックを保持する。
            self.getPlug("ktv")[index][1].set(value, timeUnit="sec", fast=True)
        else:
            fn.setValue(index, value)

    def _output_angle_unit(self, unit):
        """角度の単位名を検証し、出力が角度(A型)のカーブだけ換算する単位を返す。

        Args:
            unit (str): 角度の単位名。

        Returns:
            str: A型のカーブでは ``"deg"`` / ``"rad"``、それ以外は換算しない ``"rad"``。

        Raises:
            TypeError: unitが文字列以外の場合。
            ValueError: unitが未対応の単位名の場合。
        """
        angle_unit = _angle_unit(unit)
        # 削除済みのカーブでは、他のメソッドと同じ文言のRuntimeErrorにする。
        self._require_valid("access attributes of")
        return angle_unit if self.getType().endswith("A") else "rad"

    def _input_time_unit(self, time_unit):
        """時間の単位名を検証し、入力が時間(T型)のカーブだけ換算する単位を返す。

        Args:
            time_unit (str): 時間の単位名。

        Returns:
            str: T型入力のカーブでは ``"frame"`` / ``"sec"``、U型入力では換算しない ``"sec"``。

        Raises:
            TypeError: time_unitが文字列以外の場合。
            ValueError: time_unitが未対応の単位名の場合。
        """
        time_unit = _time_unit(time_unit)
        return time_unit if self.isTimeInput() else "sec"

    def _output_time_unit(self, time_unit):
        """時間の単位名を検証し、出力が時間(TT・UT型)のカーブだけ換算する単位を返す。

        Args:
            time_unit (str): 時間の単位名。

        Returns:
            str: 時間出力のカーブでは ``"frame"`` / ``"sec"``、それ以外は換算しない ``"sec"``。

        Raises:
            TypeError: time_unitが文字列以外の場合。
            ValueError: time_unitが未対応の単位名の場合。
        """
        time_unit = _time_unit(time_unit)
        self._require_valid("access attributes of")
        return time_unit if self.getType().endswith("T") else "sec"

    def _curve_fn(self):
        """保持ノードのAPI 2.0カーブ関数セットを返す。

        削除済みの MObject へ関数セットを作るとMayaが異常終了するため、先に有効性を検査する。

        Returns:
            oma2.MFnAnimCurve: 有効なカーブの関数セット。

        Raises:
            RuntimeError: ノードが無効(削除済み)の場合。
        """
        self._require_valid("access attributes of")
        return oma2.MFnAnimCurve(self.mnode())

    def _api_input(self, value):
        """内部単位の入力をAPIが要求する時間値または数値へ変換する。"""
        return om2.MTime(value, om2.MTime.kSeconds) if self.isTimeInput() else value

    @staticmethod
    def _api_number(value):
        """時間値を秒、その他を数値として返す。"""
        return value.asUnits(om2.MTime.kSeconds) if isinstance(value, om2.MTime) else float(value)

    @staticmethod
    def _tangent_type(name, *, incoming=False, key=False):
        """Mayaの接線名を変換し、直接更新できない組合せを更新前に拒否する。

        Args:
            name (str): Maya標準の接線型名。
            incoming (bool): 入力接線として解釈するか。
            key (bool): setKeyでキーを作成・更新するか。
        """
        if not isinstance(name, str) or name.lower() not in _TANGENT_TYPES:
            raise ValueError(f"Unsupported tangent type: {name!r}")
        name = name.lower()
        if key and name == "fixed":
            raise ValueError("setKey cannot use fixed tangents; use setTangent")
        if incoming and name == "stepnext":
            raise NotImplementedError("fast setKey does not support incoming stepnext tangents")
        if incoming and name == "step":
            name = "auto"
        return _TANGENT_TYPES[name]

    @staticmethod
    def _tangent_name(value):
        """API接線型をMayaのコマンド表記へ変換する。"""
        # 未登録のCustom/Shared番号はMayaのkeyTangent照会も空文字を返す。
        return _TANGENT_NAMES.get(value, "")

    def _require_curve_writable(self):
        """直接編集前に、キーを格納するアトリビュート(keyTimeValue)のロック・入力接続を検査する。

        全キーの要素を調べるとキー数に比例して遅くなる(キーを打つたびに全要素を調べる)ため、
        マルチアトリビュート自体だけを調べる。要素ごとのロックはcmds.setKeyframeでもエラーにならない。

        Raises:
            RuntimeError: ノードが無効、またはkeyTimeValueがロック・入力接続されている場合。
        """
        self._require_valid("access attributes of")
        require_writable(self._dependency_fn().findPlug("keyTimeValue", False))

    def _unit_value(self, value, output=False, to_ui=True):
        """カーブの入出力アトリビュート定義に従い、コマンド境界で単位を変換する。

        Args:
            value (float): 変換する値。
            output (bool): Trueはoutput、Falseはinputの定義を使う。
            to_ui (bool): Trueは内部単位からUI単位、FalseはUI単位から内部単位へ変換する。

        Returns:
            float: 単位型に応じた値。無次元のアトリビュートでは値をそのまま使う。
        """
        name = "output" if output else "input"
        if self.isValid():
            # getPlug(name).mplug() と同じ findPlug の結果を、Plugラッパーを作らずに使う。
            # 解決できない場合と無効なノードは、従来どおりgetPlugの結果・例外に委ねる。
            try:
                mplug = self._dependency_fn().findPlug(name, False)
            except RuntimeError:
                mplug = None
            if mplug is not None:
                return _convert_units(mplug, value, to_ui)
        return _convert_units(self.getPlug(name).mplug(), value, to_ui)

    @staticmethod
    def _finite(value):
        """キーや接線の入力をfloatへ変換し、非有限値を拒否する。

        float()に従うため、変換可能な数値文字列やboolもここでは受理する。
        キー番号などの厳密なint検証とは別の責務とする。

        Args:
            value (object): float()へ渡す値。

        Returns:
            float: 有限な値。

        Raises:
            TypeError: float()が受理しない型の場合。
            ValueError: 変換できない文字列など、またはNaN/正負の無限大の場合。
        """
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Expected a finite value")
        return value

    def _time_span(self, time, time_unit):
        """入力の時刻・範囲を、その中にあるキーの番号の範囲へ変換する。

        Args:
            time (float | Sequence[float]): 時刻、または両端を含む範囲。
            time_unit (str): T型入力のtimeの単位。

        Returns:
            tuple[int, int] | None: 最初と最後のキー番号。範囲内にキーが無ければNone。

        Raises:
            TypeError: timeが数値・2つの数値の並び以外の場合。
            ValueError: 有限でない、開始が終了より大きい、またはtime_unitが未対応の単位名の場合。
        """
        unit = self._input_time_unit(time_unit)
        values = tuple(time) if isinstance(time, (tuple, list)) else (time, time)
        if len(values) != 2:
            raise TypeError("time must be a number or a (start, end) pair")
        start, end = (_to_seconds(self._finite(value), unit) for value in values)
        if start > end:
            raise ValueError(f"time range start must not be greater than end: {values}")
        # 浮動小数の誤差でちょうど端のキーを落とさないよう、わずかに広げて比べる。
        tolerance = 1e-9 * max(1.0, abs(start), abs(end))
        inside = [key for key, value in enumerate(self.getKeyInputs(timeUnit="sec"))
                  if start - tolerance <= value <= end + tolerance]
        return (inside[0], inside[-1]) if inside else None

    def _key_ranges(self, index, time, time_unit):
        """index・timeの指定を、``cmds.keyframe`` の ``index`` フラグに渡す番号の範囲の並びへ変換する。

        Args:
            index (int | Iterable[int] | None): キー番号、またはその並び。
            time (float | Sequence[float] | None): 入力の時刻、または両端を含む範囲。
            time_unit (str): T型入力のtimeの単位。

        Returns:
            list[tuple[int, int]]: 昇順で重ならない ``(最初, 最後)`` の並び。両方Noneは全キー、該当なしは空。

        Raises:
            IndexError: 範囲外の番号を含む場合。
        """
        if time is not None:
            span = self._time_span(time, time_unit)
            return [span] if span is not None else []
        if index is None:
            count = self.getKeyCount()
            return [(0, count - 1)] if count else []
        numbers = list(index) if isinstance(index, (list, tuple, range)) else [index]
        for number in numbers:
            self._index(number)
        ranges = []
        for number in sorted(set(numbers)):
            if ranges and ranges[-1][1] + 1 == number:
                ranges[-1] = (ranges[-1][0], number)
            else:
                ranges.append((number, number))
        return ranges

    def _index(self, index):
        """0始まりの既存キー番号を検証し、cmdsの単一キー範囲へ変換する。

        Args:
            index (int): boolを除くint。負値による末尾参照は受け付けない。

        Returns:
            tuple[int, int]: 同じ番号を両端に持つ範囲。

        Raises:
            IndexError: 非int、bool、負値、または現在のキー数以上の場合。
        """
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < self.getKeyCount():
            raise IndexError("Key index is out of range")
        return (index, index)
