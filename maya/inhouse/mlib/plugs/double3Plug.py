"""double3アトリビュートを意味付きの3成分値として読み書きする。"""

import math

import maya.api.OpenMaya as om2

from ..core.attributeType import _convert_angles, _convert_units, _plain_angle_unit, _plain_time_unit
from ..core.fastWrite import set_plug
from ..decorator import _require_bool
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

    def get(self, *, unit=None, timeUnit=None, uiUnits=False):
        """3成分のチャンネル値を取得する。jointOrientなどは合成しない。

        Args:
            unit (str | None): 角度の子の数値の単位。None(既定)は度(rotateはEulerRotate)。
                rotateにunitを明示すると、EulerRotateではなく指定単位の数値tupleを返す。
                ``"deg"`` / ``"rad"`` と ``"degree"`` 等の別名を受け付け、uiUnits=Trueとは同時に指定できない。
            timeUnit (str | None): Plug共通の時間の単位指定。3成分の子は時間を持たないため検証だけ行う。
            uiUnits (bool): Trueは現在のUI単位の数値tuple。既定Falseは数学値。

        Returns:
            Vector | Translate | EulerRotate | Scale | Shear | tuple[float, float, float]:
                translateはTranslate、rotateはノードのrotateOrderを持つEulerRotate(内部はrad)、
                scaleはScale、shearはShear、その他はVector。距離はcm、jointOrient・rotateAxis等の
                角度の子は度(unit="rad"ならrad)の独立した値。
                uiUnits=Trueと、rotateへのunit指定では数値のtupleを返す。

        Raises:
            TypeError: uiUnitsがbool以外、またはunit・timeUnitが文字列・None以外の場合。
            ValueError: unit・timeUnitが未対応の単位名、またはuiUnits=Trueと同時に指定した場合。
            RuntimeError: 所有ノードまたはアトリビュートが無効な場合。
        """
        _require_bool(uiUnits, "uiUnits")
        angle_unit = _plain_angle_unit(unit, uiUnits)
        _plain_time_unit(timeUnit, uiUnits)
        self._require_valid()
        if uiUnits:
            return tuple(self._child_at(i).get(uiUnits=True) for i in range(3))
        value_type = self._value_types.get(self.getLongName(), Vector)
        if value_type is EulerRotate:
            # UIの角度単位に依存せず、値型はラジアンで構築する。
            values = [self._mplug.child(index).asMAngle().asRadians() for index in range(3)]
            if unit is not None:
                return tuple(math.degrees(v) if angle_unit == "deg" else v for v in values)
            order = int(self.getNode().getPlug("ro").get())
            return EulerRotate(*values, order=order)
        # 子Plugラッパーを作らず、子のget()と同じ読取関数で3成分を読む。
        values = tuple(self._child_values()[:3])
        return value_type(*_convert_angles(self._mplug, values, angle_unit, to_internal=False))

    def set(self, value, safe=False, *, unit=None, timeUnit=None, uiUnits=False, fast=False):
        """このアトリビュートの3成分だけを書き込む。マトリクス経由の姿勢変更は行わない。

        3成分の入力と書込み可否を確認してCompoundPlug.setへ渡す。
        safeの再試行では成功した子の更新を残す。通常処理はUndo有効時に記録し、fastは記録しない。

        Args:
            value (Iterable[float] | EulerRotate | Quaternion): 3成分の値。
                rotateではOpenMaya基底型の回転も受理し、ノードのrotateOrderへ揃える。
                数値列はノードのrotateOrderで解釈する。角度の子の数値は既定で度。
                EulerRotate・Quaternionは自身の単位(rad)を持つため、unitに関係なく換算しない。
            safe (bool): Trueは対応する書込み失敗を数える。
            unit (str | None): 角度の子(rotate・jointOrient・rotateAxis等)の数値の単位。
                None(既定)は度、``"rad"`` はラジアン(``"degree"`` 等の別名も可)。角度以外の子では使わない。
            timeUnit (str | None): Plug共通の時間の単位指定。3成分の子は時間を持たないため検証だけ行う。
            uiUnits (bool): TrueはUI単位の数値列を指定する。数学型とunitの同時指定は受理しない。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            Double3Plug | int: safe=Falseは自身。safe=Trueは成功0、子の失敗数、または入力変換失敗の1。
                CompoundPlug.setの再試行規則に従い、更新済みの値は自動では戻さない。

        Raises:
            TypeError: fastがbool以外、またはマルチアトリビュート全体への設定。safe=Trueでも抑制しない。
                safe=Falseでは入力型が不正な場合も送出する。
            ValueError: unit・timeUnitが未対応、またはuiUnits=Trueとの同時指定(safe=Trueでは1を返す)。
                safe=Falseで成分数・有限値が不正な場合。
            RuntimeError: safe=Falseで無効参照、ロック・入力接続、またはMayaの編集失敗。
            NotImplementedError: fastで未対応の型の場合。safe=Trueでも抑制しない。
        """
        return self._set_template(value, safe, unit=unit, timeUnit=timeUnit, uiUnits=uiUnits, fast=fast)

    def _set_value(self, value, *, uiUnits=False, fast=False):
        """3成分の入力と書込み可否を確認して書き込む。骨格は :meth:`Plug.set`。

        Args:
            value (Iterable[float] | EulerRotate | Quaternion): 3成分の値。角度の数値は
                :meth:`Plug._set_template` でradへ換算済み。
            uiUnits (bool): TrueはUI単位の数値列。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            None: 値を返さない。

        Raises:
            TypeError: 入力型が不正な場合。
            ValueError: 成分数・有限値が不正な場合。
            RuntimeError: 無効参照、ロック・入力接続、またはMayaの編集失敗。
        """
        self._require_valid()
        _require_bool(uiUnits, "uiUnits")
        if uiUnits:
            value = self._ui_components(value)
        values = self._set_components(value)
        self._require_writable()
        if fast and super()._set_value.__func__ is CompoundPlug._set_value:
            # CompoundPlug._set_value(fast)と同じ子数の検査と直接更新。参照の検証と全子の
            # 書込み可否は上で済んでいるため、set_plugでは型・範囲だけを検査する。
            if len(values) != self._mplug.numChildren():
                raise ValueError("Compound attribute value length does not match its child count")
            set_plug(self._mplug, values, _writable_checked=True)
        elif fast:
            super()._set_value(values, fast=fast)
        else:
            # 書込み可否は確認済みのため、親への1回のsetAttrを試す。
            self._set_child_values(values, writable_checked=True)

    def _set_children_safely(self, value, *, uiUnits=False, fast=False):
        """回転順序と入力単位を揃えてから、子のsafe設定を順に試す。

        UI数値への数学型指定など、成分変換そのものの失敗では子を更新しない。

        Args:
            value (object): 最初の設定へ渡した値(角度の数値はrad換算済み)。
            uiUnits (bool): TrueならUI数値を内部単位へ一度変換する。
            fast (bool): 子のsetへ渡す更新経路。

        Returns:
            int: 子の失敗数、または入力変換の失敗を表す1。
        """
        if not self.isValid() or not self.mplug().isCompound:
            return 1
        try:
            _require_bool(uiUnits, "uiUnits")
            if uiUnits:
                value = self._ui_components(value)
            values = self._set_components(value)
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

    def _set_components(self, value):
        """3成分の入力を検証し、rotateでは回転順序をノードへ揃える。

        シーンへの書込みは行わない。角度の数値は呼出元でradへ換算済みのものを受け取る。

        Args:
            value (Iterable[float] | om2.MEulerRotation | om2.MQuaternion): 入力値。

        Returns:
            tuple[float, float, float]: rotateはノードのrotateOrderに従うラジアンの成分。
                それ以外は入力の3成分。

        Raises:
            TypeError: 値を数値列へ変換できない場合。
            ValueError: 成分数・有限値が不正の場合。
        """
        if self._value_types.get(self.getLongName()) is EulerRotate:
            order = int(self.getNode().getPlug("ro").get())
            if isinstance(value, (om2.MEulerRotation, om2.MQuaternion)):
                rotation = value.asEulerRotation() if isinstance(value, om2.MQuaternion) else om2.MEulerRotation(value)
                values = tuple(rotation.reorder(order))
            else:
                values = tuple(value)
            if len(values) != 3 or not all(math.isfinite(v) for v in values):
                raise ValueError("Expected three finite rotation components")
        else:
            values = tuple(value)
            if len(values) != 3 or not all(math.isfinite(v) for v in values):
                raise ValueError("Expected three finite components")
        return values
