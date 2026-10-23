"""サブパッケージ・公開コマンドと再読み込みの入口を提供する。"""

# reloadは辞書を保持するため、前回の公開値を明示importの前に解除する。
for _name in globals().get("__all__", ()):
    if _name not in {"cmds", "nodes", "plugs", "components", "common", "logger",
                     "decorator", "maths", "reload"}:
        globals().pop(_name, None)
for _name in ("Node", "Shape", "Transform", "Plug", "ArrayPlug", "CompoundPlug",
              "NODE_REGISTRY", "PLUG_REGISTRY", "initialize_node_api",
              "initialize_plug_api", "reload_package", "importlib", "core", "scenes",
              "session", "units", "workspace", "selection", "context", "editors",
              "files", "namespaces", "plugins", "animation", "scene", "environment",
              "ui", "events", "utils", "decorators", "object", "Object", "extensions",
              "general", "json", "TYPE_CHECKING", "_command_exports", "_importlib", "_bootstrap"):
    globals().pop(_name, None)

from . import logger
from . import common, decorator, cmds, nodes, plugs, components, maths
from ._core.registry import NodeRegistry as _NodeRegistry
from ._core.reload import reload_package as _reload_package

# 標準型の対応表を構築してから任意拡張を検出する。
_node_registry = _NodeRegistry(nodes.Node, resolve_inherited_types=True)
_plug_registry = _NodeRegistry(plugs.Plug)
_node_registry.replace(nodes._WRAPPER_CLASSES)
_plug_registry.replace(plugs._WRAPPER_CLASSES)
nodes.Node._registry, plugs.Plug._registry = _node_registry, _plug_registry
del _node_registry, _plug_registry

from .cmds import (
    createNode,
    delete,
    duplicate,
    getNode,
    getPlug,
    ls,
    select,
)

__all__ = [
    "cmds",
    "common",
    "components",
    "createNode",
    "decorator",
    "delete",
    "duplicate",
    "getNode",
    "getPlug",
    "logger",
    "ls",
    "maths",
    "nodes",
    "plugs",
    "reload",
    "select",
]


def reload():
    """mlib配下を依存順に再読み込みする。

    Returns:
        tuple[module]: 再読み込みしたモジュール群。
    """
    _extensions._prepare_reload()
    return _reload_package(__name__)


from ._core import extensions as _extensions

_extensions._initialize()
