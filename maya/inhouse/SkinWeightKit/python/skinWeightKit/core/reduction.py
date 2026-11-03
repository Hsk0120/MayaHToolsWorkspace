"""ゲームエンジンへ書き出す前のウェイトのリダクション(0に近い値の削除・最大数への振り直し・精度の丸め)と診断。

1頂点ずつ次の順で行い、最後に合計がちょうど1になるようにする。

1. しきい値未満の値を0にする(全部が消える頂点は、最も大きい値だけ残す)。
2. 値の大きい順に最大数まで残し、残りを0にする。
3. 残した値を、合計1へ比率を保って振り直す。
4. 精度(小数の桁、または 1/255 のような段階)に丸める。丸めの誤差は最大剰余法で配り、合計を段階の整数倍で正確に1にする。

ロックしたインフルエンスは値を変えず、最大数の数にだけ含める。
"""

from mlib.decorator import undoChunk

from . import influences as influences_module
from . import symmetry
from . import target as target_module
from . import weights as weights_module

#: 精度の名前と、1を何段階に分けるか(None は丸めない)。
PRECISIONS = (
    ("off", None),
    ("2 decimals", 100),
    ("3 decimals", 1000),
    ("4 decimals", 10000),
    ("8-bit", 255),
    ("16-bit", 65535),
)


def quantizeRow(row, steps, locked):
    """ロックしていない値を 1/steps の整数倍に丸め、合計を1に保った行を返す(最大剰余法)。

    Args:
        row (list[float]): 合計1の行。
        steps (int): 1を分ける段階の数。
        locked (list[bool]): 列ごとのロック。

    Returns:
        list[float]: 丸めた行。
    """
    free = [index for index in range(len(row)) if not locked[index]]
    locked_sum = sum(value for index, value in enumerate(row) if locked[index])
    free_sum = sum(row[index] for index in free)
    if not free or free_sum <= weights_module.TOLERANCE:
        return list(row)
    total_units = int(round(max(0.0, 1.0 - locked_sum) * steps))
    exact = [row[index] / free_sum * total_units for index in free]
    units = [int(value) for value in exact]
    remainder = total_units - sum(units)
    # 切り捨てで足りない段階を、端数の大きい値から1つずつ配る(同じなら元の値が大きい方)。
    order = sorted(range(len(free)), key=lambda position: (exact[position] - units[position], exact[position]),
                   reverse=True)
    for position in order[:max(0, remainder)]:
        units[position] += 1
    result = list(row)
    for position, index in enumerate(free):
        result[index] = units[position] / float(steps)
    return result


def reduceRow(row, locked, threshold=0.0, maxInfluences=None, steps=None):
    """1頂点の行をリダクションする(削除 → 最大数 → 振り直し → 丸め)。

    Args:
        row (list[float]): 元の行。
        locked (list[bool]): 列ごとのロック。
        threshold (float): これ未満の値を0にする。
        maxInfluences (int | None): 1頂点の最大数。Noneは制限しない。
        steps (int | None): 丸めの段階の数。Noneは丸めない。

    Returns:
        list[float]: リダクションした行(合計1)。
    """
    free = [index for index in range(len(row)) if not locked[index]]
    if not free:
        return list(row)
    largest = max(free, key=lambda index: row[index])
    kept = {index for index in free if row[index] >= threshold and row[index] > 0.0}
    if not kept and row[largest] > 0.0:
        kept = {largest}
    if maxInfluences is not None:
        locked_used = sum(1 for index in range(len(row)) if locked[index] and row[index] > 0.0)
        allowed = max(1, maxInfluences - locked_used)
        kept = set(sorted(kept, key=lambda index: -row[index])[:allowed])
    new = [row[index] if locked[index] or index in kept else 0.0 for index in range(len(row))]
    new = weights_module.fitRow(new, row, locked)
    if steps:
        new = quantizeRow(new, steps, locked)
    return new


def _skinned_targets(targets):
    """バインドされた対象だけを返す。"""
    return [current for current in targets if current is not None and current.skin is not None]


