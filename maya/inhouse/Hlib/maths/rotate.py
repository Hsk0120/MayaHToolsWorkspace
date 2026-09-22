"""Vector と同じ演算を持つ互換用の回転3成分値。"""

from .vector import Vector


class Rotate(Vector):
    """行列互換のために保持する 3 成分回転値。"""