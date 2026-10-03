"""Maya付属プラグインのTHdependNode基底型。"""

from .._core.registry import node_wrapper
from .node import Node


@node_wrapper("THdependNode")
class THDependNode(Node):
    """Maya付属プラグインのTHdependNode基底型。"""
