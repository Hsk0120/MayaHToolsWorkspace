"""角度。get/setはradを使用する。"""

from .._core.registry import plug_wrapper
from .plug import Plug


@plug_wrapper("doubleAngle")
class DoubleAnglePlug(Plug):
    """角度。get/setはradを使用する。"""
