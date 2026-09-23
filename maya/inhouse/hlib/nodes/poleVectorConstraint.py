"""Maya の poleVectorConstraint を扱う。"""

from .._core.registry import node_wrapper
from .constraint import Constraint


@node_wrapper("poleVectorConstraint")
class PoleVectorConstraint(Constraint):
    """RP IK ハンドルの極ベクトルを拘束するラッパー。"""
