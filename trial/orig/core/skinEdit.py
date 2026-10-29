"""skinClusterのウェイト移送をOpenMayaで実行する(``SkinCluster.transferWeights`` のfast経路)。
"""


def transfer_weights(skin, pairs):
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
    if len(skin.mfn().getOutputGeometry()) != 1:
        raise NotImplementedError("fast weight transfer requires one geometry")
    names, values = skin._editable_weights()
    influences = skin.getInfluences()
    ids = [node.getUuid() for node in influences]
    width = len(names)
    # Nodeは循環import回避のため関数内で読み込む。
    from ..nodes.node import Node
    indices = [(ids.index(Node(source).getUuid()), ids.index(Node(target).getUuid()))
               for source, target in pairs]
    normalize = skin.getPlug("normalizeWeights").get() == 1
    for source, target in indices:
        for offset in range(0, len(values), width):
            if values[offset + source] <= 0:
                continue
            # MayaのtransformMoveWeightsは既存targetへ加算せず、
            # source値で置き換えてから正規化する。通常経路と同じ結果にする。
            values[offset + target] = values[offset + source]
            values[offset + source] = 0.0
            if normalize:
                total = sum(values[offset:offset + width])
                if total > 0:
                    values[offset:offset + width] = [v / total for v in values[offset:offset + width]]
    skin.setWeights(names, values, fast=True)
