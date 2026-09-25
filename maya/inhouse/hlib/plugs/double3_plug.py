"""double3 属性を意味付きの3成分値として扱う。"""

from ..decorators._fast import fast_edit

import math

from .._core.registry import plug_wrapper
from ..maths import EulerRotation, Scale, Shear, Translation, Vector
from .compound_plug import CompoundPlug


@plug_wrapper("double3")
class Double3Plug(CompoundPlug):
    """double3（3つの double からなる compound）属性用の Plug。"""

    _value_types = {
        "translate": Translation,
        "t": Translation,
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

        ローカル回転は子Plug.get()が返す度をラジアンへ変換する。

        Args:
            ws (bool): True で既知の変換属性に対応するノードの取得メソッドを呼ぶ。それ以外は子属性の値を使う。

        Returns:
            Vector | Translation | EulerRotation | Scale | Shear: 属性名に応じた3成分値。ローカルの rotate は度からラジアンに変換し、rotateOrder を保持する。
        """
        if ws and self.attribute() in self._value_types:
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
            getter = getattr(self.node, getters[self.attribute()], None)
            if getter is not None:
                return getter(ws=True)
        values = tuple(self.child(index).get() for index in range(3))
        value_type = self._value_types.get(self.attribute(), Vector)
        if value_type is EulerRotation:
            order_index = self.node.plug("ro").get()
            order = self._rotation_orders[int(order_index)]
            return EulerRotation(*(math.radians(value) for value in values), order=order)
        return value_type(*values)

    @fast_edit
    def set(self, value, ws=False, unit="rad", *, fast=False):
        """変換属性をローカルまたはワールド空間へ設定する。

        対応するノードメソッドがあればローカル指定でも委譲する。なければ各子プラグへ順に設定する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Iterable[float] | Quaternion): 設定値。通常は3成分。回転メソッドへの委譲時はその受け入れ型に従う。
            ws (bool): True ならノードの変換設定メソッドへワールド指定で委譲する。
            unit (str): 回転の委譲時のみ使用する入力単位 rad または deg。その他の属性では無視する。

        Returns:
            Double3Plug: 自身。

        Raises:
            ValueError: 対応する設定メソッドがない属性で ws=True を指定、値の要素数が不正、または委譲先の変換条件が不正の場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
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
        setter_name = setters.get(self.attribute())
        setter = getattr(self.node, setter_name, None) if setter_name else None
        if setter is not None:
            kwargs = {"ws": ws}
            if self.attribute() in ("rotate", "r"):
                kwargs["unit"] = unit
            setter(value, **kwargs)
            return self
        if ws:
            raise ValueError("World-space writes are only supported for Transform attributes")
        return super().set(value)
