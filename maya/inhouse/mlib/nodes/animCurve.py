"""アニメーションカーブの共通操作。通常編集はUndo、fastはAPI直接更新。"""

import math

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds

from ..common.units import angleToUi
from ..core.attributeType import _convert_units
from ..decorator import _flag_aliases, _fast_edit, _is_fast, undoChunk
from .node import Node


# コマンドの接線名を正式な入口にし、APIのSmooth等の別表記を外へ出さない。
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
_TANGENT_NAMES = {value: name for name, value in _TANGENT_TYPES.items()}


class AnimCurve(Node):
    """8種類のカーブの基底クラス。数値は内部単位(cm/rad/秒)を使う。"""

    def isTimeInput(self):
        """横軸が時間ならTrue、単位なしならFalse。

        Returns:
            bool: 横軸が時間ならTrue、単位なしならFalse。
        """
        return self.getType()[9] == "T"

    def getKeyCount(self):
        """キー数。

        Returns:
            int: キー数。
        """
        return self._curve_fn().numKeys

    def getKeyInputs(self):
        """キー順の入力。時間型は秒、それ以外は単位なし。

        Returns:
            list[float]: キー順の入力。時間型は秒、それ以外は単位なし。
        """
        fn = self._curve_fn()
        return [self._api_number(fn.input(i)) for i in range(fn.numKeys)]

    def getKeyValues(self):
        """キー順の出力値。角度・距離・時間は内部単位(cm/rad/秒)。

        Returns:
            list[float]: キー順の出力値。角度・距離・時間は内部単位(cm/rad/秒)。
        """
        fn = self._curve_fn()
        if self.getType().endswith("T"):
            return [self.getPlug("ktv")[i][1].get() for i in range(fn.numKeys)]
        return [fn.value(i) for i in range(fn.numKeys)]

    def evaluate(self, input):
        """指定入力でカーブ単体を評価する。シーン時刻は変更しない。

        Args:
            input (float): 時間または単位なしの入力。

        Returns:
            float: 評価値。空カーブはRuntimeError。
        """
        fn = self._curve_fn()
        if not fn.numKeys:
            raise RuntimeError("Cannot evaluate an empty curve")
        result = fn.evaluate(self._api_input(self._finite(input)))
        if self.getType().endswith("T") and om2.MGlobal.apiVersion() < 20240000:
            # Maya 2022/2023のPython APIは生tick数をUI単位のMTimeとして返す。
            # APIのtick周波数で秒へ戻し、正常な2024以降の返却は補正しない。
            return result.value / om2.MTime.ticksPerSecond()
        return self._api_number(result)

    @_fast_edit
    @undoChunk("mlibAnimCurveSetKey")
    def setKey(self, input, value, inTangentType="linear", outTangentType="linear", *, fast=False):
        """キーを追加、同じ入力位置なら更新する。

        Args:
            input (float): 時間または単位なしの入力。
            value (float): 内部単位(cm/rad/秒)の出力。
            inTangentType (str): Mayaの入力接線型。
            outTangentType (str): Mayaの出力接線型。
            fast (bool): TrueはAPI 2.0で直接更新し、Undo履歴を追加しない。

        Returns:
            AnimCurve: 自身。fixed接線の詳細設定にはsetTangentを使う。

        Raises:
            ValueError: fastでfixed・global・未知の接線型を指定した場合。
            NotImplementedError: fastで入力接線にstepnextを指定した場合。

        fastの入力stepはMayaと同じautoへ補正する。入力stepnextはMayaの版で
        補正が異なるため、キーを追加・変更する前に未対応として拒否する。
        """
        input, value = self._finite(input), self._finite(value)
        if _is_fast():
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

    @_flag_aliases(idx="index")
    @_fast_edit
    @undoChunk("mlibAnimCurveRemoveKey")
    def removeKey(self, index, *, fast=False):
        """指定番号のキーを削除する。キークリップボードは変更しない。

        Args:
            index (int): 0始まりのキー番号。 別名 ``idx`` も使用可能。
            fast (bool): TrueはAPI 2.0によるUndoなし削除。

        Returns:
            AnimCurve: 自身。
        """
        span = self._index(index)
        if _is_fast():
            self._require_curve_writable()
            self._curve_fn().remove(span[0])
        else:
            cmds.cutKey(self.getFullName(), index=span, clear=True, animation="objects")
        return self

    @_flag_aliases(idx="index")
    def getTangent(self, index):
        """指定キーの接線情報を取得する。

        Args:
            index (int): 0始まりのキー番号。 別名 ``idx`` も使用可能。

        Returns:
            dict: Mayaの接線フラグ名をキーとした型・角度・ウェイト・ロック情報。
        """
        self._index(index)
        fn = self._curve_fn()
        incoming = fn.getTangentAngleWeight(index, True)
        outgoing = fn.getTangentAngleWeight(index, False)
        return {"inTangentType": self._tangent_name(fn.inTangentType(index)),
                "outTangentType": self._tangent_name(fn.outTangentType(index)),
                "inAngle": incoming[0].asRadians(), "outAngle": outgoing[0].asRadians(),
                "inWeight": incoming[1], "outWeight": outgoing[1],
                "lock": fn.tangentsLocked(index), "weightLock": fn.weightsLocked(index),
                "weightedTangents": fn.isWeighted}

    @_flag_aliases(idx="index")
    @_fast_edit
    @undoChunk("mlibAnimCurveSetTangent")
    def setTangent(self, index, *, fast=False, **kwargs):
        """キーの接線を変更する。Mayaの接線ロック規則に従う。

        Args:
            index (int): 0始まりのキー番号。 別名 ``idx`` も使用可能。
            fast (bool): TrueはAPI 2.0で直接接線を更新する。
            **kwargs: getTangent()で返すキーと同名のMayaフラグ。
                weightedTangentsはカーブ全体に適用される。

        Returns:
            AnimCurve: 自身。未知のフラグはValueError。

        Raises:
            ValueError: fastでglobal・未知の接線型を指定した場合。
            NotImplementedError: fastで入力接線にstepnextを指定した場合。

        fastの入力stepはMayaと同じautoへ補正する。入力stepnextはMayaの版で
        補正が異なるため、ロック・ウェイトを含む更新の前に拒否する。
        """
        allowed = {"inTangentType", "outTangentType", "inAngle", "outAngle", "inWeight",
                   "outWeight", "lock", "weightLock", "weightedTangents"}
        if not kwargs or set(kwargs) - allowed:
            raise ValueError("Specify supported tangent flags")
        self._index(index)
        if _is_fast():
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
                    angle = om2.MAngle(values[side + "Angle"], om2.MAngle.kRadians) if side + "Angle" in values else angle
                    fn.setTangent(index, angle, values.get(side + "Weight", weight), incoming)
            return self
        kwargs = dict(kwargs)
        for flag in ("inAngle", "outAngle"):
            if flag in kwargs:
                kwargs[flag] = angleToUi(kwargs[flag])
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

    @_fast_edit
    @undoChunk("mlibAnimCurveInfinity")
    def setInfinity(self, *, pre=None, post=None, fast=False):
        """指定した側だけ外挿方法を変更する。省略した側は維持する。

        Args:
            pre (str | None): constant/linear/cycle/cycleRelative/oscillate。
                Noneは変更しない。
            post (str | None): preと同じ選択肢。Noneは変更しない。
            fast (bool): Trueはom2で直接更新し、Undoなし。既定Falseはcmdsで更新。

        Returns:
            AnimCurve: 自身。

        Raises:
            ValueError: 指定した外挿方法が不正な場合。両側を変更前に検証する。
            TypeError: fastがboolでない場合。
            RuntimeError: ノードが無効、または更新先がロック・接続などで書込み不可の場合。
        """
        allowed = {"constant": 0, "linear": 1, "cycle": 3, "cycleRelative": 4, "oscillate": 5}
        values = {key: value for key, value in (("pre", pre), ("post", post)) if value is not None}
        if any(not isinstance(value, str) or value not in allowed for value in values.values()):
            raise ValueError("Unsupported infinity type")
        targets = [(self.getPlug(key + "Infinity"), allowed[value]) for key, value in values.items()]
        if _is_fast():
            # 片側を書いた後にもう片側のロック・接続で失敗しないよう先に確認する。
            for plug, value in targets:
                plug._require_writable()
        for plug, value in targets:
            plug.set(value)
        return self

    @_fast_edit
    @undoChunk("mlibAnimCurveShift")
    def shiftKeys(self, input_offset=0, value_offset=0, *, fast=False):
        """全キーを移動する。

        Args:
            input_offset (float): 横軸の移動量。時間型は秒。
            value_offset (float): 縦軸の移動量。内部単位(cm/rad/秒)。
            fast (bool): TrueはAPI直接更新でUndoなし。

        Returns:
            AnimCurve: 自身。空カーブは変更しない。
        """
        input_offset, value_offset = self._finite(input_offset), self._finite(value_offset)
        if _is_fast():
            self._transform_keys(1, 1, input_offset, value_offset)
            return self
        x = self._unit_value(input_offset)
        y = self._unit_value(value_offset, output=True)
        if self.getKeyCount():
            flag = "timeChange" if self.isTimeInput() else "floatChange"
            cmds.keyframe(self.getFullName(), edit=True, relative=True, animation="objects",
                          valueChange=y, **{flag: x})
        return self

    @_fast_edit
    @undoChunk("mlibAnimCurveScale")
    def scaleKeys(self, input_scale=1, value_scale=1, input_pivot=0, value_pivot=0, *, fast=False):
        """全キーを基準値のまわりで拡縮する。接線処理はMayaのscaleKeyに従う。

        Args:
            input_scale (float): 横軸倍率。0はキーが重なるためValueError。
            value_scale (float): 縦軸倍率。
            input_pivot (float): 横軸の基準値。
            value_pivot (float): 縦軸の基準値。
            fast (bool): TrueはAPI直接更新。負の入力倍率は更新前に未対応として拒否。

        Returns:
            AnimCurve: 自身。
        """
        x, y, px, py = map(self._finite, (input_scale, value_scale, input_pivot, value_pivot))
        if not x:
            raise ValueError("Input scale cannot be zero")
        if _is_fast():
            if x < 0:
                raise NotImplementedError("fast scaleKeys requires a positive input scale")
            self._transform_keys(x, y, px * (1 - x), py * (1 - y))
            return self
        px, py = self._unit_value(px), self._unit_value(py, output=True)
        if self.getKeyCount():
            prefix = "time" if self.isTimeInput() else "float"
            cmds.scaleKey(self.getFullName(), animation="objects", valueScale=y, valuePivot=py,
                          **{prefix + "Scale": x, prefix + "Pivot": px})
        return self

    @_fast_edit
    def mirror(self, input=False, value=True, input_pivot=0, value_pivot=0, *, fast=False):
        """入力軸・出力軸を反転する。内部のscaleKeysでUndoをまとめる。

        Args:
            input (bool): 横軸を反転するか。
            value (bool): 縦軸を反転するか。
            input_pivot (float): 横軸の反転中心。
            value_pivot (float): 縦軸の反転中心。
            fast (bool): TrueはAPI直接更新。input=Trueとの併用は未対応。

        Returns:
            AnimCurve: 自身。
        """
        return self.scaleKeys(-1 if input else 1, -1 if value else 1, input_pivot, value_pivot)

    def _set_api_value(self, fn, index, value):
        """キー値を直接更新し、時間出力の秒をMTimeで保持する。

        Args:
            fn (oma2.MFnAnimCurve): 更新対象カーブ。
            index (int): キー番号。
            value (float): 内部単位の値。
        """
        if self.getType().endswith("T"):
            # MFnAnimCurve.setValueは時間出力をdoubleで正しく更新できない。
            # Maya標準のtime型keyValueへ書き、既存の接線・ロックを保持する。
            self.getPlug("ktv")[index][1].set(value, fast=True)
        else:
            fn.setValue(index, value)

    def _transform_keys(self, x_scale, y_scale, x_offset, y_offset):
        """キー順を保つ移動・拡縮をAPIで実行し固定接線を追従させる。

        Args:
            x_scale (float): 正の入力倍率。
            y_scale (float): 出力倍率。
            x_offset (float): 内部単位の入力オフセット。
            y_offset (float): 内部単位の出力オフセット。
        """
        self._require_curve_writable()
        fn = self._curve_fn()
        inputs, values = self.getKeyInputs(), self.getKeyValues()
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

    def _curve_fn(self):
        """保持ノードのAPI 2.0カーブ関数セットを返す。"""
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
            raise NotImplementedError("fast editing of incoming stepnext tangents is not supported")
        if incoming and name == "step":
            name = "auto"
        return _TANGENT_TYPES[name]

    @staticmethod
    def _tangent_name(value):
        """API接線型をMayaのコマンド表記へ変換する。"""
        # 未登録のCustom/Shared番号はMayaのkeyTangent照会も空文字を返す。
        return _TANGENT_NAMES.get(value, "")

    def _require_curve_writable(self):
        """直接編集前にカーブとキー格納先のロックを検査する。"""
        self.getPlug("ktv")._require_writable()

    def _unit_value(self, value, output=False, to_ui=True):
        """入出力の単位型に従いコマンド境界で値を変換する。

        Args:
            value: 変換・設定する入力値。
            output: Trueは出力側、Falseは入力側を扱う。
            to_ui: Trueは内部単位からUI単位、Falseは逆方向へ変換する。
        """
        return _convert_units(self.getPlug("output" if output else "input").mplug(), value, to_ui)

    @staticmethod
    def _finite(value):
        """有限の数値へ変換する。不正値はValueError。

        Args:
            value: 変換・設定する入力値。
        """
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Expected a finite value")
        return value

    def _index(self, index):
        """存在するキー番号を検証する。不正値はIndexError。

        Args:
            index: 対象要素の番号または探索開始番号。
        """
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < self.getKeyCount():
            raise IndexError("Key index is out of range")
        return (index, index)
