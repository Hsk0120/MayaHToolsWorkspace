"""列挙値。get/setは整数値、enumName/enumValueは名前と値を扱う。"""

from .._core.registry import plug_wrapper
from .plug import Plug


@plug_wrapper("enum")
class EnumPlug(Plug):
    """列挙値。get/setは整数値、enumName/enumValueは名前と値を扱う。"""
