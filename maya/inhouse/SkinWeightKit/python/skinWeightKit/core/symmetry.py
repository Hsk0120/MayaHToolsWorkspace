"""選んだ頂点のウェイトを、反対側の頂点へ写す(位置で頂点を対応させ、インフルエンスは名前の左右で入れ替える)。

メッシュ全体のミラー(Maya の Mirror Skin Weights)と違い、選んだ頂点だけを写せる。反対側の頂点は、
オブジェクト空間の座標を軸で反転した位置に最も近い頂点(許容範囲内)。
"""

import re

from mlib.decorator import undoChunk

from . import influences as influences_module
from . import weights as weights_module

#: 軸の名前と座標の成分の番号。
AXES = {"x": 0, "y": 1, "z": 2}

#: 名前を "_" で区切った語の左右の組。
TOKEN_PAIRS = (("L", "R"), ("l", "r"), ("Left", "Right"), ("left", "right"), ("Lf", "Rt"), ("lf", "rt"))

#: 名前の先頭・末尾に付く左右の語(区切りなし。leftArm・armLeft 等)。
AFFIX_PAIRS = (("left", "right"), ("Left", "Right"))


def oppositeName(name):
    """名前の左右を入れ替えた名前を返す(名前空間はそのまま)。左右の語が無ければ同じ名前。

    Args:
        name (str): インフルエンスの名前。

    Returns:
        str: 左右を入れ替えた名前。
    """
    namespace, _, short = name.rpartition(":")
    swap = {}
    for left, right in TOKEN_PAIRS:
        swap[left] = right
        swap[right] = left
    tokens = short.split("_")
    if len(tokens) > 1:
        changed = [swap.get(token, token) for token in tokens]
        if changed != tokens:
            return (namespace + ":" if namespace else "") + "_".join(changed)
    for left, right in AFFIX_PAIRS:
        for old, new in ((left, right), (right, left)):
            if short.startswith(old) and len(short) > len(old) and not short[len(old)].islower():
                return (namespace + ":" if namespace else "") + new + short[len(old):]
            if re.search(old + r"$", short) and len(short) > len(old):
                return (namespace + ":" if namespace else "") + short[:-len(old)] + new
    return name


def missingOpposites(names):
    """左右の語を持つのに、反対側の名前が無いものを返す(ミラーの前の確認)。

    Args:
        names (Iterable[str]): インフルエンスの名前。

    Returns:
        list[tuple[str, str]]: (名前, 見つからない反対側の名前) の組。
    """
    names = list(names)
    present = set(names)
    return [(name, oppositeName(name)) for name in names
            if oppositeName(name) != name and oppositeName(name) not in present]


def mirrorMap(mesh, vertices, axis="x", tolerance=0.01):
    """頂点ごとの反対側の頂点を返す。

    Args:
        mesh (mlib.Mesh): メッシュ。
        vertices (Iterable[int]): 調べる頂点。
        axis (str): ミラーの軸(``"x"``・``"y"``・``"z"``)。
        tolerance (float): 反転した位置と頂点の距離の許容量(cm、オブジェクト空間)。

    Returns:
        dict[int, int]: {頂点: 反対側の頂点}。見つからない頂点と、軸の上の頂点(反対側が自身)は含めない。

    Raises:
        ValueError: axis が不正、または tolerance が0以下の場合。
    """
    if axis not in AXES:
        raise ValueError("axis must be one of x, y, z")
    if tolerance <= 0:
        raise ValueError("tolerance must be greater than 0")
    pairs = mesh.getMirrorVertexMap(axis, tolerance)
    return {vertex: pairs[vertex] for vertex in vertices if vertex in pairs and pairs[vertex] != vertex}


@undoChunk("skinWeightKitMirrorSelected")
def mirrorVertices(target, axis="x", tolerance=0.01):
    """選んだ頂点のウェイトを、反対側の頂点へ写す(インフルエンスは名前の左右で入れ替える)。

    反対側の頂点のロックしたインフルエンスは変えず、残りで合計を1にする。左右の語が無いインフルエンスは
    同じインフルエンスへ写す。

    Args:
        target (Target): 対象。
        axis (str): ミラーの軸(``"x"``・``"y"``・``"z"``)。
        tolerance (float): 反対側の頂点を探す許容量(cm、オブジェクト空間)。

    Returns:
        tuple[int, int]: (写した頂点の数, 反対側が見つからなかった頂点の数)。

    Raises:
        ValueError: 反対側のインフルエンスが skinCluster に無い場合。
    """
    skin = target.requireSkin()
    vertices = target.requireVertices()
    influences = skin.getInfluences()
    names = [node.getNodeName() for node in influences]
    opposite = []
    missing = []
    for name in names:
        other = oppositeName(name)
        if other not in names:
            missing.append(other)
        opposite.append(names.index(other) if other in names else None)
    if missing:
        raise ValueError("Opposite influences are not in {}: {}".format(skin.getNodeName(), ", ".join(missing)))
    pairs = mirrorMap(target.mesh, vertices, axis, tolerance)
    sources = [vertex for vertex in vertices if vertex in pairs]
    destinations = [pairs[vertex] for vertex in sources]
    # 写し先が選んだ頂点と重なる場合(両側を選んだ場合)は、写し先を一度だけにする。
    unique = {}
    for source, destination in zip(sources, destinations):
        unique.setdefault(destination, source)
    destinations = sorted(unique)
    sources = [unique[destination] for destination in destinations]
    if not destinations:
        return 0, len(vertices)
    locked = [influences_module.isLocked(node) for node in influences]
    source_rows = weights_module.readRows(skin, influences, sources)
    destination_rows = weights_module.readRows(skin, influences, destinations)
    written = []
    for source_row, destination_row in zip(source_rows, destination_rows):
        swapped = [0.0] * len(influences)
        for column, value in enumerate(source_row):
            swapped[opposite[column]] += value
        written.append(weights_module.fitRow(swapped, destination_row, locked))
    weights_module.writeRows(skin, influences, destinations, written)
    return len(destinations), len(vertices) - len(pairs)