@undoChunk("skinWeightKitReduce")
def reduce(targets, threshold=0.0, maxInfluences=None, steps=None, removeUnused=False, setSkinLimit=False):
    """複数の対象のウェイトをリダクションする(1回の Undo)。

    Args:
        targets (Iterable[Target]): 対象(頂点を選んだ対象はその頂点、メッシュの対象は全頂点)。
        threshold (float): これ未満の値を0にする。
        maxInfluences (int | None): 1頂点の最大数。Noneは制限しない。
        steps (int | None): 丸めの段階の数(:data:`PRECISIONS`)。Noneは丸めない。
        removeUnused (bool): Trueは終わった後に、どの頂点にも影響しないインフルエンスを外す。
        setSkinLimit (bool): Trueは skinCluster の maxInfluences を最大数にし、維持する設定を有効にする。

    Returns:
        dict[str, int]: ``"meshes"``・``"vertices"``・``"removedInfluences"`` の数。

    Raises:
        ValueError: バインドされた対象が無い、または引数が範囲外の場合。
    """
    if threshold < 0:
        raise ValueError("threshold must be 0 or more")
    if maxInfluences is not None and maxInfluences < 1:
        raise ValueError("maxInfluences must be 1 or more")
    if steps is not None and steps < 1:
        raise ValueError("steps must be 1 or more")
    targets = _skinned_targets(targets)
    if not targets:
        raise ValueError("Select skinned meshes or their vertices")
    summary = {"meshes": 0, "vertices": 0, "removedInfluences": 0}
    for current in targets:
        skin = current.skin
        influences = skin.getInfluences()
        locked = [influences_module.isLocked(node) for node in influences]
        vertices = current.editVertices()
        rows = weights_module.readRows(skin, influences, vertices)
        written = [reduceRow(row, locked, threshold, maxInfluences, steps) for row in rows]
        weights_module.writeRows(skin, influences, vertices, written)
        if setSkinLimit and maxInfluences is not None:
            skin.setMaxInfluences(maxInfluences, maintain=True, prune=False)
        if removeUnused:
            summary["removedInfluences"] += len(skin.removeUnusedInfluences())
        summary["meshes"] += 1
        summary["vertices"] += len(vertices)
    return summary


@undoChunk("skinWeightKitLimitBones")
def limitBones(current, maxBones):
    """skinCluster のインフルエンスの数を maxBones 以下にする(ゲームの1メッシュあたりのボーン数の上限向け)。

    ウェイトの合計(全頂点の和)が最も小さいジョイントから順に、ウェイトを最も近い親のインフルエンスへ移して外す。
    ロックしたもの・親にインフルエンスの無いジョイントは外さない。

    Args:
        current (Target): 対象。
        maxBones (int): 残すインフルエンスの数の上限(1以上)。

    Returns:
        list[tuple[str, str]]: 外した (ジョイント, 移した先の親) の順の組。

    Raises:
        ValueError: maxBones が1未満、または外せるジョイントが足りず上限まで減らせない場合(それまでに外した分は残る)。
    """
    if maxBones < 1:
        raise ValueError("maxBones must be 1 or more")
    skin = current.requireSkin()
    removed = []
    while len(skin.getInfluences()) > maxBones:
        influences = skin.getInfluences()
        flat = skin.getWeights(influences)
        width = len(influences)
        totals = [sum(flat[column::width]) for column in range(width)]
        candidates = []
        for column, node in enumerate(influences):
            if influences_module.isLocked(node) or not hasattr(node, "getTransferTarget"):
                continue
            parent = node.getTransferTarget(skin)
            if parent is not None:
                candidates.append((totals[column], column, parent))
        if not candidates:
            raise ValueError("Cannot reduce {} below {} influences (no unlocked joint has a parent influence)"
                             .format(skin.getNodeName(), len(influences)))
        _total, column, parent = min(candidates)
        node = influences[column]
        skin.removeInfluence(node, transferToParent=True)
        removed.append((node.getNodeName(), parent))
    return removed


