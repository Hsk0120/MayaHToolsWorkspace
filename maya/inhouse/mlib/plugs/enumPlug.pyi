# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""列挙値。get/setは整数値、getEnumName/getEnumValueは名前と値を扱う。"""

from .plug import Plug



class EnumPlug(Plug):
    """列挙値。get/setは整数値、getEnumName/getEnumValueは名前と値を扱う。"""
