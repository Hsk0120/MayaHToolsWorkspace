"""Maya の parentConstraint を扱う。"""

from .._core.registry import node_wrapper
from .constraint import Constraint


@node_wrapper("parentConstraint")
class ParentConstraint(Constraint):
    """位置と回転を拘束する parentConstraint ラッパー。"""
