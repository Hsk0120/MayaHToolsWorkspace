"""Maya の parentConstraint を扱う。"""

from .constraint import Constraint


class ParentConstraint(Constraint):
    """位置と回転を拘束する parentConstraint ラッパー。"""
