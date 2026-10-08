"""Maya の normalConstraint を扱う。"""

from .constraint import Constraint


class NormalConstraint(Constraint):
    """ターゲット表面の法線方向へ向けるラッパー。"""
