"""見本にした頂点のウェイトを、別の頂点へ配る(平均、または距離に応じた加重平均)。

エッジループの両端だけを整えて見本にし、間の頂点へ距離で配ると、滑らかな移り変わりを手早く作れる。
硬いパーツは、見本の頂点の平均をそのまま配れば同じウェイトにそろう。インフルエンスは名前で対応させるので、
同じジョイントの別のメッシュへも配れる。
"""

from mlib.decorator import undoChunk

from . import influences as influences_module
from . import weights as weights_module

#: 覚えた見本。{"rows": [{インフルエンスの名前: 値}], "positions": [(x, y, z)]}(位置はワールド空間)。
_sample = {"rows": None, "positions": None}


def sampleVertices(target):
    """選んだ頂点のウェイトとワールド空間の位置を、見本として覚える。

    Args:
        target (Target): 対象。

    Returns:
        int: 覚えた頂点の数。
    """
    skin = target.requireSkin()
    vertices = target.requireVertices()
    influences = skin.getInfluences()
    names = [node.getNodeName() for node in influences]
    rows = weights_module.readRows(skin, influences, vertices)
    _sample["rows"] = [{name: value for name, value in zip(names, row) if value > 0.0} for row in rows]
    _sample["positions"] = [(point.x, point.y, point.z)
                            for point in target.mesh.getVertices(vertices).getPosition(worldSpace=True)]
    return len(vertices)


def hasSample():
    """見本を覚えているかを返す。

    Returns:
        bool: 覚えていればTrue。
    """
    return bool(_sample["rows"])


def sampleCount():
    """覚えている見本の頂点の数を返す。

    Returns:
        int: 頂点の数。
    """
    return len(_sample["rows"] or [])


def _columns(skin, influences):
    """見本のインフルエンスの名前から、skinCluster の列への対応を返す。"""
    names = [node.getNodeName() for node in influences]
    wanted = set()
    for row in _sample["rows"]:
        wanted.update(row)
    missing = sorted(wanted - set(names))
    if missing:
        raise ValueError("Not influences of {}: {}".format(skin.getNodeName(), ", ".join(missing)))
    return {name: names.index(name) for name in wanted}


@undoChunk("skinWeightKitApplySample")
def apply(target, mode="average", power=2.0):
    """見本のウェイトを、選んだ頂点へ配る。

    Args:
        target (Target): 対象。
        mode (str): ``"average"`` は見本の平均をすべての頂点へ、``"proximity"`` は頂点ごとに見本との距離の
            -power 乗で重み付けした平均を配る(見本と同じ位置の頂点は、その見本と同じ値になる)。
        power (float): 距離の重みの指数(大きいほど近い見本の影響が強い)。

    Returns:
        int: 変えた頂点の数。

    Raises:
        ValueError: 見本が無い、mode が不正、または見本のインフルエンスが対象に無い場合。
    """
    if not hasSample():
        raise ValueError("Sample vertices first")
    if mode not in ("average", "proximity"):
        raise ValueError("mode must be 'average' or 'proximity'")
    skin = target.requireSkin()
    vertices = target.requireVertices()
    influences = skin.getInfluences()
    column_of = _columns(skin, influences)
    locked = [influences_module.isLocked(node) for node in influences]
    samples = []
    for row in _sample["rows"]:
        full = [0.0] * len(influences)
        for name, value in row.items():
            full[column_of[name]] = value
        samples.append(full)
    rows = weights_module.readRows(skin, influences, vertices)
    if mode == "average":
        mean = [sum(column) / len(samples) for column in zip(*samples)]
        written = [weights_module.fitRow(mean, row, locked) for row in rows]
    else:
        points = target.mesh.getVertices(vertices).getPosition(worldSpace=True)
        written = []
        for point, row in zip(points, rows):
            position = (point.x, point.y, point.z)
            distances = [sum((a - b) ** 2 for a, b in zip(position, other)) ** 0.5 for other in _sample["positions"]]
            nearest = min(range(len(distances)), key=lambda index: distances[index])
            if distances[nearest] <= weights_module.TOLERANCE:
                blended = list(samples[nearest])
            else:
                factors = [distance ** -power for distance in distances]
                total = sum(factors)
                blended = [sum(factor * sample[column] for factor, sample in zip(factors, samples)) / total
                           for column in range(len(influences))]
            written.append(weights_module.fitRow(blended, row, locked))
    weights_module.writeRows(skin, influences, vertices, written)
    return len(vertices)
