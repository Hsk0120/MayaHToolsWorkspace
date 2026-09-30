"""短整数。範囲の制約はMayaの定義に従う。"""

from .._core.registry import plug_wrapper
from .plug import Plug


@plug_wrapper("short")
class ShortPlug(Plug):
    """短整数。範囲の制約はMayaの定義に従う。"""
