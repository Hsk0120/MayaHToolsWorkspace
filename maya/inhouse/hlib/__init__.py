"""サブパッケージ・公開コマンドと再読み込みの入口を提供する。"""

# reloadは辞書を保持するため、前回の公開値を明示importの前に解除する。
for _name in globals().get("__all__", ()):
    if _name not in {"cmds", "nodes", "plugs", "components", "common", "logger",
                     "decorator", "maths", "json", "reload"}:
        globals().pop(_name, None)
for _name in ("Node", "Shape", "Transform", "Plug", "ArrayPlug", "CompoundPlug",
              "NODE_REGISTRY", "PLUG_REGISTRY", "initialize_node_api",
              "initialize_plug_api", "reload_package", "importlib", "core", "scenes",
              "session", "units", "workspace", "selection", "context", "editors",
              "files", "namespaces", "plugins", "animation", "scene", "environment",
              "ui", "events", "utils", "decorators", "object", "Object", "extensions",
              "general", "TYPE_CHECKING", "_command_exports"):
    globals().pop(_name, None)

import importlib as _importlib

from . import logger
from . import common, decorator, cmds, nodes, plugs, components, maths, json
from ._core import bootstrap as _bootstrap
from ._core.reload import reload_package as _reload_package

# 標準型の対応表を構築してから任意拡張を検出する。
_importlib.reload(_bootstrap)
_bootstrap.initialize_node_api(__name__)
_bootstrap.initialize_plug_api(__name__)

from .cmds import (
    addAttr,
    addConstraint,
    attr,
    bakeResults,
    bindSkin,
    captureSelection,
    channelBox,
    createBlendShape,
    createCurve,
    createGroup,
    createIkHandle,
    createNode,
    createNurbs,
    createPolygon,
    createSet,
    createShader,
    createShadingGroup,
    createShelf,
    delete,
    drivenKey,
    duplicate,
    executeDeferred,
    getAttr,
    getChannelBox,
    getDrivenKey,
    getNode,
    getOutliner,
    getPlug,
    getScene,
    getShelf,
    getTimeSlider,
    getViewport,
    getWindow,
    getWorkspaceControl,
    getWorkspaceLayout,
    ls,
    makeIdentity,
    mirrorJoint,
    node,
    outliner,
    plug,
    reorder,
    requirePlugins,
    scene,
    select,
    shelf,
    timeSlider,
    viewport,
    window,
    workspaceControl,
    workspaceLayout,
)

__all__ = [
    "addAttr",
    "addConstraint",
    "attr",
    "bakeResults",
    "bindSkin",
    "captureSelection",
    "channelBox",
    "cmds",
    "common",
    "components",
    "createBlendShape",
    "createCurve",
    "createGroup",
    "createIkHandle",
    "createNode",
    "createNurbs",
    "createPolygon",
    "createSet",
    "createShader",
    "createShadingGroup",
    "createShelf",
    "decorator",
    "delete",
    "drivenKey",
    "duplicate",
    "executeDeferred",
    "getAttr",
    "getChannelBox",
    "getDrivenKey",
    "getNode",
    "getOutliner",
    "getPlug",
    "getScene",
    "getShelf",
    "getTimeSlider",
    "getViewport",
    "getWindow",
    "getWorkspaceControl",
    "getWorkspaceLayout",
    "json",
    "logger",
    "ls",
    "makeIdentity",
    "maths",
    "mirrorJoint",
    "node",
    "nodes",
    "outliner",
    "plug",
    "plugs",
    "reload",
    "reorder",
    "requirePlugins",
    "scene",
    "select",
    "shelf",
    "timeSlider",
    "viewport",
    "window",
    "workspaceControl",
    "workspaceLayout",
]


def reload():
    """hlib配下を依存順に再読み込みする。

    Returns:
        tuple[module]: 再読み込みしたモジュール群。
    """
    _extensions._prepare_reload()
    return _reload_package(__name__)


from ._core import extensions as _extensions

_extensions._initialize()
