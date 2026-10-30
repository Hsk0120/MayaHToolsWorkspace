# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""二つのRGB入力をblenderで補間する。"""

from .node import Node



class BlendColors(Node):
    """color1 * blender + color2 * (1 - blender)を評価するノード。"""
