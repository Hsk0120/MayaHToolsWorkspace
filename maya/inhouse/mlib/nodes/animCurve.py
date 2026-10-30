"""アニメーションカーブの共通操作。通常編集はUndo、fastはAPI直接更新。"""

import math

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds

from ..common.units import angleToUi
from ..core.attributeType import _convert_units, _from_seconds, _to_seconds
from ..core.fastWrite import require_writable
from ..decorator import _edit_context, _require_bool
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

    def setKey(self, input, value, inTangentType="linear", outTangentType="linear", *, unit="deg", timeUnit="frame",
               fast=False):
        """キーを追加する。同じ入力位置にキーがあれば値と接線型を更新する。

        通常はUI単位へ換算してsetKeyframeを呼ぶ。fastの既存キーは値→入力接線型→出力接線型の
        順に更新する。新規キーは両接線型を指定し、時間出力の値は追加後に設定する。
        後続の失敗で先行の変更を自動復元しない。

        Args:
            input (float): T型入力はtimeUnitの単位(既定はフレーム)、U型入力は無次元。
            value (float): 出力型に従う度(unit)/cm/フレーム(timeUnit)、または無次元。inputと共に有限値へ変換する。
            inTangentType (str): Mayaの入力接線型。fastのstepはautoへ補正する。
            outTangentType (str): Mayaの出力接線型。
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
                tangent_in = self._tangent_type(inTangentType, incoming=True, key=True)
                tangent_out = self._tangent_type(outTangentType, key=True)
                at = self._api_input(input)
                self._require_curve_writable()
                index = fn.find(at)
                if index is not None:
                    self._set_api_value(fn, index, value)
                    fn.setInTangentType(index, tangent_in)
                    fn.setOutTangentType(index, tangent_out)
                else:
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
            flag = "time" if self.isTimeInput() else "float"
            cmds.setKeyframe(self.getFullName(), value=value, inTangentType=inTangentType,
                            outTangentType=outTangentType, **{flag: position})
            return self

    def removeKey(self, index, *, fast=False):
        """指定番号のキーを削除する。キークリップボードは変更しない。

        Args:
            index (int): 0始まりのキー番号。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            AnimCurve: 自身。
        """
        with _edit_context("mlibAnimCurveRemoveKey", fast):
            span = self._index(index)
            if fast:
                self._require_curve_writable()
                self._curve_fn().remove(span[0])
            else:
                cmds.cutKey(self.getFullName(), index=span, clear=True, animation="objects")
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

    def shiftKeys(self, inputOffset=0, valueOffset=0, *, unit="deg", timeUnit="frame", fast=False):
        """全キーを移動する。

        Args:
            inputOffset (float): 横軸の移動量。T型入力はtimeUnitの単位(既定はフレーム)、U型は無次元。
            valueOffset (float): 縦軸の移動量。角度はunitの単位(既定は度)、距離cm、時間はtimeUnitの単位。
            unit (str): 角度出力(A型)のvalueOffsetの単位。``"deg"`` / ``"rad"``。
            timeUnit (str): T型入力のinputOffsetと、時間出力のvalueOffsetの単位。``"frame"`` / ``"sec"``。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            AnimCurve: 自身。空カーブは変更しない。

        Raises:
            TypeError: unit・timeUnitが文字列以外、または数値へ変換できない型の場合。
            ValueError: 非有限値、またはunit・timeUnitが未対応の単位名の場合。
        """
        with _edit_context("mlibAnimCurveShiftKeys", fast):
            angle_unit = self._output_angle_unit(unit)
            input_unit, output_unit = self._input_time_unit(timeUnit), self._output_time_unit(timeUnit)
            inputOffset = _to_seconds(self._finite(inputOffset), input_unit)
            valueOffset = _to_seconds(_to_radians(self._finite(valueOffset), angle_unit), output_unit)
            if fast:
                self._transform_keys(1, 1, inputOffset, valueOffset)
                return self
            x = self._unit_value(inputOffset)
            y = self._unit_value(valueOffset, output=True)
            if self.getKeyCount():
                flag = "timeChange" if self.isTimeInput() else "floatChange"
                cmds.keyframe(self.getFullName(), edit=True, relative=True, animation="objects",
                              valueChange=y, **{flag: x})
            return self

    def scaleKeys(self, inputScale=1, valueScale=1, inputPivot=0, valuePivot=0, *, unit="deg", timeUnit="frame",
                  fast=False):
        """全キーを基準値のまわりで拡縮する。接線処理はMayaのscaleKeyに従う。

        Args:
            inputScale (float): 横軸倍率(単位なし)。0はキーが重なるためValueError。
            valueScale (float): 縦軸倍率(単位なし)。
            inputPivot (float): 横軸の基準値。T型入力はtimeUnitの単位(既定はフレーム)、U型は無次元。
            valuePivot (float): 縦軸の基準値。角度出力(A型)はunitの単位(既定は度)、時間出力はtimeUnitの単位。
            unit (str): 角度出力のvaluePivotの単位。``"deg"`` / ``"rad"``。
            timeUnit (str): T型入力のinputPivotと、時間出力のvaluePivotの単位。``"frame"`` / ``"sec"``。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。負の入力倍率は更新前に未対応として拒否。

        Returns:
            AnimCurve: 自身。

        Raises:
            TypeError: unit・timeUnitが文字列以外、または数値へ変換できない型の場合。
            ValueError: inputScaleが0、非有限値、またはunit・timeUnitが未対応の単位名の場合。
            NotImplementedError: fastで負の入力倍率を指定した場合。
        """
        with _edit_context("mlibAnimCurveScaleKeys", fast):
            angle_unit = self._output_angle_unit(unit)
            input_unit, output_unit = self._input_time_unit(timeUnit), self._output_time_unit(timeUnit)
            x, y, px, py = map(self._finite, (inputScale, valueScale, inputPivot, valuePivot))
            px = _to_seconds(px, input_unit)
            py = _to_seconds(_to_radians(py, angle_unit), output_unit)
            if not x:
                raise ValueError("Input scale cannot be zero")
            if fast:
                if x < 0:
                    raise NotImplementedError("fast scaleKeys does not support a non-positive input scale")
                self._transform_keys(x, y, px * (1 - x), py * (1 - y))
                return self
            px, py = self._unit_value(px), self._unit_value(py, output=True)
            if self.getKeyCount():
                prefix = "time" if self.isTimeInput() else "float"
                cmds.scaleKey(self.getFullName(), animation="objects", valueScale=y, valuePivot=py,
                              **{prefix + "Scale": x, prefix + "Pivot": px})
            return self

    def mirror(self, input=False, value=True, inputPivot=0, valuePivot=0, *, unit="deg", timeUnit="frame",
               fast=False):
        """入力軸・出力軸を反転する。内部のscaleKeysでUndoをまとめる。

        Args:
            input (bool): 横軸を反転するか。
            value (bool): 縦軸を反転するか。
            inputPivot (float): 横軸の反転中心。T型入力はtimeUnitの単位(既定はフレーム)、U型は無次元。
            valuePivot (float): 縦軸の反転中心。角度出力(A型)はunitの単位(既定は度)、時間出力はtimeUnitの単位。
            unit (str): 角度出力のvaluePivotの単位。``"deg"`` / ``"rad"``。
            timeUnit (str): T型入力のinputPivotと、時間出力のvaluePivotの単位。``"frame"`` / ``"sec"``。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。input=Trueとの併用は未対応。

        Returns:
            AnimCurve: 自身。
        """
        _require_bool(fast, "fast")
        return self.scaleKeys(-1 if input else 1, -1 if value else 1, inputPivot, valuePivot, unit=unit,
                              timeUnit=timeUnit, fast=fast)

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

    def _transform_keys(self, x_scale, y_scale, x_offset, y_offset):
        """キー順を保つ移動・拡縮をAPIで実行し固定接線を追従させる。

        Args:
            x_scale (float): 正の入力倍率。
            y_scale (float): 出力倍率。
            x_offset (float): 内部単位の入力オフセット。
            y_offset (float): 内部単位の出力オフセット。

        Returns:
            None: 値を返さない。
        """
        self._require_curve_writable()
        fn = self._curve_fn()
        inputs, values = self.getKeyInputs(timeUnit="sec"), self.getKeyValues(unit="rad", timeUnit="sec")
        targets = [x * x_scale + x_offset for x in inputs]
        outputs = [y * y_scale + y_offset for y in values]
        if not all(math.isfinite(v) for v in targets + outputs):
            raise ValueError("Key transform must produce finite values")
        tangents = [(fn.inTangentType(i), fn.outTangentType(i),
                     fn.getTangentAngleWeight(i, True), fn.getTangentAngleWeight(i, False),
                     fn.tangentsLocked(i), fn.weightsLocked(i)) for i in range(fn.numKeys)]
        # 左へ動くキーは先頭から、右へ動くキーは末尾から更新し、途中の交差を避ける。
        # 同じ入力のsetInputはMayaが不正な範囲として拒否するため変更しない。
        order = ([i for i in range(fn.numKeys) if targets[i] < inputs[i]] +
                 [i for i in reversed(range(fn.numKeys)) if targets[i] > inputs[i]])
        for i in order:
            fn.setInput(i, self._api_input(targets[i]))
        for i, value in enumerate(outputs):
            self._set_api_value(fn, i, value)
        if x_scale == 1 and y_scale == 1:
            return
        for i, (incoming_type, outgoing_type, incoming, outgoing, locked, weights_locked) in enumerate(tangents):
            if (incoming_type == fn.kTangentFixed or outgoing_type == fn.kTangentFixed or fn.isWeighted):
                fn.setTangentsLocked(i, False)
                fn.setWeightsLocked(i, False)
                for is_in, kind, tangent in ((True, incoming_type, incoming),
                                             (False, outgoing_type, outgoing)):
                    if kind == fn.kTangentFixed or fn.isWeighted:
                        angle, weight = tangent
                        x = math.cos(angle.asRadians()) * x_scale
                        y = math.sin(angle.asRadians()) * y_scale
                        new_angle = om2.MAngle(math.atan2(y, x), om2.MAngle.kRadians)
                        new_weight = weight * math.hypot(x, y) if fn.isWeighted else weight
                        fn.setTangent(i, new_angle, new_weight, is_in)
                    (fn.setInTangentType if is_in else fn.setOutTangentType)(i, kind)
                fn.setTangentsLocked(i, locked)
                fn.setWeightsLocked(i, weights_locked)

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
