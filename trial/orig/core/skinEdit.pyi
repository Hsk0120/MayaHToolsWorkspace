# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""skinClusterのウェイト移送をOpenMayaで実行する(``SkinCluster.transferWeights`` のfast経路)。
"""

from mlib.nodes.skinCluster import SkinCluster


def transfer_weights(skin: SkinCluster, pairs: list[tuple[str, str]]) -> None:
    """skinPercentの移送とinteractive正規化を再現する。

    Args:
        skin (SkinCluster): 更新先。
        pairs (list[tuple[str, str]]): 検証済みのinfluence名ペア。

    Returns:
        None: 値を返さない。

    Raises:
        RuntimeError: ウェイトがロック・接続されていて書き込めない場合。
        NotImplementedError: geometryが1個でない場合。
    """
    ...
