"""二つのRGB入力をblenderで補間する。"""

from .node import Node


class BlendColors(Node):
    """color1 * blender + color2 * (1 - blender)を評価するノード。"""
