"""double3アトリビュートを意味付きの3成分値として読み書きする。"""

import math
from contextlib import nullcontext

import maya.api.OpenMaya as om2

from ..core.attributeType import _convert_units
from ..core.fastWrite import _require_supported_type, set_plug
from ..decorator import undoChunk
from ..maths import EulerRotate, Scale, Shear, Translate, Vector
from .compoundPlug import CompoundPlug


class Double3Plug(CompoundPlug):
    """3成分アトリビュートを参照し、チャンネル値を読み書きする。マトリクス変換は行わない。"""

    _value_types = {
        "translate": Translate, "t": Translate,
        "rotate": EulerRotate, "r": EulerRotate,
        "scale": Scale, "s": Scale,
        "shear": Shear, "sh": Shear,
    }

    def get(self, *, uiUnits=False):
        """3成分のチャンネル値を取得する。jointOrientなどは合成しない。

        Args:
            uiUnits (bool): Trueは現在のUI単位の数値tuple。既定Falseは内部単位の数学値。

        Returns:
            Vector | Translate | EulerRotate | Scale | Shear | tuple[float, float, float]:
                translateはTranslate、rotateはノードのrotateOrderを持つEulerRotate、
                scaleはScale、shearはShear、その他はVector。距離cm・角度radの独立した値。
                uiUnits=Trueでは子の単位定義に従うtupleを返し、数学型は返さない。

        Raises:
            TypeError: uiUnitsがbool以外の場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効な場合。
        """
        self._validate_ui_units(uiUnits)
        self._require_valid()
        if uiUnits:
            return tuple(self._child_at(i).get(uiUnits=True) for i in range(3))
        value_type = self._value_types.get(self.getLongName(), Vector)
        if value_type is EulerRotate:
            order = int(self.getNode().getPlug("ro").get())
            # UIの角度単位に依存せず、値型はラジアンで構築する。
            values = [self._mplug.child(index).asMAngle().asRadians() for index in range(3)]
            return EulerRotate(*values, order=order)
        # 子Plugラッパーを作らず、子のget()と同じ読取関数で3成分を読む。
        return value_type(*self._child_values()[:3])

    def set(self, value, safe=False, *, unit="rad", uiUnits=False, fast=False):
        """このアトリビュートの3成分だけを書き込む。マトリクス経由の姿勢変更は行わない。

        3成分の入力と書込み可否を確認してCompoundPlug.setへ渡す。
        safeの再試行では成功した子の更新を残す。通常処理はUndo有効時に記録し、fastは記録しない。

        Args:
            value (Iterable[float] | EulerRotate | Quaternion): 3成分の値。
                rotateではOpenMaya基底型の回転も受理し、ノードのrotateOrderへ揃える。
                数値列はノードのrotateOrderで解釈する。
            safe (bool): Trueは対応する書込み失敗を数える。
            unit (str): uiUnits=Falseではrotateの数値列にrad/degを使い、他のアトリビュートでは未使用。
                型付き回転はradのみ。
            uiUnits (bool): TrueはUI単位の数値列を指定する。数学型と既定rad以外のunitは受理しない。
            fast (bool): TrueはUndoなしのOpenMaya直接更新。Undo設定は変更しない。

        Returns:
            Double3Plug | int: safe=Falseは自身。safe=Trueは成功0、子の失敗数、または入力変換失敗の1。
                CompoundPlug.setの再試行規則に従い、更新済みの値は自動では戻さない。

        Raises:
            TypeError: fastがbool以外、または配列全体への設定。safe=Trueでも抑制しない。
                safe=Falseでは入力型が不正な場合も送出する。
            NotImplementedError: fastで未対応の型の場合。safe=Trueでも抑制しない。
            ValueError: safe=Falseで成分数・有限値・角度単位が不正な場合。
            RuntimeError: safe=Falseで無効参照、ロック・入力接続、またはMayaの編集失敗。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibDouble3PlugSet"):
            if self.isArray():
                raise TypeError("Set an array element instead of the array plug")
            if safe and fast and self.isValid() and self.mplug().isCompound:
                _require_supported_type(self.mplug())
            original_value = value
            try:
                self._require_valid()
                self._validate_ui_units(uiUnits)
                if uiUnits:
                    if unit != "rad":
                        raise ValueError("uiUnits=True cannot be combined with a non-default unit")
                    value = self._ui_components(value)
                values = self._set_components(value, unit)
                self._require_writable()
                if fast and super().set.__func__ is CompoundPlug.set:
                    # CompoundPlug.set(fast)と同じ子数の検査と直接更新。参照の検証と全子の
                    # 書込み可否は上で済んでいるため、set_plugでは型・範囲だけを検査する。
                    if len(values) != self._mplug.numChildren():
                        raise ValueError("Compound plug value length does not match its child count")
                    set_plug(self._mplug, values, _writable_checked=True)
                elif fast:
                    super().set(values, safe=False, fast=fast)
                else:
                    # 書込み可否は確認済みのため、親への1回のsetAttrを試す。
                    self._set_child_values(values, writable_checked=True)
            except NotImplementedError:
                raise
            except (RuntimeError, TypeError, ValueError):
                if not safe:
                    raise
                return self._set_children_safely(original_value, unit=unit, uiUnits=uiUnits, fast=fast)
            return 0 if safe else self

    def _set_children_safely(self, value, *, unit="rad", uiUnits=False, fast=False):
        """回転順序と入力単位を揃えてから、子のsafe設定を順に試す。

        UI数値への数学型指定など、成分変換そのものの失敗では子を更新しない。

        Args:
            value (object): 最初の設定へ渡した値。
            unit (str): rotateの数値列の角度単位。
            uiUnits (bool): TrueならUI数値を内部単位へ一度変換する。
            fast (bool): 子のsetへ渡す更新経路。

        Returns:
            int: 子の失敗数、または入力変換の失敗を表す1。
        """
        if not self.isValid() or not self.mplug().isCompound:
            return 1
        try:
            self._validate_ui_units(uiUnits)
            if uiUnits:
                if unit != "rad":
                    raise ValueError("uiUnits=True cannot be combined with a non-default unit")
                value = self._ui_components(value)
            values = self._set_components(value, unit)
        except NotImplementedError:
            raise
        except (RuntimeError, TypeError, ValueError):
            return 1
        return super()._set_children_safely(values, uiUnits=False, fast=fast)

    def _ui_components(self, value):
        """UI入力を数値列として変換し、内部単位を持つ数学値を拒否する。

        Args:
            value (Iterable[float]): UI単位の数値3成分。

        Returns:
            tuple: 内部単位の数値3成分。

        Raises:
            TypeError: OpenMayaの数学値をUI数値として指定した場合。
        """
        if isinstance(value, (om2.MEulerRotation, om2.MQuaternion, om2.MVector)):
            raise TypeError("uiUnits=True requires plain numeric components, not a math value")
        return _convert_units(self._mplug, value, to_ui=False)

    def _set_components(self, value, unit="rad"):
        """3成分の入力を検証し、rotateでは角度単位と回転順序をノードへ揃える。

        シーンへの書込みは行わない。rotate以外ではunitを解釈せず、有限な3成分を返す。

        Args:
            value (Iterable[float] | om2.MEulerRotation | om2.MQuaternion): 入力値。
            unit (str): rotateの数値列はrad/deg。型付き回転ではradのみ。

        Returns:
            tuple[float, float, float]: rotateはノードのrotateOrderに従うラジアンの成分。
                それ以外は入力の3成分。回転以外の単位換算は呼出元が担当する。

        Raises:
            TypeError: 値を数値列へ変換できない場合。
            ValueError: 成分数・有限値・角度単位が不正の場合。
        """
        if self._value_types.get(self.getLongName()) is EulerRotate:
            if unit not in ("rad", "deg"):
                raise ValueError("unit must be 'rad' or 'deg'")
            order = int(self.getNode().getPlug("ro").get())
            if isinstance(value, (om2.MEulerRotation, om2.MQuaternion)):
                if unit != "rad":
                    raise ValueError("unit='deg' requires three plain components")
                rotation = value.asEulerRotation() if isinstance(value, om2.MQuaternion) else om2.MEulerRotation(value)
                values = tuple(rotation.reorder(order))
            else:
                values = tuple(value)
                if unit == "deg":
                    values = tuple(math.radians(v) for v in values)
            if len(values) != 3 or not all(math.isfinite(v) for v in values):
                raise ValueError("Expected three finite rotation components")
        else:
            values = tuple(value)
            if len(values) != 3 or not all(math.isfinite(v) for v in values):
                raise ValueError("Expected three finite components")
        return values
