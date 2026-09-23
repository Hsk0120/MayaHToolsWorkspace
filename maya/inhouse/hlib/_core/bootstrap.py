"""ノード・属性ラッパーの登録表を初期化する。"""

import importlib

from .registry import NodeRegistry


def initialize_node_api(package_name):
    """Node の型登録表を構築する。ルートへのクラス展開は行わない。

    Args:
        package_name (str): hlib パッケージの完全修飾名。

    Returns:
        NodeRegistry: 初期化した型登録表。
    """
    package = importlib.import_module(package_name + ".nodes")
    registry = NodeRegistry(package.Node)
    for type_name, wrapper in sorted(package._discovered_wrappers.items()):
        registry.register(type_name, wrapper)
    package.Node._registry = registry
    return registry


def initialize_plug_api(package_name):
    """Plug の型登録表を構築する。ルートへのクラス展開は行わない。

    Args:
        package_name (str): hlib パッケージの完全修飾名。

    Returns:
        NodeRegistry: 初期化した型登録表。
    """
    package = importlib.import_module(package_name + ".plugs")
    registry = NodeRegistry(package.Plug)
    for type_name, wrapper in sorted(package._discovered_wrappers.items()):
        registry.register(type_name, wrapper)
    package.Plug._registry = registry
    return registry


__all__ = ["initialize_node_api", "initialize_plug_api"]
