"""Mayaの状態・環境・イベントと共通処理の入口を提供する。

各公開名は利用時に解決する。Node/Plugの初期化中に選択関連のクラスを
先行importせず、再読み込み後も現在の実装モジュールから取得する。
"""

from importlib import import_module
from typing import TYPE_CHECKING

# reload前に保持された公開値を、新しい公開一覧の構築前に解除する。
for _name in globals().get("__all__", ()):
    globals().pop(_name, None)

_exports = {
    "CurveFit": ("curveFit", "CurveFit"),
    "DampedSpring": ("dampedSpring", "DampedSpring"),
    "Deferred": ("deferred", "Deferred"),
    "DrivenKey": ("drivenKey", "DrivenKey"),
    "Keyframe": ("keyframe", "Keyframe"),
    "Keyframes": ("keyframe", "Keyframes"),
    "LOAD_FAILED": ("pluginPackage", "LOAD_FAILED"),
    "LOADED": ("pluginPackage", "LOADED"),
    "MISSING": ("pluginPackage", "MISSING"),
    "Module": ("module", "Module"),
    "Namespace": ("namespace", "Namespace"),
    "OUTDATED": ("pluginPackage", "OUTDATED"),
    "Plugin": ("plugin", "Plugin"),
    "PluginPackage": ("pluginPackage", "PluginPackage"),
    "ProgressCancelled": ("progress", "ProgressCancelled"),
    "SKIPPED": ("pluginPackage", "SKIPPED"),
    "ScalarGraph": ("scalarGraph", "ScalarGraph"),
    "ScriptJob": ("scriptJob", "ScriptJob"),
    "ScriptJobs": ("scriptJobs", "ScriptJobs"),
    "Selection": ("selection", "Selection"),
    "Time": ("sceneTime", "Time"),
    "Version": ("version", "Version"),
    "progressBar": ("progress", "progressBar"),
    "units": ("units", None),
}

__all__ = sorted(_exports)

# reload前に保持された公開値や廃止名を残さず、常に定義元から解決する。
for _name in __all__ + ["legalizeName", "legalize_name", "progress_bar"]:
    globals().pop(_name, None)

if TYPE_CHECKING:
    from . import units
    from .curveFit import CurveFit
    from .dampedSpring import DampedSpring
    from .deferred import Deferred
    from .drivenKey import DrivenKey
    from .keyframe import Keyframe, Keyframes
    from .module import Module
    from .namespace import Namespace
    from .plugin import Plugin
    from .pluginPackage import LOAD_FAILED, LOADED, MISSING, OUTDATED, SKIPPED, PluginPackage
    from .scalarGraph import ScalarGraph
    from .sceneTime import Time
    from .scriptJob import ScriptJob
    from .scriptJobs import ScriptJobs
    from .selection import Selection
    from .version import Version
    from .progress import ProgressCancelled, progressBar


def __getattr__(name):
    """公開名を現在の実装モジュールから取得する。

    Args:
        name (str): 取得する公開名。

    Returns:
        object: クラス・関数・定数またはモジュール。

    Raises:
        AttributeError: 定義されていない公開名の場合。
    """
    if name not in _exports:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = _exports[name]
    module = import_module("." + module_name, __name__)
    return module if attribute_name is None else getattr(module, attribute_name)


def __dir__():
    """モジュール内の名前と遅延公開名を列挙する。

    Returns:
        list[str]: 補完・探索に使用する名前の一覧。
    """
    return sorted(set(globals()) | set(__all__))
