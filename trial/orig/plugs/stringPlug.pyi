# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""文字列。get/setで読み書きする。数値のresetは対象外。"""

from .plug import Plug



class StringPlug(Plug):
    """文字列。get/setで読み書きする。数値のresetは対象外。"""
