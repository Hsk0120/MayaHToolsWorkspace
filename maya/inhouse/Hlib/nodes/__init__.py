"""ノードラッパーを検出して公開する。"""

from ..core.discovery import discover_node_package
from .node import Node
from .shape import Shape
from .transform import Transform


for _export_name in globals().get("_discovered_exports", {}):
    globals().pop(_export_name, None)
_discovered_wrappers, _discovered_exports = discover_node_package(__name__)
globals().update(_discovered_exports)

__all__ = [
    "Node",
    "Shape",
    "Transform",
    *sorted(_discovered_exports),
]
