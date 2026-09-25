"""Python探索パス直下のhlib_*拡張を検出する。独自Mayaプラグインはロードしない。"""

import importlib
import logging
import os
import pkgutil
import re
import sys

from ._core.discovery import discover_node_package, discover_plug_package
from ._core.registry import node_wrapper, plug_wrapper

__all__ = ["status", "node_wrapper", "plug_wrapper"]

_states = {}
_loading = False


def status():
    """dict: 拡張名ごとの状態と理由をコピーして返す。"""
    return {name: dict(state) for name, state in _states.items()}


def _initialize():
    """標準登録完了後に拡張を検出し、拡張単位で検証して登録する。"""
    global _loading, _states
    if _loading:
        return
    from .nodes import Node
    from .plugs import Plug

    _loading = True
    _states = {}
    try:
        candidates = {}
        for path in dict.fromkeys(sys.path):
            for info in pkgutil.iter_modules([path]):
                if info.ispkg and re.fullmatch(r"hlib_[a-z][a-z0-9_]*", info.name):
                    location = os.path.normcase(os.path.realpath(path))
                    candidates.setdefault(info.name, set()).add(location)
        for name, locations in sorted(candidates.items()):
            try:
                if len(locations) != 1:
                    raise ValueError("Duplicate extension package: " + name)
                previous = sys.modules.get(name)
                if getattr(previous, "HLIB_EXTENSION_API", None) == 1:
                    # 新しいhlib基底クラスで作り直す。外部SDK自体は再ロードしない。
                    for module_name in list(sys.modules):
                        if module_name == name or module_name.startswith(name + "."):
                            del sys.modules[module_name]
                package = importlib.import_module(name)
                if getattr(package, "HLIB_EXTENSION_API", None) != 1:
                    _states[name] = {"state": "skipped", "reason": "HLIB_EXTENSION_API != 1"}
                    continue
                available = package.is_available()
                if not isinstance(available, bool):
                    raise TypeError("is_available() must return bool")
                if not available:
                    _states[name] = {"state": "unavailable", "reason": "Optional dependency unavailable"}
                    continue
                entries = []
                for suffix, discover, base in (("nodes", discover_node_package, Node),
                                               ("plugs", discover_plug_package, Plug)):
                    if importlib.util.find_spec(name + "." + suffix) is None:
                        continue
                    wrappers, exports = discover(name + "." + suffix)
                    for key, cls in wrappers.items():
                        if not issubclass(cls, base):
                            raise TypeError("Invalid wrapper base: " + key)
                        if base._registry.lookup(key) is not None:
                            raise ValueError("Duplicate wrapper type: " + key)
                    entries.append((base._registry, wrappers, suffix, exports))
                # 全種類の検証成功後に登録。片方だけ登録された状態を作らない。
                for registry, wrappers, suffix, exports in entries:
                    for key, cls in wrappers.items():
                        registry.register(key, cls)
                    namespace = sys.modules[name + "." + suffix]
                    vars(namespace).update(exports)
                    namespace.__all__ = sorted(exports)
                _states[name] = {"state": "loaded", "reason": ""}
            except Exception as exc:
                _states[name] = {"state": "error", "reason": str(exc)}
                logging.getLogger(__name__).warning("hlib extension %s: %s", name, exc)
    finally:
        _loading = False
