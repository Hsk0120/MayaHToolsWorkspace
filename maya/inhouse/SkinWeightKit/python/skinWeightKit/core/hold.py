"""スキン全体のウェイトを一時的に覚え、後で戻す(試しに大きく変えてから、元へ戻せるようにする)。

Undo を何回も戻さずに、覚えた時点へ一度で戻せる。メモリにだけ覚え、Maya を閉じると消える。
"""

from mlib.decorator import undoChunk

from . import weights as weights_module

#: 覚えたウェイト。{メッシュの名前: {"influences": [名前], "rows": [[値]]}}。
_held = {}


def hold(target):
    """メッシュ全体のウェイトを覚える(同じメッシュの前の分は置き換える)。

    Args:
        target (Target): 対象。

    Returns:
        int: 覚えた頂点の数。
    """
    skin = target.requireSkin()
    influences = skin.getInfluences()
    vertices = list(range(target.mesh.getNumVertices()))
    _held[str(target.mesh)] = {"influences": [node.getNodeName() for node in influences],
                               "rows": weights_module.readRows(skin, influences, vertices)}
    return len(vertices)


def hasHold(target):
    """メッシュのウェイトを覚えているかを返す。

    Args:
        target (Target | None): 対象。

    Returns:
        bool: 覚えていればTrue。
    """
    return target is not None and str(target.mesh) in _held


@undoChunk("skinWeightKitFetch")
def fetch(target):
    """覚えたウェイトへ戻す(1回の Undo)。頂点を選んでいれば、その頂点だけを戻す。

    Args:
        target (Target): 対象。

    Returns:
        int: 戻した頂点の数。

    Raises:
        ValueError: 覚えていない、頂点数が変わった、または覚えたインフルエンスが無い場合。
    """
    if not hasHold(target):
        raise ValueError("Hold the weights of {} first".format(target.mesh.getNodeName()))
    held = _held[str(target.mesh)]
    if len(held["rows"]) != target.mesh.getNumVertices():
        raise ValueError("The vertex count changed since Hold")
    skin = target.requireSkin()
    influences = skin.getInfluences()
    names = [node.getNodeName() for node in influences]
    missing = sorted(set(held["influences"]) - set(names))
    if missing:
        raise ValueError("Influences removed since Hold: " + ", ".join(missing))
    mapping = [names.index(name) for name in held["influences"]]
    vertices = target.editVertices()
    written = []
    for vertex in vertices:
        row = [0.0] * len(influences)
        for column, value in zip(mapping, held["rows"][vertex]):
            row[column] = value
        written.append(row)
    weights_module.writeRows(skin, influences, vertices, written)
    return len(vertices)
