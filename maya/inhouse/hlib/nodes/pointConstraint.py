"""Maya の pointConstraint を扱う。"""

from .._core.registry import node_wrapper
from .constraint import Constraint


@node_wrapper("pointConstraint")
class PointConstraint(Constraint):
    """位置を拘束する pointConstraint ラッパー。"""
