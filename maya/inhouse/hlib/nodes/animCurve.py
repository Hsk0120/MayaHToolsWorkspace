"""アニメーションカーブの共通操作。編集はMayaコマンドでUndoに対応する。"""

import math
import maya.cmds as cmds
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from .node import Node


@node_wrapper("animCurve")
class AnimCurve(Node):
    """8種類のカーブの基底クラス。数値はMayaの現在のUI単位を使う。"""

    @staticmethod
    def _finite(value):
        """有限の数値へ変換する。不正値はValueError。"""
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Expected a finite value")
        return value

    def _index(self, index):
        """存在するキー番号を検証する。不正値はIndexError。"""
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < self.key_count():
            raise IndexError("Key index is out of range")
        return (index, index)

    def is_time_input(self):
        """bool: 横軸が時間ならTrue、単位なしならFalse。"""
        return self.type()[9] == "T"

    def key_count(self):
        """int: キー数。"""
        return cmds.keyframe(self.full_name(), query=True, keyframeCount=True) or 0

    def key_inputs(self):
        """list[float]: キー順の入力。時間型は現在の時間単位、それ以外は単位なし。"""
        flag = "timeChange" if self.is_time_input() else "floatChange"
        return cmds.keyframe(self.full_name(), query=True, **{flag: True}) or []

    def values(self):
        """list[float]: キー順の出力値。角度・距離・時間は現在のUI単位。"""
        return cmds.keyframe(self.full_name(), query=True, valueChange=True) or []

    def evaluate(self, input):
        """指定入力でカーブ単体を評価する。シーン時刻は変更しない。

        Args:
            input (float): 時間または単位なしの入力。
        Returns:
            float: 評価値。空カーブはRuntimeError。
        """
        value = self._finite(input)
        flag = "time" if self.is_time_input() else "float"
        result = cmds.keyframe(self.full_name(), query=True, eval=True, **{flag: (value, value)})
        if not result:
            raise RuntimeError("Cannot evaluate an empty curve")
        return result[0]

    @undo_chunk("hlibAnimCurveSetKey")
    def set_key(self, input, value, in_tangent="linear", out_tangent="linear"):
        """キーを追加、同じ入力位置なら更新する。

        Args:
            input (float): 時間または単位なしの入力。
            value (float): 現在のUI単位の出力。
            in_tangent (str): Mayaの入力接線型。
            out_tangent (str): Mayaの出力接線型。
        Returns:
            AnimCurve: 自身。fixed接線の詳細設定にはset_tangentを使う。
        """
        position, value = self._finite(input), self._finite(value)
        flag = "time" if self.is_time_input() else "float"
        cmds.setKeyframe(self.full_name(), value=value, inTangentType=in_tangent,
                        outTangentType=out_tangent, **{flag: position})
        return self

    @undo_chunk("hlibAnimCurveRemoveKey")
    def remove_key(self, index):
        """指定番号のキーを削除する。キークリップボードは変更しない。

        Args:
            index (int): 0始まりのキー番号。
        Returns:
            AnimCurve: 自身。
        """
        cmds.cutKey(self.full_name(), index=self._index(index), clear=True, animation="objects")
        return self

    def tangent(self, index):
        """指定キーの接線情報を取得する。

        Args:
            index (int): 0始まりのキー番号。
        Returns:
            dict: Mayaの接線フラグ名をキーとした型・角度・ウェイト・ロック情報。
        """
        span = self._index(index)
        return {flag: cmds.keyTangent(self.full_name(), query=True, index=span, **{flag: True})[0]
                for flag in ("inTangentType", "outTangentType", "inAngle", "outAngle",
                             "inWeight", "outWeight", "lock", "weightLock", "weightedTangents")}

    @undo_chunk("hlibAnimCurveSetTangent")
    def set_tangent(self, index, **kwargs):
        """キーの接線を変更する。Mayaの接線ロック規則に従う。

        Args:
            index (int): 0始まりのキー番号。
            **kwargs: tangent()で返すキーと同名のMayaフラグ。
                weightedTangentsはカーブ全体に適用される。
        Returns:
            AnimCurve: 自身。未知のフラグはValueError。
        """
        allowed = {"inTangentType", "outTangentType", "inAngle", "outAngle", "inWeight",
                   "outWeight", "lock", "weightLock", "weightedTangents"}
        if not kwargs or set(kwargs) - allowed:
            raise ValueError("Specify supported tangent flags")
        cmds.keyTangent(self.full_name(), edit=True, index=self._index(index), animation="objects", **kwargs)
        return self

    def infinity(self):
        """dict: pre/postをキーとした外挿方法名。"""
        names = {0: "constant", 1: "linear", 3: "cycle", 4: "cycleRelative", 5: "oscillate"}
        return {key: names[cmds.getAttr(self.full_name() + "." + key + "Infinity")]
                for key in ("pre", "post")}

    @undo_chunk("hlibAnimCurveInfinity")
    def set_infinity(self, pre="constant", post="constant"):
        """前後の外挿方法を設定する。

        Args:
            pre (str): constant/linear/cycle/cycleRelative/oscillate。
            post (str): preと同じ選択肢。
        Returns:
            AnimCurve: 自身。
        """
        allowed = {"constant": 0, "linear": 1, "cycle": 3, "cycleRelative": 4, "oscillate": 5}
        if pre not in allowed or post not in allowed:
            raise ValueError("Unsupported infinity type")
        cmds.setAttr(self.full_name() + ".preInfinity", allowed[pre])
        cmds.setAttr(self.full_name() + ".postInfinity", allowed[post])
        return self

    @undo_chunk("hlibAnimCurveShift")
    def shift_keys(self, input_offset=0, value_offset=0):
        """全キーを移動する。

        Args:
            input_offset (float): 横軸の移動量。時間型は現在の時間単位。
            value_offset (float): 縦軸の移動量。現在のUI単位。
        Returns:
            AnimCurve: 自身。空カーブは変更しない。
        """
        x, y = self._finite(input_offset), self._finite(value_offset)
        if self.key_count():
            flag = "timeChange" if self.is_time_input() else "floatChange"
            cmds.keyframe(self.full_name(), edit=True, relative=True, animation="objects",
                          valueChange=y, **{flag: x})
        return self

    @undo_chunk("hlibAnimCurveScale")
    def scale_keys(self, input_scale=1, value_scale=1, input_pivot=0, value_pivot=0):
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
        if not x:
            raise ValueError("Input scale cannot be zero")
        if self.key_count():
            prefix = "time" if self.is_time_input() else "float"
            cmds.scaleKey(self.full_name(), animation="objects", valueScale=y, valuePivot=py,
                          **{prefix + "Scale": x, prefix + "Pivot": px})
        return self

    def mirror(self, input=False, value=True, input_pivot=0, value_pivot=0):
        """入力軸・出力軸を反転する。内部のscale_keysでUndoをまとめる。

        Args:
            input (bool): 横軸を反転するか。
            value (bool): 縦軸を反転するか。
            input_pivot (float): 横軸の反転中心。
            value_pivot (float): 縦軸の反転中心。
        Returns:
            AnimCurve: 自身。
        """
        return self.scale_keys(-1 if input else 1, -1 if value else 1, input_pivot, value_pivot)

    def driver(self):
        """Plug | None: inputの直接接続元。時間型では通常timeノード。"""
        return self.plug("input").source()

    def output(self):
        """Plug: 出力プラグ。"""
        return self.plug("output")

    def driven_plugs(self):
        """list[Plug]: 直接の出力接続先。変換・合成ノード越しの探索はしない。"""
        return self.output().destinations()
