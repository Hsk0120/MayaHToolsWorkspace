"""頂点の位置を含めたウェイトの書き出しと、番号または最も近い位置で対応させる読込み。

書き出す JSON は次の形(値が0のインフルエンスは書かない)::

    {"format": "skinWeightKit", "version": 1, "mesh": "body_GEO",
     "influences": ["root", "spine"], "positions": [[x, y, z], ...],
     "weights": [[[列, 値], ...], ...]}

位置はオブジェクト空間(cm)。mlib の ``SkinCluster.exportWeights`` の JSON(``mlib.skinWeights`` 形式)も読める。
読込みは、頂点を選んでいればその頂点だけに書く。インフルエンスは名前(名前空間を除いた短い名前)で対応させる。
"""

import io
import json
import math

import mlib
from mlib.decorator import undoChunk

from . import influences as influences_module
from . import weights as weights_module

#: 書き出す形式の名前と版。
FORMAT = "skinWeightKit"
VERSION = 1

#: 読込みの対応のさせ方。
METHODS = ("index", "position")


def _short(name):
    """名前空間とDAGパスを除いた名前。"""
    return name.split("|")[-1].split(":")[-1]


def exportWeights(target, path):
    """ウェイトと頂点の位置を JSON へ書き出す(メッシュ全体)。

    Args:
        target (Target): 対象。
        path (str): 書き出し先。

    Returns:
        int: 書き出した頂点の数。
    """
    skin = target.requireSkin()
    influences = skin.getInfluences()
    vertices = list(range(target.mesh.getNumVertices()))
    rows = weights_module.readRows(skin, influences, vertices)
    data = {
        "format": FORMAT,
        "version": VERSION,
        "mesh": target.mesh.getNodeName(),
        "influences": [node.getNodeName() for node in influences],
        "positions": [[round(point.x, 6), round(point.y, 6), round(point.z, 6)] for point in target.mesh.getPoints()],
        "weights": [[[column, round(value, 8)] for column, value in enumerate(row) if value > 0.0] for row in rows],
    }
    with io.open(path, "w", encoding="utf-8") as stream:
        json.dump(data, stream)
    return len(vertices)


def readFile(path):
    """書き出したファイルを読み、共通の形にする。

    Args:
        path (str): 読み込むファイル(この形式か、mlib の ``mlib.skinWeights`` 形式)。

    Returns:
        dict: ``influences``(list[str])・``rows``(list[dict[int, float]])・``positions``(list | None)。

    Raises:
        ValueError: 形式が分からない場合。
    """
    with io.open(path, "r", encoding="utf-8") as stream:
        data = json.load(stream)
    if data.get("format") == FORMAT:
        return {"influences": data["influences"], "positions": data.get("positions"),
                "rows": [{int(column): float(value) for column, value in row} for row in data["weights"]]}
    if isinstance(data.get("header"), dict) and data["header"].get("format") == "mlib.skinWeights":
        body = data["data"]
        rows = [{int(column): float(value) for column, value in zip(columns, values)}
                for columns, values in zip(body["weights"]["indices"], body["weights"]["values"])]
        return {"influences": [reference["name"] for reference in body["influences"]],
                "positions": body.get("positions"), "rows": rows}
    raise ValueError("Unknown weight file format: {}".format(path))


class _Grid(object):
    """ファイルに書いた点から、最も近い点を探すための一様な格子。

    メッシュの頂点の最近傍は mlib の ``Mesh.getClosestVertices`` を使う。ファイルの点はメッシュではないため、
    この格子で探す。
    """


    def __init__(self, points):
        self.points = points
        lows = [min(point[axis] for point in points) for axis in range(3)]
        highs = [max(point[axis] for point in points) for axis in range(3)]
        diagonal = math.sqrt(sum((high - low) ** 2 for low, high in zip(lows, highs))) or 1.0
        # 1つの格子に数点が入る大きさにする。
        self.size = max(diagonal / max(1.0, len(points) ** (1.0 / 3.0)), 1e-6)
        self.cells = {}
        for index, point in enumerate(points):
            self.cells.setdefault(self._cell(point), []).append(index)
        self.reach = int(math.ceil(diagonal / self.size)) + 1

    def _cell(self, point):
        """座標を格子の番号にする。"""
        return tuple(int(math.floor(value / self.size)) for value in point)

    def nearest(self, point):
        """最も近い点の番号を返す(近くの格子から広げて探す)。"""
        base = self._cell(point)
        best, best_distance = None, float("inf")
        for radius in range(self.reach + 1):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    for dz in range(-radius, radius + 1):
                        if max(abs(dx), abs(dy), abs(dz)) != radius:
                            continue
                        for index in self.cells.get((base[0] + dx, base[1] + dy, base[2] + dz), ()):
                            distance = sum((a - b) ** 2 for a, b in zip(self.points[index], point))
                            if distance < best_distance:
                                best, best_distance = index, distance
            # 見つかった点より近い点は、次の輪より外には無い。
            if best is not None and math.sqrt(best_distance) <= radius * self.size:
                break
        return best


