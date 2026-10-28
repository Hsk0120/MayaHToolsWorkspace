"""Maya の poleVectorConstraint を扱う。"""

from .pointConstraint import PointConstraint


class PoleVectorConstraint(PointConstraint):
    """RP IKハンドルのポールベクトルをコンストレイントするラッパー。

    Maya の poleVectorConstraint は pointConstraint の派生型なので、基底も PointConstraint にする。
    """
