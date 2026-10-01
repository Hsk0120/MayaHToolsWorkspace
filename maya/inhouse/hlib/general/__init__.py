"""Mayaの実行環境・シーン・UI・イベントを扱う参照型を公開する。

ノードやアトリビュート以外のMayaサービスはここへ集約する。
importだけでプラグインのロード、UI生成、イベント登録は行わない。
"""

from .module import Module
from .color import Color, Colors
from .plugin import Plugin
from .plugins import Plugins
from .pluginPackage import LOAD_FAILED, LOADED, MISSING, OUTDATED, SKIPPED, PluginPackage
from .workspace import Workspace
from .preferences import Preferences

# リロード時にも廃止した設定クラスを公開しない。
globals().pop("Units", None)
from .selection import Selection
from .scene import Scene
from .namespace import Namespace
from .uiElement import UiElement
from .nodeEditor import NodeEditor
from .graphEditor import GraphEditor
from .mainWindow import MainWindow
from .timeSlider import TimeSlider
from .viewport import Viewport
from .outliner import Outliner
from .channelBox import ChannelBox
from .deferred import Deferred
from .scriptJob import ScriptJob
from .scriptJobs import ScriptJobs

__all__ = [
    "Color", "Colors", "Module", "Plugin", "Plugins", "PluginPackage",
    "LOAD_FAILED", "LOADED", "MISSING", "OUTDATED", "SKIPPED",
    "Workspace", "Preferences", "Selection", "Scene", "Namespace",
    "UiElement", "NodeEditor", "GraphEditor", "MainWindow", "TimeSlider",
    "Viewport", "Outliner", "ChannelBox", "Deferred", "ScriptJob", "ScriptJobs",
]

from .drivenKey import DrivenKey
from .drivenKeys import DrivenKeys

__all__ += ["DrivenKey", "DrivenKeys"]

from .shelf import Shelf
from .shelfButton import ShelfButton

__all__ += ["Shelf", "ShelfButton"]

from .window import Window
from .workspaceControl import WorkspaceControl
from .workspaceLayout import WorkspaceLayout

__all__ += ["Window", "WorkspaceControl", "WorkspaceLayout"]

from .uiSnapshot import UiSnapshot

__all__ += ["UiSnapshot"]
