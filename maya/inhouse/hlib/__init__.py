"""サブパッケージと再読み込みの入口を提供する。"""

# 旧構成を読み込み済みのセッションでも、ルートの再公開名を残さない。
for _name in globals().get("__all__", ()):
    if _name not in {"cmds", "nodes", "plugs", "components", "files", "namespaces", "plugins", "units", "workspace", "editors", "maths", "json", "reload"}:
        globals().pop(_name, None)
for _name in ("Node", "Shape", "Transform", "Plug", "ArrayPlug", "CompoundPlug",
              "NODE_REGISTRY", "PLUG_REGISTRY", "initialize_node_api",
              "initialize_plug_api", "reload_package", "importlib", "core", "scenes", "session"):
    globals().pop(_name, None)

import importlib as _importlib
from typing import TYPE_CHECKING

from . import cmds, nodes, plugs, components, files, namespaces, plugins, units, workspace, editors, maths, json
globals().pop("scene", None)
from ._core import bootstrap as _bootstrap
from ._core.reload import reload_package as _reload_package

# importlib.reload(hlib) でも初期化関数の旧シグネチャを残さない。
_importlib.reload(_bootstrap)
_bootstrap.initialize_node_api(__name__)
_bootstrap.initialize_plug_api(__name__)

__all__ = ["cmds", "nodes", "plugs", "components", "files", "namespaces", "plugins", "units", "workspace", "editors", "maths", "reload"]
__all__.append("json")

# 静的解析(Pylance/pyright)向けの宣言。実行時には評価されず、上記の動的公開が実体。
# 公開名の一覧との一致は test_typing_exports.py が検証する。
if TYPE_CHECKING:
    from .cmds import (
        bakeResults,
        captureSelection,
        channelBox,
        constraint,
        createNode,
        currentTime,
        delete,
        drivenKey,
        duplicate,
        group,
        ls,
        node,
        objExists,
        outliner,
        scene,
        select,
        setKeyframe,
        timeSlider,
        viewport,
    )


def reload():
    """hlib 配下を依存順に再読み込みする。

    Returns:
        tuple[module]: 再読み込みしたモジュール群。
    """
    _prepare = getattr(cmds, "_prepare_reload", None)
    if _prepare is not None:
        _prepare()
    return _reload_package(__name__)


# コマンドは同じ関数を二つの入口で公開する。既存のパッケージ名や reload は保護する。
_command_exports = tuple(name for name in cmds.__all__ if name not in globals())
for _name in _command_exports:
    globals()[_name] = getattr(cmds, _name)
__all__ += list(_command_exports)

# 標準APIを利用できる状態にしてから任意拡張を検出する。
from . import extensions
extensions._initialize()
__all__.append("extensions")
