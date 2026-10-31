# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Mayaの状態・環境・イベントと共通処理の入口を提供する。

各公開名は利用時に解決する。Node/Plugの初期化中に選択関連のクラスを
先行importせず、再読み込み後も現在の実装モジュールから取得する。
"""

from importlib import import_module
from typing import TYPE_CHECKING
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
from typing import Any

_exports: dict
__all__ = ['CurveFit', 'DampedSpring', 'Deferred', 'DrivenKey', 'Keyframe', 'Keyframes', 'LOADED', 'LOAD_FAILED', 'MISSING', 'Module', 'Namespace', 'OUTDATED', 'Plugin', 'PluginPackage', 'ProgressCancelled', 'SKIPPED', 'ScalarGraph', 'ScriptJob', 'ScriptJobs', 'Selection', 'Time', 'Version', 'progressBar', 'units']

def __getattr__(name: str) -> Any:
    """公開名を現在の実装モジュールから取得する。

    Args:
        name (str): 取得する公開名。

    Returns:
        object: クラス・関数・定数またはモジュール。

    Raises:
        AttributeError: 定義されていない公開名の場合。
    """
    ...

def __dir__() -> list[str]:
    """モジュール内の名前と遅延公開名を列挙する。

    Returns:
        list[str]: 補完・探索に使用する名前の一覧。
    """
    ...
