"""インフルエンスの一覧・ロック・影響する頂点の選択・追加と削除。"""

import fnmatch

import mlib
from mlib.decorator import undoChunk

from . import target as target_module

#: 影響しているとみなすウェイトの下限。
THRESHOLD = 1e-4


class InfluenceInfo(object):
    """一覧に出す1つのインフルエンスの情報。

    Args:
        node (mlib.Node): インフルエンス。
        locked (bool): ロックしているか。
        value (float | None): 選んだ頂点での平均のウェイト。頂点を選んでいなければNone。
    """

    def __init__(self, node, locked, value):
        self.node = node
        self.name = node.getName(node=True)
        self.locked = locked
        self.value = value


def find(skin, influence):
    """skinCluster のインフルエンスを、名前または Node から返す。

    Args:
        skin (mlib.SkinCluster): skinCluster。
        influence (mlib.Node | str): インフルエンス。

    Returns:
        mlib.Node: インフルエンス。

    Raises:
        ValueError: skinCluster のインフルエンスでない場合。
    """
    for node in skin.getInfluences():
        if node == influence or node.getName(node=True) == str(influence) or str(node) == str(influence):
            return node
    raise ValueError("{} is not an influence of {}".format(influence, skin.getName(node=True)))


def lockedFlags(skin, influences):
    """インフルエンスごとに、ロックされているかを返す(mlib の ``SkinCluster.getLockedInfluences``)。

    Args:
        skin (mlib.SkinCluster): skinCluster。
        influences (Iterable[mlib.Node]): 調べるインフルエンス。

    Returns:
        list[bool]: influences の順に、ロックされていればTrue。
    """
    locked = {node.getFullName() for node in skin.getInfluences(locked=True)}
    return [node.getFullName() in locked for node in influences]


def isLocked(skin, node):
    """インフルエンスがロックされているかを返す。

    Args:
        skin (mlib.SkinCluster): skinCluster。
        node (mlib.Node): インフルエンス。

    Returns:
        bool: ロックされていればTrue。
    """
    return lockedFlags(skin, [node])[0]


def setLocked(skin, nodes, state):
    """インフルエンスのロックを変える(mlib の ``SkinCluster.setInfluencesLocked``)。

    Args:
        skin (mlib.SkinCluster): skinCluster。
        nodes (Iterable[mlib.Node]): インフルエンス。
        state (bool): Trueはロック、Falseは解除。

    Returns:
        int: 変えた数。
    """
    nodes = list(nodes)
    if nodes:
        skin.setInfluencesLocked(nodes, bool(state))
    return len(nodes)


def lockOthers(target, keep):
    """指定したもの以外のインフルエンスをロックし、指定したものは解除する。

    Args:
        target (Target): 対象。
        keep (Iterable[mlib.Node]): ロックしないインフルエンス。

    Returns:
        int: ロックした数。
    """
    keep = list(keep)
    skin = target.requireSkin()
    with undoChunk("skinWeightKitLockOthers"):
        setLocked(skin, keep, False)
        return setLocked(skin, [node for node in skin.getInfluences() if node not in keep], True)


def listInfluences(target):
    """一覧に出すインフルエンスの情報を返す。

    Args:
        target (Target): 対象。

    Returns:
        list[InfluenceInfo]: skinCluster のインフルエンスの順。バインドされていなければ空。
    """
    if target is None or target.skin is None:
        return []
    influences = target.skin.getInfluences()
    values = [None] * len(influences)
    if target.vertices:
        flat = target.skin.getWeights(influences, vertices=target.vertices)
        width = len(influences)
        count = len(target.vertices)
        values = [sum(flat[row * width + column] for row in range(count)) / count for column in range(width)]
    locked = lockedFlags(target.skin, influences)
    return [InfluenceInfo(node, flag, value) for node, flag, value in zip(influences, locked, values)]


def affectedVertices(target, influence, threshold=THRESHOLD):
    """インフルエンスが影響している頂点の番号を返す。

    Args:
        target (Target): 対象。
        influence (mlib.Node | str): インフルエンス。
        threshold (float): これより大きいウェイトを影響とみなす。

    Returns:
        list[int]: 頂点の番号。
    """
    skin = target.requireSkin()
    return list(skin.getInfluenceVertices(find(skin, influence), threshold=threshold).indices)


def verticesInRange(target, influence, minimum, maximum):
    """インフルエンスの値が minimum 以上 maximum 以下の頂点を返す(選んだ頂点、またはメッシュ全体から探す)。

    Args:
        target (Target): 対象。
        influence (mlib.Node | str): インフルエンス。
        minimum (float): 値の下限。
        maximum (float): 値の上限。

    Returns:
        list[int]: 頂点の番号。

    Raises:
        ValueError: minimum が maximum より大きい場合。
    """
    if minimum > maximum:
        raise ValueError("The minimum must not be greater than the maximum")
    skin = target.requireSkin()
    vertices = target.editVertices()
    values = skin.getWeights([find(skin, influence)], vertices=vertices)
    return [vertex for vertex, value in zip(vertices, values) if minimum - 1e-9 <= value <= maximum + 1e-9]


def selectInRange(target, influence, minimum, maximum):
    """インフルエンスの値が範囲内の頂点を選ぶ。

    Args:
        target (Target): 対象。
        influence (mlib.Node | str): インフルエンス。
        minimum (float): 値の下限。
        maximum (float): 値の上限。

    Returns:
        int: 選んだ頂点の数。
    """
    return target_module.selectVertices(target.mesh, verticesInRange(target, influence, minimum, maximum))