def analyze(current, threshold=0.0, maxInfluences=None, steps=None, tolerance=1e-4):
    """ウェイトの状態を調べる(シーンは変えない)。

    Args:
        current (Target): 対象。
        threshold (float): これ未満で0でない値を「極小」として数える。
        maxInfluences (int | None): 1頂点の上限。Noneは skinCluster の maxInfluences。
        steps (int | None): 丸めの段階の数。指定すると、段階に乗っていない値の数も数える。
        tolerance (float): 合計のずれ・段階のずれの許容量。

    Returns:
        dict: 次のキーを持つ辞書。

        - ``vertices`` (int): 調べた頂点の数。
        - ``maxUsed`` (int): 1頂点で使っているインフルエンスの最大数。
        - ``histogram`` (dict[int, int]): {使っている数: 頂点の数}。
        - ``limit`` (int): 上限。
        - ``overLimit`` (list[int]): 上限を超えた頂点。
        - ``notNormalized`` (list[int]): 合計が1からずれた頂点。
        - ``tiny`` (list[int]): 極小の値を持つ頂点。
        - ``offGrid`` (list[int]): 段階に乗っていない値を持つ頂点(steps が無ければ空)。
        - ``unused`` (list[str]): どの頂点にも影響しないインフルエンスの名前(全体を調べたときだけ)。
        - ``missingOpposites`` (list[tuple[str, str]]): 左右の語を持つのに反対側が無いインフルエンス(ミラーの前の確認)。
        - ``leastUsed`` (list[tuple[str, float]]): ウェイトの合計が小さい順の5つ(全体を調べたときだけ。
          Limit Bones で先に外れる候補)。
    """
    skin = current.requireSkin()
    limit = skin.getMaxInfluences() if maxInfluences is None else maxInfluences
    influences = skin.getInfluences()
    vertices = current.editVertices()
    rows = weights_module.readRows(skin, influences, vertices)
    report = {"vertices": len(vertices), "maxUsed": 0, "histogram": {}, "limit": limit, "overLimit": [],
              "notNormalized": [], "tiny": [], "offGrid": [], "unused": []}
    used_columns = set()
    for vertex, row in zip(vertices, rows):
        used = [index for index, value in enumerate(row) if value > 0.0]
        used_columns.update(used)
        count = len(used)
        report["histogram"][count] = report["histogram"].get(count, 0) + 1
        report["maxUsed"] = max(report["maxUsed"], count)
        if limit and count > limit:
            report["overLimit"].append(vertex)
        if abs(sum(row) - 1.0) > tolerance:
            report["notNormalized"].append(vertex)
        if threshold and any(0.0 < value < threshold for value in row):
            report["tiny"].append(vertex)
        if steps and any(abs(value * steps - round(value * steps)) > tolerance * steps for value in row):
            report["offGrid"].append(vertex)
    report["missingOpposites"] = symmetry.missingOpposites(node.getNodeName() for node in influences)
    report["leastUsed"] = []
    if not current.hasComponents():
        report["unused"] = [node.getNodeName() for index, node in enumerate(influences) if index not in used_columns]
        totals = [sum(row[column] for row in rows) for column in range(len(influences))]
        order = sorted((column for column in used_columns), key=lambda column: totals[column])
        report["leastUsed"] = [(influences[column].getNodeName(), totals[column]) for column in order[:5]]
    return report


def problemVertices(report):
    """診断の結果から、直すべき頂点(上限超え・合計のずれ・極小・段階のずれ)を返す。

    Args:
        report (dict): :func:`analyze` の結果。

    Returns:
        list[int]: 頂点の番号(昇順)。
    """
    found = set()
    for key in ("overLimit", "notNormalized", "tiny", "offGrid"):
        found.update(report[key])
    return sorted(found)


def selectProblems(current, threshold=0.0, maxInfluences=None, steps=None):
    """直すべき頂点を選ぶ。

    Args:
        current (Target): 対象。
        threshold (float): 極小とみなす値の上限。
        maxInfluences (int | None): 1頂点の上限。Noneは skinCluster の maxInfluences。
        steps (int | None): 丸めの段階の数。

    Returns:
        int: 選んだ頂点の数。
    """
    report = analyze(current, threshold, maxInfluences, steps)
    return target_module.selectVertices(current.mesh, problemVertices(report))


def formatReport(report, name=""):
    """診断の結果を、パネルに出す英語の文にする。

    Args:
        report (dict): :func:`analyze` の結果。
        name (str): 先頭に出すメッシュの名前。

    Returns:
        str: 複数行の文。
    """
    histogram = ", ".join("{}:{}".format(count, report["histogram"][count]) for count in sorted(report["histogram"]))
    lines = [
        "{}{} vertices, max influences used {} (limit {})".format(name + ": " if name else "", report["vertices"],
                                                                report["maxUsed"], report["limit"]),
        "Influences per vertex: " + (histogram or "-"),
        "Over limit {}, not normalized {}, tiny {}".format(len(report["overLimit"]), len(report["notNormalized"]),
                                                          len(report["tiny"])),
    ]
    if report["offGrid"]:
        lines.append("Off the precision grid {}".format(len(report["offGrid"])))
    if report.get("missingOpposites"):
        lines.append("No opposite side: " + ", ".join("{} (no {})".format(name, other)
                                                     for name, other in report["missingOpposites"][:6]))
    if report.get("leastUsed"):
        lines.append("Least used: " + ", ".join("{} ({:.2f})".format(name, total)
                                               for name, total in report["leastUsed"]))
    if report["unused"]:
        lines.append("Unused influences {}: {}".format(len(report["unused"]), ", ".join(report["unused"][:6]) +
                                                       (" ..." if len(report["unused"]) > 6 else "")))
    return "\n".join(lines)
