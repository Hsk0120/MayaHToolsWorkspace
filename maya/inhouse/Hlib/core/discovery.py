"""型メタデータを持つラッパークラスをパッケージから検出する。"""

import importlib
import inspect
import pkgutil


def discover_node_package(package_name):
    """パッケージ内の metadata 付き wrapper と export を発見する。

    Args:
        package_name (str): wrapper module を含む package の完全修飾名。

    Returns:
        tuple[dict[str, type], dict[str, type]]: Maya nodeType から wrapper
            class への対応表と、公開する class 名から class への対応表。

    Raises:
        ValueError: 同じ Maya nodeType に複数の wrapper class がある場合。
    """
    return _discover_typed_package(package_name, "__hlib_node_type__")


def discover_plug_package(package_name):
    """パッケージ内の metadata 付き plug wrapper と export を発見する。

    Args:
        package_name (str): wrapper module を含む package の完全修飾名。

    Returns:
        tuple[dict[str, type], dict[str, type]]: 属性データ型から wrapper
            class への対応表と、公開する class 名から class への対応表。

    Raises:
        ValueError: 同じ属性データ型に複数の wrapper class がある場合。
    """
    return _discover_typed_package(package_name, "__hlib_plug_type__")


def _discover_typed_package(package_name, type_attr):
    """パッケージ内の metadata 付き wrapper と export を発見する共通実装。

    Args:
        package_name (str): wrapper module を含む package の完全修飾名。
        type_attr (str): 型キーを保持するクラス属性名（例: ``__hlib_node_type__``）。

    Returns:
        tuple[dict[str, type], dict[str, type]]: 型キーから wrapper class への
            対応表と、公開する class 名から class への対応表。

    Raises:
        ValueError: 同じ型キーに複数の wrapper class がある場合。
    """
    package = importlib.import_module(package_name)
    wrappers = {}
    exports = {}
    module_names = sorted(
        name
        for _, name, _ in pkgutil.iter_modules(package.__path__)
        if not name.startswith("_")
    )
    for module_name in module_names:
        module = importlib.import_module(f"{package_name}.{module_name}")
        for wrapper_class in vars(module).values():
            if not inspect.isclass(wrapper_class) or wrapper_class.__module__ != module.__name__:
                continue
            metadata = wrapper_class.__dict__
            type_key = metadata.get(type_attr)
            if type_key is not None:
                if type_key in wrappers and wrappers[type_key] is not wrapper_class:
                    raise ValueError(f"Duplicate Hlib wrapper for {type_attr}: {type_key}")
                wrappers[type_key] = wrapper_class
            if metadata.get("__hlib_public__", False):
                exports[wrapper_class.__name__] = wrapper_class
    return wrappers, exports


__all__ = ["discover_node_package", "discover_plug_package"]
