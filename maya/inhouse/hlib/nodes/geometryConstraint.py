"""Maya の geometryConstraint を扱う。"""

from .._core.registry import node_wrapper
from .constraint import Constraint


@node_wrapper("geometryConstraint")
class GeometryConstraint(Constraint):
    """ターゲット表面上の位置へ拘束するラッパー。"""
