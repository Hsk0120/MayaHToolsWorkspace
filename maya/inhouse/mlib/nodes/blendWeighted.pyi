# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""ウェイト付き加算ノード。ウェイトの正規化はしない。"""

from .node import Node



class BlendWeighted(Node):
    """input[i] * weight[i]を合計する。weightの既定値は1。"""
