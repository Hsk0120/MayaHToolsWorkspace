"""XY・XZ・YZ のシアーを表す3成分のベクトル値。"""

from dataclasses import dataclass

from .vector import Vector


@dataclass(frozen=True, repr=False)
class Shear(Vector):
    """XY・XZ・YZ のシアーを表す3成分の Vector 派生型。

    型によって用途を識別するが、演算を禁止する検査は行わない。"""
