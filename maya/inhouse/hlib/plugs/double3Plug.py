"""double3属性を意味付きの3成分値として読み書きする。"""

import math
import maya.api.OpenMaya as om2

from ..decorators._fast import fast_edit
from .._core.fastWrite import writable
from .._core.registry import plug_wrapper
from ..maths import EulerRotation, Scale, Shear, Translation, Vector
from .compoundPlug import CompoundPlug


@plug_wrapper("double3")
class Double3Plug(CompoundPlug):
    """属性の子成分だけを扱う。ノードの行列変換には委譲しない。"""

    _value_types = {
        "translate": Translation, "t": Translation,
        "rotate": EulerRotation, "r": EulerRotation,
        "scale": Scale, "s": Scale,
        "shear": Shear, "sh": Shear,
    }

    def get(self):
        """属性の3成分を取得する。jointOrientなどを合成しない。

        Returns:
            Vector | Translation | EulerRotation | Scale | Shear: 属性の値。
                rotateはラジアン・ノードのrotateOrder、距離は現在のUI単位。

        Raises:
            RuntimeError: 所有ノードまたは属性が無効の場合。
        """
        self._require_valid()
        value_type = self._value_types.get(self.attribute(), Vector)
        if value_type is EulerRotation:
            order = int(self.node.plug("ro").get())
            # UIの角度単位に依存せず、値型はラジアンで構築する。
            values = [self.child(index).mplug().asMAngle().asRadians() for index in range(3)]
            return EulerRotation(*values, order=order)
        return value_type(*(self.child(index).get() for index in range(3)))

    @fast_edit
    def set(self, value, unit="rad", *, fast=False):
        """対象属性の3成分を書き込む。ほかの変換チャンネルは変更しない。

        Args:
            value (Iterable[float] | EulerRotation | Quaternion): 3成分の値。
                rotateではEuler/Quaternionも受け入れ、ノードのrotateOrderへ変換する。
                数値3成分は現在のrotateOrderのチャンネル値として解釈する。
            unit (str): rotateの数値3成分の角度単位rad/deg。それ以外の属性では未使用。
            fast (bool): TrueはOpenMaya直接更新でUndoなし。

        Returns:
            Double3Plug: 自身。

        Raises:
            ValueError: 要素数・有限値・角度単位が不正、または型付き回転にdegを指定した場合。
            RuntimeError: 属性が無効、ロック・接続済み、またはMayaが更新を拒否した場合。

        ワールド空間やjointOrientを含む姿勢の変更はTransform.set_rotate等を使う。
        通常モードは1回のUndoで戻せる。Mayaの実行時エラーを自動ロールバックはしない。
        """
        self._require_valid()
        if self._value_types.get(self.attribute()) is EulerRotation:
            if unit not in ("rad", "deg"):
                raise ValueError("unit must be 'rad' or 'deg'")
            order = int(self.node.plug("ro").get())
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
            # 子Plug.setとcmds.setAttrはUI単位で書く。fastでも同じ数値を渡す。
            values = tuple(om2.MAngle(v).asUnits(om2.MAngle.uiUnit()) for v in values)
        else:
            values = tuple(value)
            if len(values) != 3 or not all(math.isfinite(v) for v in values):
                raise ValueError("Expected three finite components")
        for index in range(3):
            writable(self.child(index).mplug())
        return super().set(values)
