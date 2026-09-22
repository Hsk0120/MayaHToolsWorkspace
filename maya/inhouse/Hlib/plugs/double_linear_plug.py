"""距離属性を汎用 Plug の読み書き機能で扱う。"""

from ..core.registry import plug_wrapper
from .plug import Plug


@plug_wrapper("doubleLinear")
class DoubleLinearPlug(Plug):
    """doubleLinear（距離）属性用の Plug。"""
