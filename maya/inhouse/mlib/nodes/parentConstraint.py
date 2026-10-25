"""Maya の parentConstraint を扱う。"""

from .constraint import Constraint


class ParentConstraint(Constraint):
    """位置と回転をコンストレイントする parentConstraint ラッパー。"""
