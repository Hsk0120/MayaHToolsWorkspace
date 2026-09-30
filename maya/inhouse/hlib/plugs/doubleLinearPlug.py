"""距離アトリビュートを汎用 Plug の読み書き機能で扱う。"""

from .._core.registry import plug_wrapper
from .plug import Plug


@plug_wrapper("doubleLinear")
class DoubleLinearPlug(Plug):
    """doubleLinear（距離）アトリビュート用の Plug。"""
