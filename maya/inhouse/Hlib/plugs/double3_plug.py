"""double3 (compound numeric triple) attribute plug wrapper."""

import math

from ..core.registry import plug_wrapper
from ..maths import EulerRotation, Scale, Shear, Translate, Vector
from .compound_plug import CompoundPlug


@plug_wrapper("double3")
class Double3Plug(CompoundPlug):
    """double3（3つの double からなる compound）属性用の Plug。"""

    _value_types = {
        "translate": Translate,
        "t": Translate,
        "rotate": EulerRotation,
        "r": EulerRotation,
        "scale": Scale,
        "s": Scale,
        "shear": Shear,
        "sh": Shear,
    }
    _rotation_orders = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")

    def get(self, ws=False):
        """3つの子要素を属性の意味に対応するベクトルとして取得する。

        Args:
            ws (bool): ``True`` で変換属性をワールド空間で取得する。

        Returns:
            Vector: 3成分の値。既知の変換属性では意味付きサブクラス。
        """
        if ws and self.attribute in self._value_types:
            getters = {
                "translate": "get_translate",
                "t": "get_translate",
                "rotate": "get_rotate",
                "r": "get_rotate",
                "scale": "get_scale",
                "s": "get_scale",
                "shear": "get_shear",
                "sh": "get_shear",
            }
            getter = getattr(self.node, getters[self.attribute], None)
            if getter is not None:
                return getter(ws=True)
        values = tuple(self.child(index).get() for index in range(3))
        value_type = self._value_types.get(self.attribute, Vector)
        if value_type is EulerRotation:
            order_index = self.node.plug("ro").get()
            order = self._rotation_orders[int(order_index)]
            return EulerRotation(*(math.radians(value) for value in values), order=order)
        return value_type(*values)

    def set(self, value, ws=False, unit="rad"):
        """変換属性をローカルまたはワールド空間へ設定する。"""
        setters = {
            "translate": "set_translate",
            "t": "set_translate",
            "rotate": "set_rotate",
            "r": "set_rotate",
            "scale": "set_scale",
            "s": "set_scale",
            "shear": "set_shear",
            "sh": "set_shear",
        }
        setter_name = setters.get(self.attribute)
        setter = getattr(self.node, setter_name, None) if setter_name else None
        if setter is not None:
            kwargs = {"ws": ws}
            if self.attribute in ("rotate", "r"):
                kwargs["unit"] = unit
            setter(value, **kwargs)
            return self
        if ws:
            raise ValueError("World-space writes are only supported for Transform attributes")
        return super().set(value)
