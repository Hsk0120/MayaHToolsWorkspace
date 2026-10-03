"""Python探索パス直下のhlib_*拡張を検出する。独自Mayaプラグインはロードしない。"""

import ast
import importlib
import os
import pkgutil
import re
import sys
import tokenize
from pathlib import Path

from ._core.discovery import discover_node_package, discover_plug_package
from ._core.registry import node_wrapper, plug_wrapper
from .utils import logger

__all__ = ["status", "node_wrapper", "plug_wrapper"]

_states = {}
_loading = False
_extension_pattern = re.compile(re.escape(__package__) + r"_[a-z][a-z0-9_]*")
# 親のimportに失敗すると子だけsys.modulesに残るため、試行した名前も保持する。
# extensions自体のreloadでも、次の一括解除まで追跡を失わない。
_attempted = globals().get("_attempted", set())


def status():
    """dict: 拡張名ごとの状態と理由をコピーして返す。"""
    return {name: dict(state) for name, state in _states.items()}


def _prepare_reload():
    """本体の再読み込み前に、宣言済み・読み込み失敗の拡張をまとめて解除する。

    外部SDKやMayaプラグインは対象外。保持済みのPython参照は利用側で取得し直す。
    初期化途中の再入では、モジュールを一つも削除せず拒否する。
    """
    roots = {name for name, module in list(sys.modules.items())
             if _extension_pattern.fullmatch(name)
             and getattr(module, "HLIB_EXTENSION_API", None) == 1}
    roots.update(_attempted)
    if _loading or any(getattr(getattr(sys.modules.get(name), "__spec__", None),
                               "_initializing", False) for name in roots):
        raise RuntimeError("Cannot reload " + __package__ + " while an extension is initializing")
    for name in list(sys.modules):
        if name.split(".", 1)[0] in roots:
            del sys.modules[name]
    _attempted.clear()


def _validate_dependencies(name, locations):
    """拡張のPythonソースにある他拡張へのimportを登録前に拒否する。

    Args:
        name (str): 検査する拡張名。
        locations (Iterable[str]): パッケージの親フォルダー。

    Raises:
        ValueError: 他のhlib_*へのimportがある場合。

    動的importまで実行して解析しない。拡張作者は動的importでも同じ規則に従う。
    """
    for location in locations:
        root = Path(location) / name
        for path in root.rglob("*.py"):
            if any(part in {"__tests__", "tests", "docs", "__pycache__"}
                   for part in path.relative_to(root).parts[:-1]):
                continue
            with tokenize.open(str(path)) as stream:
                tree = ast.parse(stream.read(), filename=str(path))
            for node in ast.walk(tree):
                imports = []
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and not node.level:
                    imports = [node.module or ""]
                for target in imports:
                    package = target.split(".", 1)[0]
                    if package != name and _extension_pattern.fullmatch(package):
                        raise ValueError("Extensions must not depend on each other: "
                                         + name + " -> " + package)


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
                if info.ispkg and _extension_pattern.fullmatch(info.name):
                    location = os.path.normcase(os.path.realpath(path))
                    candidates.setdefault(info.name, set()).add(location)
        for name, locations in sorted(candidates.items()):
            try:
                if len(locations) != 1:
                    raise ValueError("Duplicate extension package: " + name)
                previous = sys.modules.get(name)
                if getattr(getattr(previous, "__spec__", None), "_initializing", False):
                    raise RuntimeError("Extension __init__ must not import " + __package__ + " or wrappers; "
                                       "finish its declarations before loading submodules")
                _attempted.add(name)
                package = importlib.import_module(name)
                if getattr(package, "HLIB_EXTENSION_API", None) != 1:
                    _attempted.discard(name)
                    _states[name] = {"state": "skipped", "reason": "HLIB_EXTENSION_API != 1"}
                    continue
                available = package.is_available()
                if not isinstance(available, bool):
                    raise TypeError("is_available() must return bool")
                if not available:
                    _states[name] = {"state": "unavailable", "reason": "Optional dependency unavailable"}
                    continue
                _validate_dependencies(name, locations)
                entries = []
                for suffix, discover, base in (("nodes", discover_node_package, Node),
                                               ("plugs", discover_plug_package, Plug)):
                    if importlib.util.find_spec(name + "." + suffix) is None:
                        continue
                    wrappers, exports = discover(name + "." + suffix)
                    for key, cls in wrappers.items():
                        if any(_extension_pattern.fullmatch(base_cls.__module__.split(".", 1)[0])
                               and base_cls.__module__.split(".", 1)[0] != name
                               for base_cls in cls.__mro__):
                            raise TypeError("Extension wrappers must not inherit from another extension")
                        if not issubclass(cls, base):
                            raise TypeError("Invalid wrapper base: " + key)
                        if base._registry.lookup(key) is not None:
                            raise ValueError("Duplicate wrapper type: " + key)
                    entries.append((base._registry, wrappers, suffix, exports))
                # 全種類の検証成功後に登録。片方だけ登録された状態を作らない。
                snapshots = [(registry, dict(registry._classes), sys.modules[name + "." + suffix],
                              dict(vars(sys.modules[name + "." + suffix])))
                             for registry, _, suffix, _ in entries]
                try:
                    for registry, wrappers, suffix, exports in entries:
                        for key, cls in wrappers.items():
                            registry.register(key, cls)
                        namespace = sys.modules[name + "." + suffix]
                        vars(namespace).update(exports)
                        namespace.__all__ = sorted(exports)
                except Exception:
                    # 登録中の障害でも、この拡張より前の型と公開名へ戻す。
                    for registry, classes, namespace, attributes in snapshots:
                        registry._classes.clear()
                        registry._classes.update(classes)
                        vars(namespace).clear()
                        vars(namespace).update(attributes)
                    raise
                _states[name] = {"state": "loaded", "reason": ""}
            except Exception as exc:
                _states[name] = {"state": "error", "reason": str(exc)}
                logger.warning("%s extension %s: %s", __package__, name, exc)
    finally:
        _loading = False
