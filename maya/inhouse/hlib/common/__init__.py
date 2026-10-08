"""Mayaの状態・環境・UI・イベントと共通機能の入口を提供する。

各公開名は利用時に解決する。Node/Plugの初期化中にUIや選択関連のクラスを
先行importせず、再読み込み後も現在の実装モジュールから取得する。
"""

from importlib import import_module
from typing import TYPE_CHECKING

_exports = {
    "ChannelBox": ("channelBox", "ChannelBox"),
    "Color": ("color", "Color"),
    "CurveFit": ("curveFit", "CurveFit"),
    "Cycle": ("cycle", "Cycle"),
    "DampedSpring": ("dampedSpring", "DampedSpring"),
    "Deferred": ("deferred", "Deferred"),
    "DrivenKey": ("drivenKey", "DrivenKey"),
    "GraphEditor": ("graphEditor", "GraphEditor"),
    "LOAD_FAILED": ("pluginPackage", "LOAD_FAILED"),
    "LOADED": ("pluginPackage", "LOADED"),
    "MISSING": ("pluginPackage", "MISSING"),
    "MainWindow": ("mainWindow", "MainWindow"),
    "Module": ("module", "Module"),
    "Namespace": ("namespace", "Namespace"),
    "NodeEditor": ("nodeEditor", "NodeEditor"),
    "OUTDATED": ("pluginPackage", "OUTDATED"),
    "OptionVar": ("optionvar", "OptionVar"),
    "Outliner": ("outliner", "Outliner"),
    "Plugin": ("plugin", "Plugin"),
    "PluginPackage": ("pluginPackage", "PluginPackage"),
    "Preferences": ("preferences", "Preferences"),
    "SKIPPED": ("pluginPackage", "SKIPPED"),
    "ScalarGraph": ("scalarGraph", "ScalarGraph"),
    "Scene": ("scene", "Scene"),
    "ScriptJob": ("scriptJob", "ScriptJob"),
    "ScriptJobs": ("scriptJobs", "ScriptJobs"),
    "Selection": ("selection", "Selection"),
    "Shelf": ("shelf", "Shelf"),
    "ShelfButton": ("shelfButton", "ShelfButton"),
    "TimeSlider": ("timeSlider", "TimeSlider"),
    "UiElement": ("uiElement", "UiElement"),
    "UiSnapshot": ("uiSnapshot", "UiSnapshot"),
    "Version": ("version", "Version"),
    "Viewport": ("viewport", "Viewport"),
    "Window": ("window", "Window"),
    "Workspace": ("workspace", "Workspace"),
    "WorkspaceControl": ("workspaceControl", "WorkspaceControl"),
    "WorkspaceLayout": ("workspaceLayout", "WorkspaceLayout"),
    "legalizeName": ("naming", "legalizeName"),
    "progressBar": ("progress", "progressBar"),
    "units": ("units", None),
}

__all__ = sorted(_exports)

# reload前に保持された公開値や廃止名を残さず、常に定義元から解決する。
for _name in __all__ + ["legalize_name", "progress_bar"]:
    globals().pop(_name, None)

if TYPE_CHECKING:
    from . import units
    from .channelBox import ChannelBox
    from .color import Color
    from .curveFit import CurveFit
    from .cycle import Cycle
    from .dampedSpring import DampedSpring
    from .deferred import Deferred
    from .drivenKey import DrivenKey
    from .graphEditor import GraphEditor
    from .mainWindow import MainWindow
    from .module import Module
    from .namespace import Namespace
    from .nodeEditor import NodeEditor
    from .optionvar import OptionVar
    from .outliner import Outliner
    from .plugin import Plugin
    from .pluginPackage import LOAD_FAILED, LOADED, MISSING, OUTDATED, SKIPPED, PluginPackage
    from .preferences import Preferences
    from .scalarGraph import ScalarGraph
    from .scene import Scene
    from .scriptJob import ScriptJob
    from .scriptJobs import ScriptJobs
    from .selection import Selection
    from .shelf import Shelf
    from .shelfButton import ShelfButton
    from .timeSlider import TimeSlider
    from .uiElement import UiElement
    from .uiSnapshot import UiSnapshot
    from .version import Version
    from .viewport import Viewport
    from .window import Window
    from .workspace import Workspace
    from .workspaceControl import WorkspaceControl
    from .workspaceLayout import WorkspaceLayout
    from .naming import legalizeName
    from .progress import progressBar


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
