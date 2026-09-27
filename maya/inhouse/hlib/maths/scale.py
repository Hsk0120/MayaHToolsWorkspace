"""スケールを表す3成分のベクトル値。"""

from .vector import Vector


class Scale(Vector):
    """スケールを表す意味付きの3成分ベクトル(om2.MVector の派生)。

    値・演算・比較はすべて :class:`~hlib.maths.vector.Vector` と同じ。
    """

    __slots__ = ()
