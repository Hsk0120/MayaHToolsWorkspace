"""選んだ頂点のウェイトを変える(値の設定・加算・倍率、ハンマー、スムーズ、平均、コピー/ペースト)。

どの操作も、ロックしたインフルエンス(lockInfluenceWeights)の値は変えず、残りのインフルエンスで合計を1にする。
各操作は1回の Undo にまとめる。
"""

import mlib
from mlib.decorator import undoChunk


from . import influences as influences_module

#: 値を変える方法。``set`` は指定値、``add`` は加算(負は減算)、``scale`` は倍率。
MODES = ("set", "add", "scale")

#: 合計が1からずれたとみなす量。
TOLERANCE = 1e-6

#: コピーしたウェイト。{インフルエンスの名前(名前空間を含む短い名前): 値}。
_clipboard = {"weights": None}


def readRows(skin, influences, vertices):
    """頂点ごとのウェイトの行を読む。

    Args:
        skin (mlib.SkinCluster): skinCluster。
        influences (list[mlib.Node]): 列にするインフルエンス。
        vertices (list[int]): 頂点の番号。

    Returns:
        list[list[float]]: 頂点の順に、influences の順の値。
    """
    if not vertices or not influences:
        return []
    return skin.getWeights(influences, vertices=vertices, rows=True)


def writeRows(skin, influences, vertices, rows, fast=False):
    """頂点ごとのウェイトの行を書く(正規化はしない。値はそのまま書く)。

    Args:
        skin (mlib.SkinCluster): skinCluster。
        influences (list[mlib.Node]): 列のインフルエンス。
        vertices (list[int]): 頂点の番号。
        rows (list[list[float]]): 頂点の順の行。
        fast (bool): TrueはUndoなしで書く(ドラッグ中の表示用)。

    Returns:
        None: 値を返さない。
    """
    if not vertices:
        return
    skin.setWeights(influences, rows, vertices=vertices, rows=True, fast=fast)



def fitRow(row, original, locked):
    """ロックした列を元の値に保ち、残りの列で合計を1にした行を返す。

    Args:
        row (list[float]): 新しい値の行(負は0にする)。
        original (list[float]): 元の行。
        locked (list[bool]): 列ごとのロック。

    Returns:
        list[float]: 合計1の行。残りの列の合計が0なら元の行。
    """
    result = [original[index] if locked[index] else max(0.0, value) for index, value in enumerate(row)]
    locked_sum = sum(value for index, value in enumerate(result) if locked[index])
    free_sum = sum(value for index, value in enumerate(result) if not locked[index])
    room = max(0.0, 1.0 - locked_sum)
    if free_sum <= TOLERANCE:
        return list(original)
    scale = room / free_sum
    return [value if locked[index] else value * scale for index, value in enumerate(result)]


def fitColumn(row, column, value, locked):
    """1つの列を value にし、残りのロックしていない列を比率を保って拡大縮小し、合計を1にした行を返す。

    Args:
        row (list[float]): 元の行。
        column (int): 変える列。
        value (float): 変える列の新しい値(0〜1に収める)。
        locked (list[bool]): 列ごとのロック。

    Returns:
        list[float]: 合計1の行。他の列が全部0なら、変える列にロック以外の残りを全部入れる。
    """
    locked_sum = sum(weight for index, weight in enumerate(row) if locked[index] and index != column)
    room = max(0.0, 1.0 - locked_sum)
    value = min(room, max(0.0, value))
    others = [index for index in range(len(row)) if index != column and not locked[index]]
    others_sum = sum(row[index] for index in others)
    result = list(row)
    if others_sum <= TOLERANCE:
        # 他に配れる値が無いので、変える列で残りを埋める(合計を1に保つ)。
        result[column] = room
        for index in others:
            result[index] = 0.0
        return result
    scale = (room - value) / others_sum
    result[column] = value
    for index in others:
        result[index] = row[index] * scale
    return result


def _context(target):
    """操作に使う skinCluster・インフルエンス・ロック・頂点を返す。"""
    skin = target.requireSkin()
    influences = skin.getInfluences()
    locked = [influences_module.isLocked(node) for node in influences]
    return skin, influences, locked, target.requireVertices()


