# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""浮動小数。get/set/resetはPlugの共通実装を使用する。"""

from .plug import Plug



class DoublePlug(Plug):
    """浮動小数。get/set/resetはPlugの共通実装を使用する。"""
