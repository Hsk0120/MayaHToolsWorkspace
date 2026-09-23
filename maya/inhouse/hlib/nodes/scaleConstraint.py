"""Maya の scaleConstraint を扱う。"""

from .._core.registry import node_wrapper
from .constraint import Constraint


@node_wrapper("scaleConstraint")
class ScaleConstraint(Constraint):
    """スケールを拘束する scaleConstraint ラッパー。"""
