"""単精度浮動小数。値の精度はMayaの定義に従う。"""

from .._core.registry import plug_wrapper
from .plug import Plug


@plug_wrapper("float")
class FloatPlug(Plug):
    """単精度浮動小数。値の精度はMayaの定義に従う。"""
