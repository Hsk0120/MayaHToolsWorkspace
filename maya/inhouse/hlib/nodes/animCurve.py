"""アニメーションカーブの共通操作。編集はMayaコマンドでUndoに対応する。"""

import math

import maya.cmds as cmds

from .._core.flags import flag_aliases
from .._core.getterAlias import _getter_alias
from .._core.unitValue import convert
from ..common._fast import fast_edit, is_fast
from ..common.units import angleToUi, angleFromUi
from ..decorator import undoChunk
from .node import Node


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
        return cmds.keyframe(self.getFullName(), query=True, keyframeCount=True) or 0

    def getKeyInputs(self):
        """キー順の入力。時間型は秒、それ以外は単位なし。

        Returns:
            list[float]: キー順の入力。時間型は秒、それ以外は単位なし。
        """
        flag = "timeChange" if self.isTimeInput() else "floatChange"
        return [self._unit_value(v, to_ui=False) for v in (cmds.keyframe(self.getFullName(), query=True, **{flag: True}) or [])]

    def getKeyValues(self):
        """キー順の出力値。角度・距離・時間は内部単位(cm/rad/秒)。

        Returns:
            list[float]: キー順の出力値。角度・距離・時間は内部単位(cm/rad/秒)。
        """
        return [self._unit_value(v, output=True, to_ui=False) for v in (cmds.keyframe(self.getFullName(), query=True, valueChange=True) or [])]

    def evaluate(self, input):
        """指定入力でカーブ単体を評価する。シーン時刻は変更しない。

        Args:
            input (float): 時間または単位なしの入力。
        Returns:
            float: 評価値。空カーブはRuntimeError。
        """
        value = self._unit_value(self._finite(input))
        flag = "time" if self.isTimeInput() else "float"
        result = cmds.keyframe(self.getFullName(), query=True, eval=True, **{flag: (value, value)})
        if not result:
            raise RuntimeError("Cannot evaluate an empty curve")
        return self._unit_value(result[0], output=True, to_ui=False)

    @undoChunk("hlibAnimCurveSetKey")
    def setKey(self, input, value, inTangentType="linear", outTangentType="linear"):
        """キーを追加、同じ入力位置なら更新する。

        Args:
            input (float): 時間または単位なしの入力。
            value (float): 内部単位(cm/rad/秒)の出力。
            inTangentType (str): Mayaの入力接線型。
            outTangentType (str): Mayaの出力接線型。
        Returns:
            AnimCurve: 自身。fixed接線の詳細設定にはsetTangentを使う。
        """
        position = self._unit_value(self._finite(input))
        value = self._unit_value(self._finite(value), output=True)
        flag = "time" if self.isTimeInput() else "float"
        cmds.setKeyframe(self.getFullName(), value=value, inTangentType=inTangentType,
                        outTangentType=outTangentType, **{flag: position})
        return self

    @flag_aliases(idx="index")
    @undoChunk("hlibAnimCurveRemoveKey")
    def removeKey(self, index):
        """指定番号のキーを削除する。キークリップボードは変更しない。

        Args:
            index (int): 0始まりのキー番号。 別名 ``idx`` も使用可能。
        Returns:
            AnimCurve: 自身。
        """
        cmds.cutKey(self.getFullName(), index=self._index(index), clear=True, animation="objects")
        return self

    @flag_aliases(idx="index")
    def getTangent(self, index):
        """指定キーの接線情報を取得する。

        Args:
            index (int): 0始まりのキー番号。 別名 ``idx`` も使用可能。
        Returns:
            dict: Mayaの接線フラグ名をキーとした型・角度・ウェイト・ロック情報。
        """
        span = self._index(index)
        result = {flag: cmds.keyTangent(self.getFullName(), query=True, index=span, **{flag: True})[0]
                for flag in ("inTangentType", "outTangentType", "inAngle", "outAngle",
                             "inWeight", "outWeight", "lock", "weightLock", "weightedTangents")}
        for flag in ("inAngle", "outAngle"):
            result[flag] = angleFromUi(result[flag])
        return result

    @flag_aliases(idx="index")
    @undoChunk("hlibAnimCurveSetTangent")
    def setTangent(self, index, **kwargs):
        """キーの接線を変更する。Mayaの接線ロック規則に従う。

        Args:
            index (int): 0始まりのキー番号。 別名 ``idx`` も使用可能。
            **kwargs: getTangent()で返すキーと同名のMayaフラグ。
                weightedTangentsはカーブ全体に適用される。
        Returns:
            AnimCurve: 自身。未知のフラグはValueError。
        """
        allowed = {"inTangentType", "outTangentType", "inAngle", "outAngle", "inWeight",
                   "outWeight", "lock", "weightLock", "weightedTangents"}
        if not kwargs or set(kwargs) - allowed:
            raise ValueError("Specify supported tangent flags")
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

    @fast_edit
    @undoChunk("hlibAnimCurveInfinity")
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
        if is_fast():
            # 片側を書いた後にもう片側のロック・接続で失敗しないよう先に確認する。
            for plug, value in targets:
                plug._require_writable()
        for plug, value in targets:
            plug.set(value)
        return self

    @undoChunk("hlibAnimCurveShift")
    def shiftKeys(self, input_offset=0, value_offset=0):
        """全キーを移動する。

        Args:
            input_offset (float): 横軸の移動量。時間型は秒。
            value_offset (float): 縦軸の移動量。内部単位(cm/rad/秒)。
        Returns:
            AnimCurve: 自身。空カーブは変更しない。
        """
        x = self._unit_value(self._finite(input_offset))
        y = self._unit_value(self._finite(value_offset), output=True)
        if self.getKeyCount():
            flag = "timeChange" if self.isTimeInput() else "floatChange"
            cmds.keyframe(self.getFullName(), edit=True, relative=True, animation="objects",
                          valueChange=y, **{flag: x})
        return self

    @undoChunk("hlibAnimCurveScale")
    def scaleKeys(self, input_scale=1, value_scale=1, input_pivot=0, value_pivot=0):
        """全キーを基準値のまわりで拡縮する。接線処理はMayaのscaleKeyに従う。

        Args:
            input_scale (float): 横軸倍率。0はキーが重なるためValueError。
            value_scale (float): 縦軸倍率。
            input_pivot (float): 横軸の基準値。
            value_pivot (float): 縦軸の基準値。
        Returns:
            AnimCurve: 自身。
        """
        x, y, px, py = map(self._finite, (input_scale, value_scale, input_pivot, value_pivot))
        px, py = self._unit_value(px), self._unit_value(py, output=True)
        if not x:
            raise ValueError("Input scale cannot be zero")
        if self.getKeyCount():
            prefix = "time" if self.isTimeInput() else "float"
            cmds.scaleKey(self.getFullName(), animation="objects", valueScale=y, valuePivot=py,
                          **{prefix + "Scale": x, prefix + "Pivot": px})
        return self

    def mirror(self, input=False, value=True, input_pivot=0, value_pivot=0):
        """入力軸・出力軸を反転する。内部のscaleKeysでUndoをまとめる。

        Args:
            input (bool): 横軸を反転するか。
            value (bool): 縦軸を反転するか。
            input_pivot (float): 横軸の反転中心。
            value_pivot (float): 縦軸の反転中心。
        Returns:
            AnimCurve: 自身。
        """
        return self.scaleKeys(-1 if input else 1, -1 if value else 1, input_pivot, value_pivot)

    def getDriverPlug(self):
        """inputの直接接続元。時間型では通常timeノード。

        Returns:
            Plug | None: inputの直接接続元。時間型では通常timeノード。
        """
        return self.getPlug("input").getSourceWithConversion()

    def getOutputPlug(self):
        """出力プラグ。

        Returns:
            Plug: 出力プラグ。
        """
        return self.getPlug("output")

    def getDrivenPlugs(self):
        """直接の出力接続先。変換・合成ノード越しの探索はしない。

        Returns:
            list[Plug]: 直接の出力接続先。変換・合成ノード越しの探索はしない。
        """
        return self.getOutputPlug().getDestinationsWithConversions()

    @_getter_alias(getKeyCount)
    def keyCount(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getKeyCount(*args, **kwargs)

    @_getter_alias(getKeyInputs)
    def keyInputs(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getKeyInputs(*args, **kwargs)

    @_getter_alias(getKeyValues)
    def keyValues(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getKeyValues(*args, **kwargs)

    @_getter_alias(getTangent)
    def tangent(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getTangent(*args, **kwargs)

    @_getter_alias(getInfinity)
    def infinity(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getInfinity(*args, **kwargs)

    @_getter_alias(getDriverPlug)
    def driverPlug(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getDriverPlug(*args, **kwargs)

    @_getter_alias(getOutputPlug)
    def outputPlug(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getOutputPlug(*args, **kwargs)

    @_getter_alias(getDrivenPlugs)
    def drivenPlugs(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getDrivenPlugs(*args, **kwargs)

    def _unit_value(self, value, output=False, to_ui=True):
        """入出力の単位型に従いコマンド境界で値を変換する。

        Args:
            value: 変換・設定する入力値。
            output: Trueは出力側、Falseは入力側を扱う。
            to_ui: Trueは内部単位からUI単位、Falseは逆方向へ変換する。
        """
        return convert(self.getPlug("output" if output else "input").mplug(), value, to_ui)

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
