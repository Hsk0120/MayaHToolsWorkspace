"""文字列。get/setで読み書きする。数値のresetは対象外。"""

from .._core.registry import plug_wrapper
from .plug import Plug


@plug_wrapper("string")
class StringPlug(Plug):
    """文字列。get/setで読み書きする。数値のresetは対象外。"""
