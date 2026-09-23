"""Maya の tangentConstraint を扱う。"""

from .._core.registry import node_wrapper
from .constraint import Constraint


@node_wrapper("tangentConstraint")
class TangentConstraint(Constraint):
    """NURBS カーブの接線方向へ向けるラッパー。"""
