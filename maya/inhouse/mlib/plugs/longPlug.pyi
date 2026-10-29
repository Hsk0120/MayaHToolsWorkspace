# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""整数。get/set/resetはPlugの共通実装を使用する。"""

from .plug import Plug



class LongPlug(Plug):
    """整数。get/set/resetはPlugの共通実装を使用する。"""
