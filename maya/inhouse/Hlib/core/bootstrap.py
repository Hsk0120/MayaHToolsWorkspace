"""ノード・属性ラッパーの登録表と公開 API を初期化する。"""

import importlib

from .registry import NodeRegistry


def initialize_node_api(package_name, target_globals):
    """node package を読み込み、target_globals に公開 class と registry を設定する。

    Args:
        package_name (str): Hlib package の完全修飾名。
        target_globals (dict): 公開 class / registry を書き込む先の globals() 辞書。

    Returns:
        dict[str, type]: 公開する class 名から class への対応表（``__all__`` の構築に使う）。
    """
    node_package = importlib.import_module(package_name + ".nodes")
    if not hasattr(node_package, "_discovered_wrappers"):
        node_package = importlib.reload(node_package)

    node_exports = node_package._discovered_exports
    for export_name in node_exports:
        target_globals.pop(export_name, None)
    target_globals.update(node_exports)

    node_cls = node_package.Node
    node_registry = NodeRegistry(node_cls)
    for node_type, wrapper_class in sorted(node_package._discovered_wrappers.items()):
        node_registry.register(node_type, wrapper_class)
    node_cls._registry = node_registry

    target_globals.update(
        _node_package=node_package,
        Node=node_cls,
        Shape=node_package.Shape,
        Transform=node_package.Transform,
        NODE_REGISTRY=node_registry,
    )

    return node_exports


def initialize_plug_api(package_name, target_globals):
    """plugs package を読み込み、target_globals に公開 class と registry を設定する。

    Args:
        package_name (str): Hlib package の完全修飾名。
        target_globals (dict): 公開 class / registry を書き込む先の globals() 辞書。

    Returns:
        dict[str, type]: 公開する class 名から class への対応表（``__all__`` の構築に使う）。
    """
    plug_package = importlib.import_module(package_name + ".plugs")
    if not hasattr(plug_package, "_discovered_wrappers"):
        plug_package = importlib.reload(plug_package)

    plug_exports = plug_package._discovered_exports
    for export_name in plug_exports:
        target_globals.pop(export_name, None)
    target_globals.update(plug_exports)

    plug_cls = plug_package.Plug
    plug_registry = NodeRegistry(plug_cls)
    for plug_type, wrapper_class in sorted(plug_package._discovered_wrappers.items()):
        plug_registry.register(plug_type, wrapper_class)
    plug_cls._registry = plug_registry

    target_globals.update(
        _plug_package=plug_package,
        Plug=plug_cls,
        ArrayPlug=plug_package.ArrayPlug,
        CompoundPlug=plug_package.CompoundPlug,
        PLUG_REGISTRY=plug_registry,
    )

    return plug_exports


__all__ = ["initialize_node_api", "initialize_plug_api"]
