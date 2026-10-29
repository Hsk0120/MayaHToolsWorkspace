"""mlibの型登録・初期化・再読み込み機能を公開する。"""

# 旧構成を読み込み済みでも、廃止した登録入口を残さない。
for _name in ("collection_export", "discover_node_package", "discover_plug_package",
              "node_wrapper", "plug_wrapper", "initialize_node_api", "initialize_plug_api", "bootstrap"):
    globals().pop(_name, None)

from .registry import NodeRegistry
from .reload import reload_package

__all__ = [
    "NodeRegistry",
    "reload_package",
]
