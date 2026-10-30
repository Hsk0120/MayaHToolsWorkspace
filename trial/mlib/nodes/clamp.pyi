# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""RGB各成分を指定範囲に制限する。"""

from .node import Node



class Clamp(Node):
    """RGB各成分を指定範囲に制限する。"""
