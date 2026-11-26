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

import maya.cmds as cmds

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
        "mesh": target.mesh.getName(short=True),
        "influences": [node.getName(short=True) for node in influences],
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


class DeformationSample:
    """同一の複合ポーズで全頂点の位置を比較し、記録した編集範囲外の変形を検出する。"""

    def __init__(self, target):
        self.mesh = target.mesh
        self.skin = target.requireSkin()
        self.region = frozenset(target.editVertices())
        self.topology = self.mesh.getTopology()
        self.pose = self._pose()
        self.before = self.mesh.getPoints(worldSpace=True)

    def _pose(self):
        """フレーム、単位、入力骨とメッシュのワールド姿勢を記録する。"""
        return (cmds.currentTime(query=True), cmds.currentUnit(query=True, time=True), cmds.currentUnit(query=True, linear=True),
                tuple(self.mesh.getTransform().getMatrix(ws=True)),
                [(joint.getUuid(), tuple(joint.getMatrix(ws=True))) for joint in self.skin.getInfluences()])

    def compare(self, mesh):
        """記録時と同じ形状・ポーズで、1e-6cmを超えた頂点番号、位置差、範囲外判定を返す。"""
        if not self.mesh.isValid() or mesh != self.mesh or not self.skin.isValid() or self.skin not in mesh.getSkinClusters():
            raise ValueError("Select the recorded skinned mesh")
        if self.topology != mesh.getTopology() or self.pose != self._pose():
            raise ValueError("Restore the recorded topology, frame, units and pose before comparing")
        result = []
        for index, (before, after) in enumerate(zip(self.before, mesh.getPoints(worldSpace=True))):
            distance = (after - before).length()
            if distance > 1e-6:
                result.append((index, distance, index not in self.region))
        return result


class BoundarySample:
    """指定した2つのスキンメッシュの境界ペアを同じ姿勢で比較する。"""

    def __init__(self, source, destination, pairs):
        self.meshes = (source, destination)
        self.pairs = tuple(pairs)
        if source == destination or not self.pairs:
            raise ValueError("Specify vertex pairs on two different meshes")
        self.pose, self.before = self._sample()

    def _sample(self):
        """フレーム・単位・メッシュとインフルエンスの姿勢、および各ペアの距離を読む。"""
        pose = [cmds.currentTime(query=True), cmds.currentUnit(query=True, time=True), cmds.currentUnit(query=True, linear=True)]
        points = []
        for mesh in self.meshes:
            if not mesh.isValid() or not mesh.getSkinClusters():
                raise ValueError("The recorded skinned mesh is unavailable")
            skin = mesh.getSkinClusters()[0]
            pose.extend((skin.getUuid(), mesh.getNumVertices(), tuple(mesh.getTransform().getMatrix(ws=True))))
            pose.extend((node.getUuid(), tuple(node.getMatrix(ws=True))) for node in skin.getInfluences())
            points.append(mesh.getPoints(worldSpace=True))
        distances = []
        for first, second in self.pairs:
            if not (0 <= first < len(points[0]) and 0 <= second < len(points[1])):
                raise ValueError("Vertex pair is outside the mesh")
            distances.append((points[0][first] - points[1][second]).length())
        return pose, distances

    def compare(self):
        """姿勢が一致すればペアごとの頂点番号と前後のワールド距離(cm)を返す。"""
        pose, after = self._sample()
        if pose != self.pose:
            raise ValueError("Restore the recorded frame, units and skeleton pose before comparing")
        return [(a, b, old, new) for (a, b), old, new in zip(self.pairs, self.before, after)]


def compareBindMeshes(first, second):
    """現在姿勢で頂点番号が対応するか調べ、ローカル・ワールド別の最大頂点差(cm)を返す。"""
    if first == second:
        raise ValueError("Select two distinct mesh objects")
    if first.getNumVertices() != second.getNumVertices() or first.getTopology() != second.getTopology():
        raise ValueError("Topology differs: vertex counts, face counts or ordered face vertices do not match")
    result = {}
    for space, world in (("local", False), ("world", True)):
        pairs = zip(first.getPoints(worldSpace=world), second.getPoints(worldSpace=world))
        result[space] = max(((index, (b - a).length()) for index, (a, b) in enumerate(pairs)),
                            key=lambda entry: entry[1], default=(None, 0.0))
    return result


