"""Mayaプラグインの照会と管理。"""

# importlib.reloadでも、utilsへ移した関数の旧公開名を残さない。
for _name in ("parse_version", "is_at_least", "format_version"):
    globals().pop(_name, None)

from .module import Module
from .package import LOAD_FAILED, LOADED, MISSING, OUTDATED, SKIPPED, PluginPackage
from .plugin import Plugin
from .plugins import Plugins

__all__ = ['Plugin', 'Plugins', 'Module', 'PluginPackage',
           'SKIPPED', 'LOADED', 'MISSING', 'OUTDATED', 'LOAD_FAILED']
