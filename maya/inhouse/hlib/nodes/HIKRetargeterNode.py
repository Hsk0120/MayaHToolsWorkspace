"""Maya標準HumanIKのHIKRetargeterNodeラッパー。"""

from .._core.registry import node_wrapper
from .node import Node


@node_wrapper('HIKRetargeterNode')
class HIKRetargeterNode(Node):
    """共通Node APIでアトリビュート・接続を扱う専用型。"""