def compareCageOutput(reference, wrapped, tolerance=1e-6):
    """直接転送した参照形状とケージ出力の差(cm)を頂点ごとに測り、開いた境界を示す。"""
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Tolerance must be finite and non-negative")
    topology = reference.getTopology()
    if reference == wrapped or reference.getNumVertices() != wrapped.getNumVertices() or topology != wrapped.getTopology():
        raise ValueError("Select distinct reference and cage outputs with matching vertex and face order")
    counts, indices = topology
    edge_counts = {}
    start = 0
    for count in counts:
        face = indices[start:start + count]
        for a, b in zip(face, face[1:] + face[:1]):
            edge = (min(a, b), max(a, b))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
        start += count
    boundary = {v for edge, count in edge_counts.items() if count == 1 for v in edge}
    rows = []
    for index, (a, b) in enumerate(zip(reference.getPoints(worldSpace=True), wrapped.getPoints(worldSpace=True))):
        distance = (a - b).length()
        if distance > tolerance:
            rows.append((index, distance, index in boundary))
    return rows


def previewCorrespondence(source, target, method, maxDistance):
    """指定範囲の頂点ごとに対応元番号とワールド空間の距離(cm)を返す。

    距離上限を超えた場合は対応元番号をNoneにする。番号対応では両メッシュの頂点数が一致する必要がある。
    """
    source.requireSkin()
    target.requireSkin()
    if source.mesh == target.mesh:
        raise ValueError("Pick a different mesh as the source")
    if method not in METHODS:
        raise ValueError("Unknown correspondence method")
    if not math.isfinite(maxDistance) or maxDistance < 0:
        raise ValueError("Maximum distance must be finite and non-negative")
    vertices = target.editVertices()
    source_points = source.mesh.getPoints(worldSpace=True)
    target_points = target.mesh.getPoints(worldSpace=True)
    if method == "index":
        if len(source_points) != len(target_points):
            raise ValueError("Vertex counts differ")
        indices = vertices
    else:
        indices = source.mesh.getClosestVertices([target_points[v] for v in vertices], worldSpace=True)
    result = []
    for vertex, index in zip(vertices, indices):
        distance = (target_points[vertex] - source_points[index]).length()
        result.append((vertex, index if distance <= maxDistance else None, distance))
    return result


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
    column_of = {_short(node.getName(short=True)): index for index, node in enumerate(influences)}
    missing = [node.getName(short=True) for node in source_influences if _short(node.getName(short=True)) not in column_of]
    if missing:
        raise ValueError("Influences not in {}: {}".format(skin.getName(short=True), ", ".join(missing)))
    mapping = [column_of[_short(node.getName(short=True))] for node in source_influences]
    source_rows = weights_module.readRows(source_skin, source_influences, list(range(source.mesh.getNumVertices())))
    vertices = target.editVertices()
    points = target.mesh.getPoints(worldSpace=True)
    closest = source.mesh.getClosestVertices([points[vertex] for vertex in vertices], worldSpace=True)
    locked = influences_module.lockedFlags(skin, influences)
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
    names = {_short(node.getName(short=True)): node for node in skin.getInfluences()}
    missing = [name for name in data["influences"] if _short(name) not in names]
    if missing and addMissing:
        found = [mlib.getNode(name) for name in missing if mlib.objExists(name)]
        influences_module.addInfluences(target, found)
        names = {_short(node.getName(short=True)): node for node in skin.getInfluences()}
        missing = [name for name in data["influences"] if _short(name) not in names]
    if missing:
        raise ValueError("Influences not in {}: {}".format(skin.getName(short=True), ", ".join(missing)))
    influences = skin.getInfluences()
    column_of = {_short(node.getName(short=True)): index for index, node in enumerate(influences)}
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
    locked = influences_module.lockedFlags(skin, influences)
    current = weights_module.readRows(skin, influences, vertices)
    written = []
    for source, row in zip(sources, current):
        new = [0.0] * len(influences)
        for column, value in data["rows"][source].items():
            new[mapping[column]] += value
        written.append(weights_module.fitRow(new, row, locked))
    weights_module.writeRows(skin, influences, vertices, written)
    return len(vertices)
