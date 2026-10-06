"""Soft IKバックエンドの選択。独自プラグインは明示選択時だけロードする。"""

from maya import cmds

from pathlib import Path
import hlib


def create_soft_ik(name, length, backend="standard"):
    """計算ノードと所有するルートを返す。

    Args:
        name (str): ノード名。
        length (float): 部位の骨長。
        backend (str): standard（標準ノード）、bifrostまたはcpp。

    Returns:
        tuple[str, str]: 計算ノード名と削除対象ルート。
    """
    if backend == "standard":
        from hrig.setups import SoftIK

        node = SoftIK.create(name, length)
        return node, node
    if backend == "bifrost":
        from hrig.setups.bifrostSoftIK import SoftIK

        graph = SoftIK.create(name, length)
        return graph.getName(), graph.getParent().getFullName()
    if backend != "cpp":
        raise ValueError("Unknown backend: " + backend)
    version = str(cmds.about(version=True)).split()[0]
    if int(version) < 2025:
        raise RuntimeError("hrig requires Maya 2025 or newer")
    plugin = Path(__file__).parent / "release" / "plug-ins" / "windows" / version / "hrigNodes.mll"
    if not hlib.environment.Plugin("hrigNodes").isLoaded():
        if not plugin.is_file():
            raise RuntimeError("Build hrigNodes for Maya " + version)
        # SafeModeの許可リストは変更しない。Mayaが拒否した場合はそのまま失敗する。
        hlib.environment.Plugin(str(plugin)).load(quiet=True)
    node = hlib.createNode("hrigSoftIK", name=name, skipSelect=True).getFullName()
    hlib.getPlug(node + ".length").set(length)
    return node, node
