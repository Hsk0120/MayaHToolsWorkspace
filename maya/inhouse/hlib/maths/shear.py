"""XY・XZ・YZ のシアーを表す3成分のベクトル値。"""

from .vector import Vector


class Shear(Vector):
    """XY・XZ・YZ のシアーを表す3成分の Vector 派生型(om2.MVector の派生)。

    型によって用途を識別するが、演算を禁止する検査は行わない。値・演算・比較は
    すべて :class:`~hlib.maths.vector.Vector` と同じ。
    """

    __slots__ = ()
