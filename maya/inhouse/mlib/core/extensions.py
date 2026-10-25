"""Python探索パス直下のmlib_*拡張を検出する。独自Mayaプラグインはロードしない。"""

import ast
import importlib
import importlib.machinery
import os
import pkgutil
import re
import sys
import tokenize
from collections.abc import Mapping
from pathlib import Path

from .. import logger

__all__ = ["status", "getDiagnostics"]

# importlib.reloadで廃止した登録デコレーターを残さない。
for _name in ("node_wrapper", "plug_wrapper", "discover_node_package", "discover_plug_package"):
    globals().pop(_name, None)

_states = {}
_loading = False
_diagnosing = False
_package_name = __package__.rpartition(".")[0]
_extension_pattern = re.compile(re.escape(_package_name) + r"_[a-z][a-z0-9_]*")
# 親のimportに失敗すると子だけsys.modulesに残るため、試行した名前も保持する。
# extensions自体のreloadでも、次の一括解除まで追跡を失わない。
_attempted = globals().get("_attempted", set())


def status():
    """最後の初期化で得た拡張名ごとの状態と理由をコピーして返す。

    現在の依存可用性は再照会しない。診断だけを更新する場合はgetDiagnosticsを使う。

    Returns:
        dict: 拡張名ごとの状態と理由をコピーして返す。
    """
    return {name: dict(state) for name, state in _states.items()}


def getDiagnostics():
    """初期化時の記録と、読込み済み宣言の現在の可用性を分けて取得する。

    status()は初期化記録だけを返す。この関数はis_available()を再照会するが、拡張の新規import・
    型登録・reload・Mayaプラグインのロードは行わない。is_available側は依存を遅延importできるが、
    シーン/UIを変更しないことが宣言の契約となる。

    Returns:
        dict[str, dict]: initializationは初期化記録のコピー（未記録ならNone）、availableはbool。
            宣言未読込・初期化中・宣言不正・再入・照会失敗ではavailable=Noneで、reasonへ理由を入れる。
            初期化記録と登録表は変更しない。
    """
    global _diagnosing
    modules = {name: module for name, module in list(sys.modules.items())
               if _extension_pattern.fullmatch(name)}
    names = set(_states) | set(modules)
    result = {}
    reentered = _diagnosing
    if not reentered:
        _diagnosing = True
    try:
        for name in sorted(names):
            initialization = _states.get(name)
            record = {"initialization": dict(initialization) if initialization is not None else None,
                      "available": None, "reason": ""}
            result[name] = record
            module = modules.get(name)
            if module is None:
                record["reason"] = "Extension declaration is not imported"
            elif _loading or getattr(getattr(module, "__spec__", None), "_initializing", False):
                record["reason"] = "Extension initialization is in progress"
            elif reentered:
                record["reason"] = "Availability query is in progress"
            elif vars(module).get("MLIB_EXTENSION_API") != 1:
                record["reason"] = "MLIB_EXTENSION_API != 1"
            else:
                try:
                    available = _is_available(module)
                    record["available"] = available
                    if not available:
                        record["reason"] = "Optional dependency unavailable"
                except Exception as exc:
                    record["reason"] = str(exc) or type(exc).__name__
    finally:
        if not reentered:
            _diagnosing = False
    return result


def _prepare_reload():
    """本体の再読み込み前に、宣言済み・読み込み失敗の拡張をまとめて解除する。

    外部SDKやMayaプラグインは対象外。保持済みのPython参照は利用側で取得し直す。
    初期化途中の再入では、モジュールを一つも削除せず拒否する。
    """
    roots = {name for name, module in list(sys.modules.items())
             if _extension_pattern.fullmatch(name)
             and getattr(module, "MLIB_EXTENSION_API", None) == 1}
    roots.update(_attempted)
    if _loading or any(getattr(getattr(sys.modules.get(name), "__spec__", None),
                               "_initializing", False) for name in roots):
        raise RuntimeError("Cannot reload " + _package_name + " while an extension is initializing")
    for name in list(sys.modules):
        if name.split(".", 1)[0] in roots:
            del sys.modules[name]
    _attempted.clear()


def _is_available(package):
    """宣言の可用性を照会し、初期化と診断で同じ型検証を使う。

    Args:
        package (ModuleType): 宣言の読み込みを完了した拡張パッケージ。

    Returns:
        bool: 拡張が現在利用可能か。

    Raises:
        TypeError: is_availableがcallableでない、またはboolを返さない場合。
    """
    query = vars(package).get("is_available")
    if not callable(query):
        raise TypeError("is_available must be callable")
    available = query()
    if not isinstance(available, bool):
        raise TypeError("is_available() must return bool")
    return available


