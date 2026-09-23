"""Maya の normalConstraint を扱う。"""

from .._core.registry import node_wrapper
from .constraint import Constraint


@node_wrapper("normalConstraint")
class NormalConstraint(Constraint):
    """ターゲット表面の法線方向へ向けるラッパー。"""
