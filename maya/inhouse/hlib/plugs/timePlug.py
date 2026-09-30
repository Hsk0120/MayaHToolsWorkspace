"""時間。get/setはMayaの現在の時間単位を使用する。"""

from .._core.registry import plug_wrapper
from .plug import Plug


@plug_wrapper("time")
class TimePlug(Plug):
    """時間。get/setはMayaの現在の時間単位を使用する。"""
