"""ノード・アトリビュートラッパーの登録表を初期化する。"""

import importlib

from .registry import NodeRegistry


def _initialize_registry(package_name, subpackage, base_name, inherited=False):
    """検出済みの標準型から新しい登録表を作り、基底へ取り付ける。

    Args:
        package_name (str): hlibの完全修飾名。
        subpackage (str): nodesまたはplugs。
        base_name (str): 登録表を保持する基底クラス名。
        inherited (bool): Mayaのノード型継承を解決するか。

    Returns:
        NodeRegistry: 再構築した登録表。任意拡張はこの後に登録する。
    """
    package = importlib.import_module(package_name + "." + subpackage)
    base = getattr(package, base_name)
    registry = NodeRegistry(base, resolve_inherited_types=inherited)
    registry.register_discovered(dict(sorted(package._discovered_wrappers.items())))
    base._registry = registry
    return registry


def initialize_node_api(package_name):
    """Node の型登録表を構築する。ルートへのクラス展開は行わない。

    Args:
        package_name (str): hlib パッケージの完全修飾名。

    Returns:
        NodeRegistry: 初期化した型登録表。
    """
    return _initialize_registry(package_name, "nodes", "Node", inherited=True)


def initialize_plug_api(package_name):
    """Plug の型登録表を構築する。ルートへのクラス展開は行わない。

    Args:
        package_name (str): hlib パッケージの完全修飾名。

    Returns:
        NodeRegistry: 初期化した型登録表。
    """
    return _initialize_registry(package_name, "plugs", "Plug")


__all__ = ["initialize_node_api", "initialize_plug_api"]
