"""平行移動を表す3成分のベクトル値。"""

from .vector import Vector


class Translation(Vector):
    """位置・平行移動を表す意味付きの3成分ベクトル(om2.MVector の派生)。

    値・演算・比較はすべて :class:`~hlib.maths.vector.Vector` と同じ。
    om2 の MVector を継承するため、``MFnTransform.setTranslation`` などへ
    そのまま渡せる。位置を行列で変換するときは
    :meth:`hlib.maths.matrix.Matrix.transform_point` か ``om2.MPoint(t) * m`` を使う
    (``t * m`` は平行移動を含まない方向の変換になる)。
    """

    __slots__ = ()