def selectAffected(target, influence, threshold=THRESHOLD):
    """インフルエンスが影響している頂点を選ぶ。

    Args:
        target (Target): 対象。
        influence (mlib.Node | str): インフルエンス。
        threshold (float): これより大きいウェイトを影響とみなす。

    Returns:
        int: 選んだ頂点の数。
    """
    return target_module.selectVertices(target.mesh, affectedVertices(target, influence, threshold))


@undoChunk("skinWeightKitAddInfluences")
def addInfluences(target, joints):
    """ジョイントを、ウェイト0のインフルエンスとして足す。

    Args:
        target (Target): 対象。
        joints (Iterable[mlib.Joint]): 足すジョイント(既にあるものは飛ばす)。

    Returns:
        int: 足した数。
    """
    skin = target.requireSkin()
    existing = skin.getInfluences()
    new = [joint for joint in joints if joint not in existing]
    if new:
        skin.addInfluences(new)
    return len(new)


def _depth(node):
    """DAG の深さ(ワールド直下が0)。"""
    depth = 0
    parent = node.getParent()
    while parent is not None:
        depth += 1
        parent = parent.getParent()
    return depth


@undoChunk("skinWeightKitRemoveJoints")
def removeJoints(joints):
    """ジョイントを、影響しているすべての skinCluster から外す。外す前に、ウェイトを最も近い親のインフルエンスへ移す。

    深いジョイントから順に外すので、親子を一緒に選んでも、ウェイトは残る祖先のインフルエンスへ集まる。
    親にインフルエンスが無いジョイントのウェイトは、Maya の標準の再配分に任せる。ジョイントのノードは消さない。

    Args:
        joints (Iterable[mlib.Joint]): 外すジョイント。

    Returns:
        list[tuple[str, str, str | None]]: 外した (ジョイント, skinCluster, 移した先の親) の組。

    Raises:
        ValueError: ジョイントが無い、またはどの skinCluster のインフルエンスでもない場合。
    """
    joints = list(joints)
    if not joints:
        raise ValueError("Select the joints to remove from the skin")
    skins = []
    for joint in joints:
        for skin in joint.getSkinClusters():
            if skin not in skins:
                skins.append(skin)
    removed = []
    for skin in skins:
        removed.extend(_remove_from(skin, joints))
    if not removed:
        raise ValueError("The selected joints are not influences of any skinCluster")
    return removed


def matchingInfluences(target, patterns):
    """名前がパターンに合うインフルエンスを返す(``*`` と ``?`` を使えるワイルドカード。名前空間は除いて比べる)。

    Args:
        target (Target): 対象。
        patterns (str | Iterable[str]): パターン。文字列ならカンマか空白で区切った複数のパターン。

    Returns:
        list[mlib.Node]: 合ったインフルエンス(skinCluster の順)。
    """
    if isinstance(patterns, str):
        patterns = [part for part in patterns.replace(",", " ").split() if part]
    skin = target.requireSkin()
    return [node for node in skin.getInfluences()
            if any(fnmatch.fnmatchcase(node.getName(node=True).split(":")[-1], pattern) for pattern in patterns)]


@undoChunk("skinWeightKitRemoveMatching")
def removeMatching(target, patterns):
    """名前がパターンに合うジョイントを外し、ウェイトを最も近い親のインフルエンスへ移す(書出し前の補助のジョイントの削除)。

    Args:
        target (Target): 対象。
        patterns (str | Iterable[str]): パターン(例 ``"*_end, *_helper"``)。

    Returns:
        list[tuple[str, str, str | None]]: 外した (ジョイント, skinCluster, 移した先の親) の組。

    Raises:
        ValueError: 合うジョイントが無い場合。
    """
    found = [node for node in matchingInfluences(target, patterns) if isinstance(node, mlib.Joint)]
    if not found:
        raise ValueError("No joint influence matches the pattern")
    return _remove_from(target.requireSkin(), found)


def _remove_from(skin, joints):
    """skinCluster のインフルエンスになっているジョイントを、深い順に外して親へウェイトを移す。

    Args:
        skin (mlib.SkinCluster): skinCluster。
        joints (Iterable[mlib.Joint]): 外すジョイント(インフルエンスでないものは飛ばす)。

    Returns:
        list[tuple[str, str, str | None]]: 外した (ジョイント, skinCluster, 移した先の親) の組。
    """
    joints = [joint for joint in joints if skin.hasInfluence(joint.getFullName())]
    ordered = sorted(joints, key=_depth, reverse=True)
    targets = [joint.getTransferTarget(skin) for joint in ordered]
    removed = [(joint.getName(node=True), skin.getName(node=True), target.getName() if target is not None else None)
               for joint, target in zip(ordered, targets)]
    if not joints:
        return removed
    try:
        skin.removeInfluences(joints)
    except ValueError:
        # 残る祖先の無いジョイントは一括解除で受け付けないため、1本ずつ外して Maya の標準の再配分に任せる。
        for joint in ordered:
            skin.removeInfluences(joint, requireAncestor=False)
    return removed



@undoChunk("skinWeightKitRemoveInfluence")
def removeInfluence(target, influence):
    """インフルエンスを外す。外す前に、そのウェイトを最も近い親のインフルエンスへ移す。

    Args:
        target (Target): 対象。
        influence (mlib.Node | str): 外すインフルエンス。

    Returns:
        None: 値を返さない。
    """
    skin = target.requireSkin()
    skin.removeInfluences(find(skin, influence), requireAncestor=False)
