"""Maya標準HumanIKのHIKControlSetNodeラッパー。"""

from .._core.registry import node_wrapper
from .node import Node


@node_wrapper('HIKControlSetNode')
class HIKControlSetNode(Node):
    """共通Node APIでアトリビュート・接続を扱う専用型。"""