def newValues(current, value, mode):
    """値の変え方に従って、新しい値を返す。

    Args:
        current (list[float]): 今の値。
        value (float): 指定値・加算量・倍率。
        mode (str): :data:`MODES` のどれか。

    Returns:
        list[float]: 0〜1に収めた新しい値。

    Raises:
        ValueError: mode が不正な場合。
    """
    if mode not in MODES:
        raise ValueError("mode must be one of " + ", ".join(MODES))
    if mode == "set":
        values = [value] * len(current)
    elif mode == "add":
        values = [weight + value for weight in current]
    else:
        values = [weight * value for weight in current]
    return [min(1.0, max(0.0, weight)) for weight in values]


@undoChunk("skinWeightKitSetValue")
def setValue(target, influence, value, mode="set"):
    """選んだ頂点で、インフルエンスのウェイトを設定・加算・倍率で変える。他のインフルエンスで合計を1にする。

    Args:
        target (Target): 対象。
        influence (mlib.Node | str): 変えるインフルエンス。
        value (float): 指定値・加算量(負は減算)・倍率。
        mode (str): ``"set"``・``"add"``・``"scale"``。

    Returns:
        int: 変えた頂点の数。

    Raises:
        ValueError: インフルエンスがロックされている場合、または mode が不正な場合。
    """
    skin = target.requireSkin()
    vertices = target.requireVertices()
    node = influences_module.find(skin, influence)
    if influences_module.isLocked(node):
        raise ValueError("{} is locked".format(node.getNodeName()))
    current = list(skin.getWeights([node], vertices=vertices))
    skin.setWeights([node], newValues(current, float(value), mode), vertices=vertices, normalize=True)
    return len(vertices)


def _segment_distance(point, start, end):
    """点と線分の距離。"""
    axis = [b - a for a, b in zip(start, end)]
    length_squared = sum(value * value for value in axis)
    if length_squared <= 1e-12:
        return sum((p - a) ** 2 for p, a in zip(point, start)) ** 0.5
    ratio = sum((p - a) * d for p, a, d in zip(point, start, axis)) / length_squared
    ratio = min(1.0, max(0.0, ratio))
    closest = [a + ratio * d for a, d in zip(start, axis)]
    return sum((p - c) ** 2 for p, c in zip(point, closest)) ** 0.5


def boneSegments(influences):
    """インフルエンスごとのボーンの線分(自身の位置から、子のジョイントの位置まで)を返す。

    Args:
        influences (list[mlib.Node]): インフルエンス。

    Returns:
        list[list[tuple[tuple, tuple]]]: インフルエンスごとの (始点, 終点) の組(子が無ければ始点と同じ点)。
    """
    result = []
    for node in influences:
        if isinstance(node, mlib.Joint):
            segments = node.getBoneSegments()
        else:
            # ジョイント以外のインフルエンス(transform 等)は、位置だけの点として扱う。
            point = node.getTranslation(worldSpace=True)
            segments = [(point, point)]
        result.append([((start.x, start.y, start.z), (end.x, end.y, end.z)) for start, end in segments])
    return result


@undoChunk("skinWeightKitAssignClosest")
def assignClosest(target):
    """選んだ頂点を、最も近いボーン(ジョイントから子のジョイントまでの線分)のインフルエンスへ100%にする。

    最初の大まかなウェイトを1対1で硬く割り当て、その後 Smooth でなじませる使い方を想定する。
    ロックしたインフルエンスは選ばず、その値も変えない。

    Args:
        target (Target): 対象(メッシュを選んでいれば全頂点)。

    Returns:
        int: 変えた頂点の数。

    Raises:
        ValueError: ロックしていないインフルエンスが無い場合。
    """
    skin = target.requireSkin()
    influences = skin.getInfluences()
    locked = [influences_module.isLocked(node) for node in influences]
    free = [column for column in range(len(influences)) if not locked[column]]
    if not free:
        raise ValueError("Every influence is locked")
    segments = boneSegments(influences)
    vertices = target.editVertices()
    points = target.mesh.getVertices(vertices).getPosition(worldSpace=True)
    rows = readRows(skin, influences, vertices)
    written = []
    for point, row in zip(points, rows):
        position = (point.x, point.y, point.z)
        best = min(free, key=lambda column: min(_segment_distance(position, start, end)
                                                for start, end in segments[column]))
        new = [value if locked[column] else (1.0 if column == best else 0.0) for column, value in enumerate(row)]
        written.append(fitRow(new, row, locked))
    writeRows(skin, influences, vertices, written)
    return len(vertices)


@undoChunk("skinWeightKitFlood")
def flood(target, influence, value):
    """選んだ頂点、またはメッシュ全体の頂点で、インフルエンスを指定値にする(Maya のペイントの Flood と同じ)。

    Args:
        target (Target): 対象(メッシュを選んでいれば全頂点)。
        influence (mlib.Node | str): 変えるインフルエンス。
        value (float): 新しい値。

    Returns:
        int: 変えた頂点の数。
    """
    return setVertexValues(target, target.editVertices(), influence, value)


