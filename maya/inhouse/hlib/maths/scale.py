"""スケールを表す3成分のベクトル値。"""

from dataclasses import dataclass

from .vector import Vector


@dataclass(frozen=True, repr=False)
class Scale(Vector):
    """スケールを表す意味付き 3 次元ベクトル。"""
