"""サブパッケージ・公開コマンドと再読み込みの入口を提供する。"""

# reloadは辞書を保持するため、前回の公開値を明示importの前に解除する。
for _name in globals().get("__all__", ()):
    if _name not in {"cmds", "nodes", "plugs", "components", "common", "logger",
                     "core", "decorator", "util", "maths", "json", "reload"}:
        globals().pop(_name, None)
for _name in ("Node", "Shape", "Transform", "Plug", "CompoundPlug",
              "NODE_REGISTRY", "PLUG_REGISTRY", "initialize_node_api",
              "initialize_plug_api", "reload_package", "importlib", "_core", "scenes",
              "session", "units", "workspace", "selection", "context", "editors",
              "files", "namespaces", "plugins", "animation", "scene", "environment",
              "ui", "events", "utils", "decorators", "object", "Object", "extensions",
              "general", "TYPE_CHECKING", "_command_exports", "_importlib", "_bootstrap"):
    globals().pop(_name, None)

from . import logger
from . import util, core, common, decorator, cmds, nodes, plugs, components, maths, json
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
    bakeDeformer,
    bakeResults,
    bindSkin,
    createBlendShape,
    createCircle,
    createCluster,
    createContainer,
    createCurve,
    createDagContainer,
    createDagPose,
    createGroup,
    createIkHandle,
    createJointChain,
    createLattice,
    createLocator,
    createNode,
    createNurbsPlane,
    createPolyCube,
    createPolyCylinder,
    createPolyPlane,
    createPolySphere,
    createWire,
    delete,
    duplicate,
    getNode,
    getPlug,
    ls,
    objExists,
    select,
)

#: mlib.<クラス名>で取得するクラスを探すパッケージ。名前が重なるときは先にあるものを優先する。
_CLASS_PACKAGES = ("nodes", "plugs", "components", "maths", "common")
#: ルートから取得させないクラス。Objectは各型の共通基底で、mlib.core.object から取得する。
_EXCLUDED_CLASSES = frozenset({"Object"})

_names = [
    "bakeDeformer",
    "bakeResults",
    "bindSkin",

    "cmds",
    "common",
    "components",
    "core",
    "createBlendShape",
    "createCircle",
    "createCluster",
    "createContainer",
    "createCurve",
    "createDagContainer",
    "createDagPose",
    "createGroup",
    "createIkHandle",
    "createJointChain",
    "createLattice",
    "createLocator",
    "createNode",
    "createNurbsPlane",
    "createPolyCube",
    "createPolyCylinder",
    "createPolyPlane",
    "createPolySphere",
    "createWire",
    "decorator",
    "delete",
    "duplicate",
    "getNode",
    "getPlug",
    "json",
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


def _class_sources():
    """ルートから取得できるクラス名と、その所属パッケージの対応を作る。

    各パッケージの ``__all__`` のうちクラスだけを対象にし、ルートの名前と ``_CLASS_PACKAGES`` の
    先にあるパッケージを優先する。commonは遅延公開のためimportせず、大文字だけの名前(定数)を除く。

    Returns:
        dict[str, str]: クラス名から所属パッケージ名への対応。
    """
    sources = {}
    for package_name in _CLASS_PACKAGES:
        package = globals()[package_name]
        for name in package.__all__:
            if name in sources or name in _names or name in _EXCLUDED_CLASSES or not name[:1].isupper():
                continue
            if package_name == "common" and name.isupper():
                continue
            if package_name != "common" and not isinstance(getattr(package, name), type):
                continue
            sources[name] = package_name
    return sources


_classes = _class_sources()
__all__ = _names + sorted(_classes)

#: mlibの版番号。maya/modules/mlib.modと同じ値にする。
__version__ = "12.4.0"


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


def __getattr__(name):
    """各パッケージのクラスを ``mlib.<クラス名>`` で取得する。

    ``mlib.Joint`` は ``mlib.nodes.Joint`` と同じクラスを返す。値は保持せず毎回所属パッケージから
    取得するため、再読み込み後も現在のクラスを返す。どのパッケージにも無い先頭が大文字の名前は、
    ``mlib.nodes`` と同じく登録の無いMayaのnodeTypeの生成クラスとして解決する(例: ``mlib.PointLight``)。

    Args:
        name (str): クラス名。

    Returns:
        type: 所属パッケージのクラス、または生成クラス。

    Raises:
        AttributeError: 対象のクラスが無い場合。
    """
    package_name = _classes.get(name)
    if package_name is not None:
        return getattr(globals()[package_name], name)
    if name[:1].isupper() and name not in _EXCLUDED_CLASSES:
        try:
            return nodes.__getattr__(name)
        except AttributeError:
            pass
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """モジュール内の名前と、ルートから取得できるクラス名を列挙する。

    Returns:
        list[str]: 補完・探索に使用する名前の一覧。
    """
    return sorted(set(globals()) | set(__all__))


from .core import extensions as _extensions

_extensions._initialize()
