"""Maya の orientConstraint を扱う。"""

from .._core.registry import node_wrapper
from .constraint import Constraint


@node_wrapper("orientConstraint")
class OrientConstraint(Constraint):
    """回転を拘束する orientConstraint ラッパー。"""