@undoChunk("skinWeightKitCopyFromMesh")
def copyFromMesh(source, target):
    """別のバインド済みメッシュの、最も近い頂点(ワールド空間)のウェイトを、対象の頂点へ写す。

    頂点を選んでいればその頂点だけ(部分的なコピー)、メッシュなら全頂点へ写す。インフルエンスは名前で対応させる。

    Args:
        source (Target): 写す元(バインド済みのメッシュ)。
        target (Target): 写す先。

    Returns:
        int: 写した頂点の数。

    Raises:
        ValueError: 元と先が同じ、または元のインフルエンスが先に無い場合。
    """
    source_skin = source.requireSkin()
    skin = target.requireSkin()
    if source.mesh == target.mesh:
        raise ValueError("Pick a different mesh as the source")
    source_influences = source_skin.getInfluences()
    influences = skin.getInfluences()
    column_of = {_short(node.getNodeName()): index for index, node in enumerate(influences)}
    missing = [node.getNodeName() for node in source_influences if _short(node.getNodeName()) not in column_of]
    if missing:
        raise ValueError("Influences not in {}: {}".format(skin.getNodeName(), ", ".join(missing)))
    mapping = [column_of[_short(node.getNodeName())] for node in source_influences]
    source_rows = weights_module.readRows(source_skin, source_influences, list(range(source.mesh.getNumVertices())))
    vertices = target.editVertices()
    points = target.mesh.getPoints(worldSpace=True)
    closest = source.mesh.getClosestVertices([points[vertex] for vertex in vertices], worldSpace=True)
    locked = [influences_module.isLocked(node) for node in influences]
    current = weights_module.readRows(skin, influences, vertices)
    written = []
    for nearest, row in zip(closest, current):
        new = [0.0] * len(influences)
        for column, value in enumerate(source_rows[nearest]):
            new[mapping[column]] += value
        written.append(weights_module.fitRow(new, row, locked))
    weights_module.writeRows(skin, influences, vertices, written)
    return len(vertices)


@undoChunk("skinWeightKitImportWeights")
def importWeights(target, path, method="index", addMissing=False):
    """ファイルのウェイトを読み込む。

    Args:
        target (Target): 対象(頂点を選んでいればその頂点だけに書く)。
        path (str): 読み込むファイル。
        method (str): ``"index"`` は頂点の番号で対応させ(頂点数が同じこと)、``"position"`` は
            最も近い位置(オブジェクト空間)の頂点のウェイトを使う。
        addMissing (bool): Trueはファイルにあって skinCluster に無いインフルエンスを、シーンにあれば足す。

    Returns:
        int: 書いた頂点の数。

    Raises:
        ValueError: method が不正、頂点数が違う(番号)、位置が無い(位置)、またはインフルエンスが足りない場合。
    """
    if method not in METHODS:
        raise ValueError("method must be one of " + ", ".join(METHODS))
    skin = target.requireSkin()
    data = readFile(path)
    names = {_short(node.getNodeName()): node for node in skin.getInfluences()}
    missing = [name for name in data["influences"] if _short(name) not in names]
    if missing and addMissing:
        found = [mlib.getNode(name) for name in missing if mlib.objExists(name)]
        influences_module.addInfluences(target, found)
        names = {_short(node.getNodeName()): node for node in skin.getInfluences()}
        missing = [name for name in data["influences"] if _short(name) not in names]
    if missing:
        raise ValueError("Influences not in {}: {}".format(skin.getNodeName(), ", ".join(missing)))
    influences = skin.getInfluences()
    column_of = {_short(node.getNodeName()): index for index, node in enumerate(influences)}
    mapping = [column_of[_short(name)] for name in data["influences"]]
    vertices = target.editVertices()
    if method == "index":
        if len(data["rows"]) != target.mesh.getNumVertices():
            raise ValueError("Vertex count differs ({} in the file, {} in the mesh); import by position instead"
                             .format(len(data["rows"]), target.mesh.getNumVertices()))
        sources = vertices
    else:
        if not data["positions"]:
            raise ValueError("The file has no vertex positions; export it again with Skin Weight Kit")
        grid = _Grid([tuple(point) for point in data["positions"]])
        points = target.mesh.getPoints()
        sources = [grid.nearest((points[vertex].x, points[vertex].y, points[vertex].z)) for vertex in vertices]
    locked = [influences_module.isLocked(node) for node in influences]
    current = weights_module.readRows(skin, influences, vertices)
    written = []
    for source, row in zip(sources, current):
        new = [0.0] * len(influences)
        for column, value in data["rows"][source].items():
            new[mapping[column]] += value
        written.append(weights_module.fitRow(new, row, locked))
    weights_module.writeRows(skin, influences, vertices, written)
    return len(vertices)
