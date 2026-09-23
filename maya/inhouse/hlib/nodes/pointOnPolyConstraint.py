"""Maya の pointOnPolyConstraint を扱う。"""

from .._core.registry import node_wrapper
from .constraint import Constraint


@node_wrapper("pointOnPolyConstraint")
class PointOnPolyConstraint(Constraint):
    """ポリゴン表面上の点へ拘束するラッパー。"""
