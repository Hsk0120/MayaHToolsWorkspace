"""ウェイトの整理(小さい値の削除・正規化・最大数・丸め)と、不正な頂点の検出。

頂点を選んでいればその頂点、オブジェクトを選んでいればスキン全体を対象にする。
"""

from mlib.decorator import undoChunk

from . import influences as influences_module
from . import target as target_module
from . import weights as weights_module


@undoChunk("skinWeightKitPrune")
def prune(target, threshold):
    """ウェイトが threshold 未満のインフルエンスを0にし、合計を1に戻す(ロックしたものは変えない)。

    Args:
        target (Target): 対象。
        threshold (float): これ未満の値を0にする。

    Returns:
        int: 対象にした頂点の数。

    Raises:
        ValueError: threshold が負の場合。
    """
    if threshold < 0:
        raise ValueError("threshold must be 0 or more")
    skin = target.requireSkin()
    if not target.hasComponents():
        skin.pruneWeights(threshold)
        return target.mesh.getNumVertices()
    return _rewrite(target, lambda row, locked: [
        value if locked[index] or value >= threshold else 0.0 for index, value in enumerate(row)])


@undoChunk("skinWeightKitNormalize")
def normalize(target):
    """ウェイトの合計を1にする(ロックしたものは変えない)。

    Args:
        target (Target): 対象。

    Returns:
        int: 対象にした頂点の数。
    """
    return _rewrite(target, lambda row, locked: list(row))


@undoChunk("skinWeightKitLimit")
def limitInfluences(target, count):
    """頂点ごとのインフルエンスの数を count 以下にする(小さい値から0にし、合計を1に戻す)。

    Args:
        target (Target): 対象。
        count (int): 1頂点の最大数(1以上)。

    Returns:
        int: 対象にした頂点の数。

    Raises:
        ValueError: count が1未満の場合。
    """
    if count < 1:
        raise ValueError("count must be 1 or more")

    def keep_largest(row, locked):
        """ロックしたもの・大きい順の count 個だけを残す。"""
        order = sorted(range(len(row)), key=lambda index: (not locked[index], -row[index]))
        kept = set(order[:count])
        return [value if index in kept or locked[index] else 0.0 for index, value in enumerate(row)]

    return _rewrite(target, keep_largest)


@undoChunk("skinWeightKitRound")
def roundWeights(target, decimals=3):
    """ウェイトを小数 decimals 桁に丸め、合計のずれを最も大きいロックしていない値で吸収する。

    Args:
        target (Target): 対象。
        decimals (int): 残す小数の桁数(1以上)。

    Returns:
        int: 対象にした頂点の数。

    Raises:
        ValueError: decimals が1未満の場合。
    """
    if decimals < 1:
        raise ValueError("decimals must be 1 or more")
    skin = target.requireSkin()
    influences = skin.getInfluences()
    locked = [influences_module.isLocked(node) for node in influences]
    vertices = target.editVertices()
    rows = []
    for row in weights_module.readRows(skin, influences, vertices):
        rounded = [value if locked[index] else round(value, decimals) for index, value in enumerate(row)]
        free = [index for index in range(len(row)) if not locked[index]]
        if free:
            largest = max(free, key=lambda index: rounded[index])
            rounded[largest] = round(max(0.0, rounded[largest] + 1.0 - sum(rounded)), decimals + 3)
        rows.append(rounded)
    weights_module.writeRows(skin, influences, vertices, rows)
    return len(vertices)


def _rewrite(target, change):
    """行を change で変えてから、ロックを保って合計を1に戻して書く。"""
    skin = target.requireSkin()
    influences = skin.getInfluences()
    locked = [influences_module.isLocked(node) for node in influences]
    vertices = target.editVertices()
    rows = weights_module.readRows(skin, influences, vertices)
    written = [weights_module.fitRow(change(row, locked), row, locked) for row in rows]
    weights_module.writeRows(skin, influences, vertices, written)
    return len(vertices)


def badVertices(target, maxInfluences=None, tolerance=1e-3):
    """合計が1からずれた頂点と、インフルエンスの数が上限を超えた頂点を返す。

    Args:
        target (Target): 対象。
        maxInfluences (int | None): 1頂点の上限。Noneは skinCluster の maxInfluences。
        tolerance (float): 合計のずれの許容量。

    Returns:
        dict[str, list[int]]: ``"sum"``(合計のずれ)・``"count"``(上限超え)の頂点の番号。
    """
    skin = target.requireSkin()
    limit = skin.getMaxInfluences() if maxInfluences is None else maxInfluences
    influences = skin.getInfluences()
    vertices = target.editVertices()
    result = {"sum": [], "count": []}
    for vertex, row in zip(vertices, weights_module.readRows(skin, influences, vertices)):
        if abs(sum(row) - 1.0) > tolerance:
            result["sum"].append(vertex)
        if limit and sum(1 for value in row if value > influences_module.THRESHOLD) > limit:
            result["count"].append(vertex)
    return result


def selectBadVertices(target, maxInfluences=None):
    """不正な頂点(合計のずれ・上限超え)を選ぶ。

    Args:
        target (Target): 対象。
        maxInfluences (int | None): 1頂点の上限。Noneは skinCluster の maxInfluences。

    Returns:
        int: 選んだ頂点の数。
    """
    found = badVertices(target, maxInfluences)
    indices = sorted(set(found["sum"]) | set(found["count"]))
    return target_module.selectVertices(target.mesh, indices)
