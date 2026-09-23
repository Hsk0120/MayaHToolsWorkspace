"""Maya の aimConstraint を扱う。"""

from .._core.registry import node_wrapper
from .constraint import Constraint


@node_wrapper("aimConstraint")
class AimConstraint(Constraint):
    """指定ターゲットへ向ける aimConstraint ラッパー。"""
