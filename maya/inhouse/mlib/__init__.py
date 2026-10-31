"""サブパッケージ・公開コマンドと再読み込みの入口を提供する。"""

# reloadは辞書を保持するため、前回の公開値を明示importの前に解除する。
for _name in globals().get("__all__", ()):
    if _name not in {"cmds", "nodes", "plugs", "components", "common", "logger",
                     "core", "decorator", "util", "maths", "reload"}:
        globals().pop(_name, None)
for _name in ("Node", "Shape", "Transform", "Plug", "CompoundPlug",
              "NODE_REGISTRY", "PLUG_REGISTRY", "initialize_node_api",
              "initialize_plug_api", "reload_package", "importlib", "_core", "scenes",
              "session", "units", "workspace", "selection", "context", "editors",
              "files", "namespaces", "plugins", "animation", "scene", "environment",
              "ui", "events", "utils", "decorators", "object", "Object", "extensions",
              "general", "json", "TYPE_CHECKING", "_command_exports", "_importlib", "_bootstrap"):
    globals().pop(_name, None)

from . import logger
from . import util, core, common, decorator, cmds, nodes, plugs, components, maths
from .core.registry import NodeRegistry as _NodeRegistry
from .core.reload import reload_package as _reload_package

# 標準型の対応表を構築してから任意拡張を検出する。
_node_registry = _NodeRegistry(nodes.Node, generate_classes=True)
_plug_registry = _NodeRegistry(plugs.Plug)
_node_registry.replace(nodes._WRAPPER_CLASSES)
_plug_registry.replace(plugs._WRAPPER_CLASSES)
nodes.Node._registry, plugs.Plug._registry = _node_registry, _plug_registry
del _node_registry, _plug_registry

from .cmds import (
    bindSkin,
    createBlendShape,
    createCircle,
    createContainer,
    createCurve,
    createDagContainer,
    createDagPose,
    createIkHandle,
    createLocator,
    createNode,
    createPolyCube,
    createPolyCylinder,
    createPolyPlane,
    createPolySphere,
    delete,
    duplicate,
    getNode,
    getPlug,
    ls,
    objExists,
    select,
)

__all__ = [
    "bindSkin",
    "cmds",
    "common",
    "components",
    "core",
    "createBlendShape",
    "createCircle",
    "createContainer",
    "createCurve",
    "createDagContainer",
    "createDagPose",
    "createIkHandle",
    "createLocator",
    "createNode",
    "createPolyCube",
    "createPolyCylinder",
    "createPolyPlane",
    "createPolySphere",
    "decorator",
    "delete",
    "duplicate",
    "getNode",
    "getPlug",
    "logger",
    "ls",
    "maths",
    "nodes",
    "objExists",
    "plugs",
    "reload",
    "select",
    "util",
]

#: mlibの版番号。maya/modules/mlib.modと_docs/source/changelog.rstの先頭見出しと同じ値にする。
__version__ = "10.0.0"


def reload():
    """本体を再読み込みし、拡張を再探索して型登録を作り直す。

    宣言済み・読込み失敗の拡張モジュールを先に解除し、本体の再読込み中に拡張を再初期化する。
    外部SDKやMayaプラグイン自体は解除対象にしない。保持済みのクラス・関数・ラッパーは取り直す。
    拡張単位の読込み/登録失敗はcore.extensions.status()で確認する。途中状態の自動復元は保証しない。

    Returns:
        tuple[module]: 本体側で再読み込みしたモジュール群。拡張モジュールの一覧ではない。

    Raises:
        RuntimeError: 拡張初期化中の再入で、再読み込みを開始できない場合。
    """
    _extensions._prepare_reload()
    return _reload_package(__name__)


from .core import extensions as _extensions

_extensions._initialize()
