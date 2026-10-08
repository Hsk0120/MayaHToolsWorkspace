"""Maya の pointConstraint を扱う。"""

from .constraint import Constraint


class PointConstraint(Constraint):
    """位置を拘束する pointConstraint ラッパー。"""