@undoChunk("skinWeightKitSetVertexValue")
def setVertexValues(target, vertices, influence, value):
    """指定した頂点で、1つのインフルエンスを指定値にする(他のロックしていないインフルエンスで合計を1にする)。

    表のセルを書き換えたときに使う。選択ではなく、渡した頂点を対象にする。

    Args:
        target (Target): skinCluster を決める対象。
        vertices (Iterable[int]): 頂点の番号。
        influence (mlib.Node | str): 変えるインフルエンス。
        value (float): 新しい値(0〜1に収める)。

    Returns:
        int: 変えた頂点の数。

    Raises:
        ValueError: インフルエンスがロックされている場合。
    """
    skin = target.requireSkin()
    node = influences_module.find(skin, influence)
    if influences_module.isLocked(node):
        raise ValueError("{} is locked".format(node.getNodeName()))
    influences = skin.getInfluences()
    locked = [influences_module.isLocked(other) for other in influences]
    column = influences.index(node)
    vertices = list(vertices)
    rows = readRows(skin, influences, vertices)
    writeRows(skin, influences, vertices, [fitColumn(row, column, float(value), locked) for row in rows])
    return len(vertices)


def table(target, limit=500):
    """選んだ頂点のウェイトを表にする(どれかの頂点で使っているインフルエンスだけを列にする)。

    Args:
        target (Target): 対象。
        limit (int): 表に出す頂点の上限。

    Returns:
        dict: ``vertices``(list[int])・``influences``(list[str])・``rows``(list[list[float]])・
        ``sums``(list[float])・``counts``(list[int])・``truncated``(bool。上限で切ったか)。
    """
    skin = target.requireSkin()
    vertices = target.requireVertices()
    truncated = len(vertices) > limit
    vertices = vertices[:limit]
    influences = skin.getInfluences()
    rows = readRows(skin, influences, vertices)
    used = [column for column in range(len(influences)) if any(row[column] > 0.0 for row in rows)]
    return {
        "vertices": vertices,
        "influences": [influences[column].getNodeName() for column in used],
        "rows": [[row[column] for column in used] for row in rows],
        "sums": [sum(row) for row in rows],
        "counts": [sum(1 for value in row if value > 0.0) for row in rows],
        "truncated": truncated,
    }


@undoChunk("skinWeightKitHammer")
def hammer(target, method="uniform", radius=0.0):
    """選んだ頂点のウェイトを、隣の頂点のウェイトの(重み付き)平均にする(飛び出した頂点をならす)。

    Args:
        target (Target): 対象。
        method (str): 隣の頂点への重みの付け方(:data:`skinWeightKit.core.smoothing.METHODS`)。
        radius (float): 0より大きければ、辺でつながっていない半径内の頂点も平均に含める(cm)。

    Returns:
        int: 変えた頂点の数。
    """
    return _smooth(target, 1.0, 1, method, radius, False)


@undoChunk("skinWeightKitSmooth")
def smooth(target, strength=0.5, iterations=1, method="uniform", radius=0.0, keepMax=False):
    """選んだ頂点のウェイトを、隣の頂点との平均へ近づける(繰り返すほど広く滑らかになる)。

    Args:
        target (Target): 対象。
        strength (float): 1回で隣の平均へ近づける割合(0〜1)。
        iterations (int): 繰り返す回数(1以上)。
        method (str): 隣の頂点への重みの付け方(``"uniform"``・``"distance"``・``"cotangent"``)。
        radius (float): 0より大きければ、辺でつながっていない半径内の頂点も平均に含める(cm)。
        keepMax (bool): Trueは skinCluster の最大インフルエンス数を超えないようにする。

    Returns:
        int: 変えた頂点の数。

    Raises:
        ValueError: strength・iterations・method・radius が範囲外の場合。
    """
    if not 0.0 <= strength <= 1.0:
        raise ValueError("strength must be between 0 and 1")
    if iterations < 1:
        raise ValueError("iterations must be 1 or more")
    return _smooth(target, strength, int(iterations), method, radius, keepMax)


