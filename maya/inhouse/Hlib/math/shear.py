"""Semantic shear vector value."""

from .vector import Vector


class Shear(Vector):
    """Shear を表す意味付き 3 次元ベクトル。

    Scale と別型にすることで、意味のない演算を区別しやすくする。
    """