"""Maya標準HumanIKのHIKSolverNodeラッパー。"""

from .._core.registry import node_wrapper
from .node import Node


@node_wrapper('HIKSolverNode')
class HIKSolverNode(Node):
    """共通Node APIでアトリビュート・接続を扱う専用型。"""
