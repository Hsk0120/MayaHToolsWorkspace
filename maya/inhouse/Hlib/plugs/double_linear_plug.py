"""doubleLinear (linear distance) attribute plug wrapper."""

from ..core.registry import plug_wrapper
from .plug import Plug


@plug_wrapper("doubleLinear")
class DoubleLinearPlug(Plug):
    """doubleLinear（距離）属性用の Plug。"""
