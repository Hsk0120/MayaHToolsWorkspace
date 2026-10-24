"""double3アトリビュートを意味付きの3成分値として読み書きする。"""

import math
from contextlib import nullcontext

import maya.api.OpenMaya as om2

from ..core.attributeType import _convert_units
from ..core.fastWrite import _require_supported_type
from ..decorator import undoChunk
from ..maths import EulerRotate, Scale, Shear, Translate, Vector
from .compoundPlug import CompoundPlug


class Double3Plug(CompoundPlug):
    """アトリビュートの子成分だけを扱う。ノードの行列変換には委譲しない。"""

    _value_types = {
        "translate": Translate, "t": Translate,
        "rotate": EulerRotate, "r": EulerRotate,
        "scale": Scale, "s": Scale,
        "shear": Shear, "sh": Shear,
    }

    def get(self, *, uiUnits=False):
        """アトリビュートの3成分を取得する。jointOrientなどを合成しない。

        translateはTranslate、rotateはノードのrotateOrderを持つEulerRotate、
        scaleはScale、shearはShear、それ以外はVectorを返す。
        アトリビュートのチャンネル値を読み、Transform.getRotate等の行列分解とは区別する。

        Args:
            uiUnits (bool): TrueはUI単位の数値。既定Falseは内部単位。

        Returns:
            Vector | Translate | EulerRotate | Scale | Shear | tuple[float, float, float]: アトリビュートの値。
                既定ではrotateはラジアン・ノードのrotateOrder、距離はcm。
                数学値はノードと独立した新しい値。
                uiUnits=Trueは子の単位定義に従う数値tupleで、数学型は返さない。

        Raises:
            RuntimeError: 所有ノードまたはアトリビュートが無効の場合。
        """
        self._validate_ui_units(uiUnits)
        self._require_valid()
        if uiUnits:
            return tuple(self._child_at(i).get(uiUnits=True) for i in range(3))
        value_type = self._value_types.get(self.getLongName(), Vector)
        if value_type is EulerRotate:
            order = int(self.getNode().getPlug("ro").get())
            # UIの角度単位に依存せず、値型はラジアンで構築する。
            values = [self._child_at(index).mplug().asMAngle().asRadians() for index in range(3)]
            return EulerRotate(*values, order=order)
        return value_type(*(self._child_at(index).get() for index in range(3)))

    def set(self, value, safe=False, *, unit="rad", uiUnits=False, fast=False):
        """対象アトリビュートの3成分を書き込む。ほかの変換チャンネルは変更しない。

        入力を内部単位の3成分へ揃えて全子の書込み可否を確認し、CompoundPlug.setへ
        渡す。safe=Trueでは失敗した一括処理を子ごとに再試行し、書ける子だけを更新する。

        Args:
            value (Iterable[float] | EulerRotate | Quaternion): 3成分の値。
                uiUnits=Trueでは内部単位を持つ数学型を受け付けず、数値列を指定する。
                rotateではEuler/Quaternionも受け入れ、ノードのrotateOrderへ変換する。
                数値3成分は現在のrotateOrderのチャンネル値として解釈する。
            safe (bool): Trueは対応する失敗を数える。成功した子は自動では戻さない。
            unit (str): rotateの数値3成分の角度単位rad/deg。それ以外のアトリビュートでは未使用。
            uiUnits (bool): TrueはUI単位の数値。既定Falseは内部単位。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。内側の編集へもfastを明示して渡す。

        Returns:
            Double3Plug | int: safe=Falseでは自身。safe=Trueでは書けなかった成分数、全て成功なら0。
                値を有効な3成分へ変換できない場合は1を返す。
                fastがbool以外のTypeErrorは抑制しない。複合値の再試行規則はCompoundPlug.setに従う。

        Raises:
            ValueError: 要素数・有限値・角度単位が不正、または型付き回転にdegを指定した場合。
            RuntimeError: アトリビュートが無効、ロック・接続済み、またはMayaが更新を拒否した場合。

        ワールド空間やjointOrientを含む姿勢の変更はTransform.setRotate等を使う。
        通常はUndoが有効なら子の変更を同じチャンクへ記録する。
        fastはUndo設定を変更しない。Mayaの実行時エラーを自動ロールバックはしない。
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
                super().set(values, safe=False, fast=fast)
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
