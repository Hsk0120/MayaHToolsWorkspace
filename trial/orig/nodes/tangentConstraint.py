"""Maya の tangentConstraint を扱う。"""

from .constraint import Constraint


class TangentConstraint(Constraint):
    """NURBS カーブの接線方向へ向けるラッパー。"""
