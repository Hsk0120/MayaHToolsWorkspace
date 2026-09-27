"""Soft IKバックエンドの選択。独自プラグインは明示選択時だけロードする。"""

from pathlib import Path
from maya import cmds

import hlib


def create_soft_ik(name, length, backend="bifrost"):
    """計算ノードと所有するルートを返す。

    Args:
        name (str): ノード名。
        length (float): 部位の骨長。
        backend (str): bifrostまたはcpp。

    Returns:
        tuple[str, str]: 計算ノード名と削除対象ルート。
    """
    if backend == "bifrost":
        from .soft_ik import build_graph

        graph = build_graph(name, length)
        # Bifrostのカスタムshapeは汎用Nodeとして解決されるため、DAG親だけcmdsで照会する。
        return graph.name(), cmds.listRelatives(graph.name(), parent=True, fullPath=True)[0]
    if backend != "cpp":
        raise ValueError("Unknown backend: " + backend)
    version = str(cmds.about(version=True)).split()[0]
    if int(version) < 2025:
        raise RuntimeError("hrig requires Maya 2025 or newer")
    plugin = Path(__file__).parent / "release" / "plug-ins" / "windows" / version / "hrigNodes.mll"
    if not hlib.plugins.Plugin("hrigNodes").is_loaded():
        if not plugin.is_file():
            raise RuntimeError("Build hrigNodes for Maya " + version)
        # SafeModeの許可リストは変更しない。Mayaが拒否した場合はそのまま失敗する。
        hlib.plugins.Plugin(str(plugin)).load(quiet=True)
    node = hlib.createNode("hrigSoftIK", name=name, skipSelect=True).full_name()
    hlib.plug(node + ".length").set(length)
    return node, node
