"""重み付き加算ノード。ウェイトの正規化はしない。"""

from .node import Node


class BlendWeighted(Node):
    """input[i] * weight[i]を合計する。weightの既定値は1。"""
