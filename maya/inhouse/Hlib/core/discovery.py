"""Hlib package discovery helpers."""

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
            node_type = metadata.get("__hlib_node_type__")
            if node_type is not None:
                if node_type in wrappers and wrappers[node_type] is not wrapper_class:
                    raise ValueError(f"Duplicate Hlib wrapper for Maya nodeType: {node_type}")
                wrappers[node_type] = wrapper_class
            if metadata.get("__hlib_public__", False):
                exports[wrapper_class.__name__] = wrapper_class
    return wrappers, exports


__all__ = ["discover_node_package"]
