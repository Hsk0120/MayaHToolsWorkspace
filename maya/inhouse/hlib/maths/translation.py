"""平行移動を表す3成分のベクトル値。"""

from dataclasses import dataclass

from .vector import Vector


@dataclass(frozen=True, repr=False)
class Translation(Vector):
    """位置を表す意味付き 3 次元ベクトル。"""
