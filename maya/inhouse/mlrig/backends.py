"""Soft IKバックエンドの選択。独自プラグインは明示選択時だけロードする。"""

from maya import cmds

from pathlib import Path
import mlib


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
        from mlrig.setups import SoftIK

        node = SoftIK.create(name, length)
        return node, node
    if backend == "bifrost":
        from mlrig.setups.bifrostSoftIK import SoftIK

        graph = SoftIK.create(name, length)
        return graph.getName(), graph.getParent().getFullName()
    if backend != "cpp":
        raise ValueError("Unknown backend: " + backend)
    version = str(cmds.about(version=True)).split()[0]
    if int(version) < 2025:
        raise RuntimeError("mlrig requires Maya 2025 or newer")
    plugin = Path(__file__).parent / "release" / "plug-ins" / "windows" / version / "mlrigNodes.mll"
    if not mlib.common.Plugin("mlrigNodes").isLoaded():
        if not plugin.is_file():
            raise RuntimeError("Build mlrigNodes for Maya " + version)
        # SafeModeの許可リストは変更しない。Mayaが拒否した場合はそのまま失敗する。
        mlib.common.Plugin(str(plugin)).load(quiet=True)
    node = mlib.createNode("mlrigSoftIK", name=name, skipSelect=True).getFullName()
    mlib.getPlug(node + ".length").set(length)
    return node, node