def _validate_dependencies(name, locations):
    """拡張のPythonソースにある他拡張へのimportを登録前に拒否する。

    Args:
        name (str): 検査する拡張名。
        locations (Iterable[str]): パッケージの親フォルダー。

    Raises:
        ValueError: 他のmlib_*へのimportがある場合。

    動的importまで実行して解析しない。拡張作者は動的importでも同じ規則に従う。
    """
    for location in locations:
        root = Path(location) / name
        for path in root.rglob("*.py"):
            if any(part in {"__tests__", "tests", "docs", "_docs", "__pycache__"}
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


def _find_candidates():
    """探索パスの重複を除き、拡張名ごとの実配置を収集する。

    Returns:
        dict[str, set[str]]: 拡張名と正規化した配置先。importは行わない。
    """
    candidates = {}
    for path in dict.fromkeys(sys.path):
        if not _may_contain_candidate(path):
            continue
        for info in pkgutil.iter_modules([path]):
            if info.ispkg and _extension_pattern.fullmatch(info.name):
                location = os.path.normcase(os.path.realpath(path))
                candidates.setdefault(info.name, set()).add(location)
    return candidates


def _may_contain_candidate(path):
    """探索パスの直下に拡張名と一致する項目があり得るかを、パッケージ判定の前に調べる。

    pkgutil.iter_modulesは通常のフォルダーに対して全サブフォルダーの中身を一覧するため、
    Mayaの長い探索パスでは起動が遅くなる。通常のフォルダー(FileFinder)でパッケージとして
    返る名前はフォルダー名そのものなので、直下に名前が一致する項目が無ければ結果は空になる。
    zip等の他のimporterは判定せず、従来どおりiter_modulesへ任せる。

    Args:
        path (str): sys.pathの1項目。

    Returns:
        bool: iter_modulesで拡張の候補を探す必要があればTrue。
    """
    importer = pkgutil.get_importer(path)
    if not isinstance(importer, importlib.machinery.FileFinder):
        return True
    if importer.path is None or not os.path.isdir(importer.path):
        return False
    try:
        filenames = os.listdir(importer.path)
    except OSError:
        return False
    return any(_extension_pattern.fullmatch(filename) for filename in filenames)


def _load_candidate(name, locations):
    """拡張の軽量な宣言を読み、対象外・利用不可ならその状態を返す。

    Args:
        name (str): 検出した拡張名。
        locations (set[str]): 拡張が存在する親フォルダー。

    Returns:
        dict | None: 読み飛ばす場合の状態。利用可能な拡張ならNone。

    Raises:
        ValueError: 同じ名前の拡張が複数箇所にある場合。
        RuntimeError: 拡張の初期化中に再入した場合。
        TypeError: 可用性判定がboolを返さない場合。
    """
    if len(locations) != 1:
        raise ValueError("Duplicate extension package: " + name)
    previous = sys.modules.get(name)
    if getattr(getattr(previous, "__spec__", None), "_initializing", False):
        raise RuntimeError("Extension __init__ must not import " + _package_name + " or wrappers; "
                           "finish its declarations before loading submodules")
    _attempted.add(name)
    package = importlib.import_module(name)
    if getattr(package, "MLIB_EXTENSION_API", None) != 1:
        _attempted.discard(name)
        return {"state": "skipped", "reason": "MLIB_EXTENSION_API != 1"}
    available = _is_available(package)
    if not available:
        return {"state": "unavailable", "reason": "Optional dependency unavailable"}
    return None


def _validated_entries(name, bases):
    """全種類の明示宣言を検証し、まだ登録せずに対応表を集める。

    Args:
        name (str): 利用可能な拡張名。
        bases (Iterable[tuple[str, type]]): サブパッケージ名と必須の基底型。

    Returns:
        list[tuple[NodeRegistry, dict[str, type]]]: 登録表と検証済みの型対応。

    Raises:
        ValueError: 型名が不正、または既存登録と衝突する場合。
        TypeError: 宣言・基底型・他拡張からの継承が不正な場合。
    """
    entries = []
    for suffix, base in bases:
        if importlib.util.find_spec(name + "." + suffix) is None:
            continue
        namespace = importlib.import_module(name + "." + suffix)
        # 公開名は拡張の__init__で定義する。ここでは型対応だけを検証する。
        declared = getattr(namespace, "_WRAPPER_CLASSES", {})
        if not isinstance(declared, Mapping):
            raise TypeError("_WRAPPER_CLASSES must be a mapping")
        wrappers = dict(declared)
        for key, cls in wrappers.items():
            if not isinstance(key, str) or not key:
                raise ValueError("Wrapper type must be a non-empty string")
            if not isinstance(cls, type) or not issubclass(cls, base):
                raise TypeError("Invalid wrapper base: " + key)
            if any(_extension_pattern.fullmatch(base_cls.__module__.split(".", 1)[0])
                   and base_cls.__module__.split(".", 1)[0] != name
                   for base_cls in cls.__mro__):
                raise TypeError("Extension wrappers must not inherit from another extension")
            if base._registry.lookup(key) is not None:
                raise ValueError("Duplicate wrapper type: " + key)
        entries.append((base._registry, wrappers))
    return entries


def _apply_entries(entries):
    """検証済みの全登録表を更新し、途中の障害では全表を元に戻す。

    Args:
        entries (list[tuple[NodeRegistry, dict[str, type]]]): 適用する型対応。

    Raises:
        Exception: 復元後、登録中の例外をそのまま再送出する。
    """
    snapshots = [(registry, registry._snapshot()) for registry, _ in entries]
    try:
        for registry, wrappers in entries:
            for key, cls in wrappers.items():
                registry.register(key, cls)
    except Exception:
        for registry, snapshot in snapshots:
            registry._restore(snapshot)
        raise


def _initialize():
    """標準登録完了後に拡張を検出し、拡張単位で検証して登録する。"""
    global _loading, _states
    if _loading:
        return
    from ..nodes import Node
    from ..plugs import Plug

    _loading = True
    _states = {}
    try:
        for name, locations in sorted(_find_candidates().items()):
            try:
                state = _load_candidate(name, locations)
                if state is None:
                    _validate_dependencies(name, locations)
                    entries = _validated_entries(name, (("nodes", Node), ("plugs", Plug)))
                    _apply_entries(entries)
                    state = {"state": "loaded", "reason": ""}
                _states[name] = state
            except Exception as exc:
                _states[name] = {"state": "error", "reason": str(exc)}
                logger.warning("%s extension %s: %s", _package_name, name, exc)
    finally:
        _loading = False
