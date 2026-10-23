"""double3アトリビュートを意味付きの3成分値として読み書きする。"""

import math

import maya.api.OpenMaya as om2

from ..core.attributeType import _convert_units
from ..decorator import _fast_edit, _safe_edit, undoChunk
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

        Args:
            uiUnits (bool): TrueはUI単位の数値。既定Falseは内部単位。

        Returns:
            Vector | Translate | EulerRotate | Scale | Shear | tuple[float, float, float]: アトリビュートの値。
                既定ではrotateはラジアン・ノードのrotateOrder、距離はcm。
                uiUnits=Trueは現在のUI単位に変換した数値tuple。

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

    @_fast_edit
    @undoChunk("mlibDouble3PlugSet")
    @_safe_edit
    def set(self, value, safe=False, *, unit="rad", uiUnits=False, fast=False):
        """対象アトリビュートの3成分を書き込む。ほかの変換チャンネルは変更しない。

        Args:
            value (Iterable[float] | EulerRotate | Quaternion): 3成分の値。
                uiUnits=Trueでは内部単位を持つ数学型を受け付けず、数値列を指定する。
                rotateではEuler/Quaternionも受け入れ、ノードのrotateOrderへ変換する。
                数値3成分は現在のrotateOrderのチャンネル値として解釈する。
            safe (bool): Trueで書込み失敗を抑制し、失敗数を返す。
            unit (str): rotateの数値3成分の角度単位rad/deg。それ以外のアトリビュートでは未使用。
            uiUnits (bool): TrueはUI単位の数値。既定Falseは内部単位。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。

        Returns:
            Double3Plug | int: safe=Falseでは自身。safe=Trueでは書けなかった成分数、全て成功なら0。
                値を有効な3成分へ変換できない場合は1を返す。

        Raises:
            ValueError: 要素数・有限値・角度単位が不正、または型付き回転にdegを指定した場合。
            RuntimeError: アトリビュートが無効、ロック・接続済み、またはMayaが更新を拒否した場合。

        ワールド空間やjointOrientを含む姿勢の変更はTransform.setRotate等を使う。
        通常モードは1回のUndoで戻せる。Mayaの実行時エラーを自動ロールバックはしない。
        """
        self._require_valid()
        self._validate_ui_units(uiUnits)
        if uiUnits:
            if unit != "rad":
                raise ValueError("uiUnits=True cannot be combined with a non-default unit")
            value = self._ui_components(value)
        values = self._set_components(value, unit)
        self._require_writable()
        return super().set(values)

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
        """入力の角度単位と回転順序を子へ設定する内部単位へ揃える。

        Args:
            value: 変換・設定する入力値。
            unit: 値の単位を指定する識別子。
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
