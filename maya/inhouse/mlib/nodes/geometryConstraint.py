"""Maya の geometryConstraint を扱う。"""

from .constraint import Constraint


class GeometryConstraint(Constraint):
    """ターゲット表面上の位置へ拘束するラッパー。"""
