"""Maya の poleVectorConstraint を扱う。"""

from .constraint import Constraint


class PoleVectorConstraint(Constraint):
    """RP IK ハンドルの極ベクトルを拘束するラッパー。"""
