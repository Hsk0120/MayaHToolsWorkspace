"""Maya の pointOnPolyConstraint を扱う。"""

from .constraint import Constraint


class PointOnPolyConstraint(Constraint):
    """ポリゴン表面上の点へ拘束するラッパー。"""
