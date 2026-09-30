"""値を保持しない接続用。connect/source/destinationsで関係を扱う。"""

from .._core.registry import plug_wrapper
from .plug import Plug


@plug_wrapper("message")
class MessagePlug(Plug):
    """値を保持しない接続用。connect/source/destinationsで関係を扱う。"""
