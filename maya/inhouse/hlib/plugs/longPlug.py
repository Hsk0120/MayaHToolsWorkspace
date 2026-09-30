"""整数。get/set/resetはPlugの共通実装を使用する。"""

from .._core.registry import plug_wrapper
from .plug import Plug


@plug_wrapper("long")
class LongPlug(Plug):
    """整数。get/set/resetはPlugの共通実装を使用する。"""