def _smooth(target, strength, iterations, method, radius, keepMax):
    """ハンマー・スムーズの共通の計算。"""
    # smoothing は行の計算(fitRow)をこのモジュールから使うため、循環参照を避けて呼出し時に読み込む。
    from . import smoothing
    skin, influences, locked, vertices = _context(target)
    neighbors = smoothing.neighborWeights(target.mesh, method, radius)
    wanted = set(vertices)
    for vertex in vertices:
        wanted.update(neighbor for neighbor, _weight in neighbors[vertex])
    order = sorted(wanted)
    rows = dict(zip(order, readRows(skin, influences, order)))
    limit = skin.getMaxInfluences() if keepMax else None
    for _ in range(iterations):
        updated = {}
        for vertex in vertices:
            updated[vertex] = smoothing.smoothRow(rows[vertex], [(rows[other], weight) for other, weight in
                                                                 neighbors[vertex]], strength, locked, limit)
        # 1回分を計算し終えてから反映する(頂点の並び順で結果が変わらないようにする)。
        rows.update(updated)
    writeRows(skin, influences, vertices, [rows[vertex] for vertex in vertices])
    return len(vertices)


@undoChunk("skinWeightKitAverage")
def average(target):
    """選んだ頂点のウェイトを、すべて選んだ頂点の平均にそろえる。

    Args:
        target (Target): 対象。

    Returns:
        int: 変えた頂点の数。
    """
    skin, influences, locked, vertices = _context(target)
    rows = readRows(skin, influences, vertices)
    mean = [sum(column) / len(rows) for column in zip(*rows)]
    writeRows(skin, influences, vertices, [fitRow(mean, row, locked) for row in rows])
    return len(vertices)


@undoChunk("skinWeightKitMoveWeights")
def moveWeights(target, source, destination):
    """インフルエンスのウェイトを、別のインフルエンスへ移す(移した元は0になる。合計は変わらない)。

    頂点を選んでいればその頂点、メッシュを選んでいれば全頂点を対象にする。

    Args:
        target (Target): 対象。
        source (mlib.Node | str): 移す元。
        destination (mlib.Node | str): 移す先。

    Returns:
        int: 対象にした頂点の数。

    Raises:
        ValueError: 元と先が同じ、またはどちらかがロックされている場合。
    """
    skin = target.requireSkin()
    influences = skin.getInfluences()
    source_node = influences_module.find(skin, source)
    destination_node = influences_module.find(skin, destination)
    if source_node == destination_node:
        raise ValueError("Choose two different influences")
    for node in (source_node, destination_node):
        if influences_module.isLocked(node):
            raise ValueError("{} is locked".format(node.getNodeName()))
    vertices = target.editVertices()
    columns = (influences.index(source_node), influences.index(destination_node))
    rows = readRows(skin, influences, vertices)
    for row in rows:
        row[columns[1]] += row[columns[0]]
        row[columns[0]] = 0.0
    writeRows(skin, influences, vertices, rows)
    return len(vertices)


def copy(target):
    """選んだ頂点のウェイト(複数なら平均)をコピーする。

    Args:
        target (Target): 対象。

    Returns:
        dict[str, float]: コピーした {インフルエンスの名前: 値}(0の値は除く)。
    """
    skin = target.requireSkin()
    vertices = target.requireVertices()
    influences = skin.getInfluences()
    rows = readRows(skin, influences, vertices)
    mean = [sum(column) / len(rows) for column in zip(*rows)]
    _clipboard["weights"] = {node.getNodeName(): value for node, value in zip(influences, mean) if value > TOLERANCE}
    return dict(_clipboard["weights"])


def hasCopy():
    """コピーしたウェイトがあるかを返す。

    Returns:
        bool: あればTrue。
    """
    return bool(_clipboard["weights"])


@undoChunk("skinWeightKitPaste")
def paste(target):
    """コピーしたウェイトを、選んだ頂点へ貼り付ける(インフルエンスは名前で対応させる)。

    Args:
        target (Target): 対象。

    Returns:
        int: 変えた頂点の数。

    Raises:
        ValueError: コピーが無い、または貼り付け先に無いインフルエンスがある場合。
    """
    if not hasCopy():
        raise ValueError("Copy weights first")
    skin, influences, locked, vertices = _context(target)
    names = [node.getNodeName() for node in influences]
    missing = sorted(set(_clipboard["weights"]) - set(names))
    if missing:
        raise ValueError("Not influences of {}: {}".format(skin.getNodeName(), ", ".join(missing)))
    copied = [_clipboard["weights"].get(name, 0.0) for name in names]
    rows = readRows(skin, influences, vertices)
    writeRows(skin, influences, vertices, [fitRow(copied, row, locked) for row in rows])
    return len(vertices)
