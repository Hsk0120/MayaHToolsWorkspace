"""ノードラッパーを検出して公開する。"""

from .._core.discovery import discover_node_package
from .node import Node
from .shape import Shape
from .transform import Transform

# Node/Shape/Transform は他モジュールからの型参照（isinstance 判定や基底クラスと
# しての利用）が多いため明示 import する。joint/mesh/camera/skinCluster などの
# 具象 wrapper は明示 import せず、discover_node_package の pkgutil スキャンだけで
# 検出・公開する（新規ファイル追加時に __init__.py の編集が不要という設計のため）。
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
