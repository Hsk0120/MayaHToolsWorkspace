"""浮動小数。get/set/resetはPlugの共通実装を使用する。"""

from .._core.registry import plug_wrapper
from .plug import Plug


@plug_wrapper("double")
class DoublePlug(Plug):
    """浮動小数。get/set/resetはPlugの共通実装を使用する。"""
