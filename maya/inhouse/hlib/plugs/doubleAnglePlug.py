"""角度。get/setはMayaの現在の角度単位を使用する。"""

from .._core.registry import plug_wrapper
from .plug import Plug


@plug_wrapper("doubleAngle")
class DoubleAnglePlug(Plug):
    """角度。get/setはMayaの現在の角度単位を使用する。"""
