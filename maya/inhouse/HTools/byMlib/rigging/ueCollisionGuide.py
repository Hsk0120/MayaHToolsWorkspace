"""Unreal Engine のコリジョン(カプセル・球・箱)の形をしたガイドメッシュを作るツール。

作ったメッシュは作成履歴(polyCylinder / polySphere / polyCube)を残し、トランスフォームに足した
アトリビュート(半径・長さ・分割数など)とつないでいる。チャンネルボックスで値を変えると、その場で形が変わる。

カプセルの寸法は UE と同じ決め方にしている:
    ``radius`` = 半径、``length`` = 円柱部分の長さ(両端の半球を含まない)。全体の長さは ``length + 2 * radius``。
    (polyCylinder の ``roundCap`` を使うと、``height`` が円柱部分の長さになり、両端に半径 ``radius`` の半球が付く)

作り方は3通り:
    1. 原点に作る。
    2. 選んだメッシュ・頂点を包むように作る(向きは主成分分析と体積の局所探索で決めた OBB の軸)。
    3. 2つのジョイント(トランスフォーム)の間にカプセルを作り、位置・向き・長さを追従させる。
       長さは ``2点の距離 + 2 * endPadding - 2 * radius`` (0 未満にはしない)で、全体の長さが2点の距離になる。

名前は UE の FBX 取り込みの決まり(``UCP_`` カプセル・``USP_`` 球・``UBX_`` 箱 + 対象メッシュ名 + ``_01``)に合わせる。
UE はこの名前のメッシュの形からコリジョンを作るので、書き出す前に作成履歴やコンストレイントを消す必要はない。

シーンの操作は mlib で行う(元の版は maya.cmds と OpenMaya(API 2.0)だけで実装している)。

使い方:
    HTools > rigging > ueCollisionGuide でウィンドウを開く。スクリプトからは ``createCapsule()``・
    ``createSphere()``・``createBox()``・``fitToSelection()``・``createCapsuleBetween()`` を呼ぶ。
"""

import math

import maya.cmds as cmds

import mlib
from mlib import Vector
from mlib.common import Plugin, Selection, units
from mlib.decorator import undoChunk

from HTools import toolHelp


_WINDOW = "HToolsUeCollisionGuide"
#: 作ったガイドをまとめるグループ。
GROUP = "UE_Collision_GRP"
#: UE の FBX 取り込みで使われる、コリジョンの名前の先頭。
PREFIXES = {"capsule": "UCP", "sphere": "USP", "box": "UBX"}
#: 形ごとのワイヤーフレームの色(RGB, 0〜1)。
COLORS = {"capsule": (0.2, 1.0, 0.45), "sphere": (0.3, 0.75, 1.0), "box": (1.0, 0.75, 0.2)}
#: 対象メッシュを決めないときの名前。
DEFAULT_TARGET = "collision"
_AXES = ("x", "y", "z")
_AXIS_VECTORS = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}
_LABEL_WIDTH = 120


# ---------------------------------------------------------------------------------------------------------------------
# 共通


def _warn(message):
    """警告を Script Editor とビューポートへ表示する。

    Args:
        message (str): 表示する英語のメッセージ。
    """
    cmds.warning(message)
    text = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    try:
        cmds.inViewMessage(amg='<font color="#ffcc00">{}</font>'.format(text), pos="midCenter", fade=True)
    except RuntimeError:
        pass


def _shortName(node):
    """名前空間とパスを除いた短い名前を返す。

    Args:
        node (str): ノード名。

    Returns:
        str: 短い名前。
    """
    return node.split("|")[-1].split(":")[-1]


def _uiFactor():
    """内部単位(cm)の長さを、シーンの長さの単位へ直す倍率を返す。

    mlib の座標は常に cm、Plug.set(uiUnits=True)・作成コマンドはシーンの単位で受け取るため、その間を直す。

    Returns:
        float: 1cm がシーンの単位でいくつか。
    """
    return units.convertDistance(1.0, "cm")


def uniqueName(shape, target=None):
    """UE の決まりに合わせた、まだ使われていない名前を返す。

    Args:
        shape (str): ``"capsule"``・``"sphere"``・``"box"``。
        target (str): 対象のメッシュ名。None なら ``collision``。

    Returns:
        str: ``UCP_<対象>_01`` のような名前(番号は空いている最小のもの)。
    """
    base = "{}_{}".format(PREFIXES[shape], _shortName(target) if target else DEFAULT_TARGET)
    index = 1
    while mlib.objExists("{}_{:02d}".format(base, index)):
        index += 1
    return "{}_{:02d}".format(base, index)


def _group():
    """ガイドをまとめるグループを返す(無ければ原点に作る)。

    Returns:
        str: グループ名。
    """
    if not mlib.objExists(GROUP):
        mlib.createGroup(name=GROUP)
    return GROUP


def _addAttr(node, name, attributeType, value, minValue=None, maxValue=None):
    """チャンネルボックスに出るアトリビュートを足して値を入れる。

    Args:
        node (mlib.Transform): 足す先のトランスフォーム。
        name (str): アトリビュート名。
        attributeType (str): ``doubleLinear``(長さ)・``long``(整数)など。
        value (float | int): 初期値(シーンの単位)。
        minValue (float | int): 最小値。None なら制限しない。
        maxValue (float | int): 最大値。None なら制限しない。
    """
    kwargs = {"attributeType": attributeType, "keyable": True}
    if minValue is not None:
        kwargs["minValue"] = minValue
    if maxValue is not None:
        kwargs["maxValue"] = maxValue
    node.addAttr(name, **kwargs).set(value, uiUnits=True)


def _styleGuide(transform, shape, wireframe=True):
    """ガイドとして見やすく、レンダリングに映らないようにする。

    Args:
        transform (mlib.Transform): ガイドのトランスフォーム。
        shape (str): ``"capsule"``・``"sphere"``・``"box"`` (色に使う)。
        wireframe (bool): True ならシェーディングせずワイヤーフレームだけで描く(中のメッシュが見える)。
    """
    meshShape = transform.getShape(intermediates=True)
    meshShape.setColor(COLORS[shape])
    meshShape.setShadingOverride(wireframe)
    for attribute in ("castsShadows", "receiveShadows", "primaryVisibility", "visibleInReflections",
                      "visibleInRefractions"):
        meshShape.getPlug(attribute).set(False)
    # 標準のマテリアルを割り当てておく(シェーディング表示に戻したときに灰色で見える)。
    mlib.getNode("initialShadingGroup").assign(meshShape)
    transform.addAttr("ueCollisionShape", dataType="string").set(shape)


def _setWorldMatrix(transform, matrix):
    """トランスフォームのワールド行列を設定する(親の行列を打ち消して、ローカルの値にして入れる)。

    Args:
        transform (mlib.Transform): 対象のトランスフォーム。
        matrix (mlib.Matrix): 目標のワールド行列(移動は cm)。
    """
    transform.setMatrix(matrix, ws=True, fast=True)


def _finish(transform, shape, wireframe):
    """作ったガイドの見た目を整え、グループに入れて選択する。

    Args:
        transform (mlib.Transform): ガイドのトランスフォーム。
        shape (str): 形の種類。
        wireframe (bool): ワイヤーフレーム表示にするか。

    Returns:
        mlib.Transform: グループに入れたトランスフォーム。
    """
    _styleGuide(transform, shape, wireframe)
    transform.setParent(_group())
    mlib.select(transform)
    return transform


# ---------------------------------------------------------------------------------------------------------------------
# 作成


def createCapsule(radius=5.0, length=10.0, axis="y", segments=16, capSegments=4, target=None, name=None,
                  wireframe=True):
    """原点にカプセルのガイドを作る。

    Args:
        radius (float): 半径(シーンの単位)。
        length (float): 円柱部分の長さ(両端の半球を含まない。UE の Length と同じ)。
        axis (str): カプセルの軸 ``"x"``・``"y"``・``"z"``。
        segments (int): 周りの分割数。
        capSegments (int): 半球の分割数。
        target (str): 名前に使う対象メッシュ。None なら ``collision``。
        name (str): 名前。None なら ``UCP_<対象>_01`` の形で自動で決める。
        wireframe (bool): ワイヤーフレーム表示にするか。

    Returns:
        str: 作ったトランスフォーム。
    """
    with undoChunk("ueCollisionCapsule"):
        transform = _buildCapsule(radius, length, axis, segments, capSegments, name or uniqueName("capsule", target))
        return _finish(transform, "capsule", wireframe).getName()


def _buildCapsule(radius, length, axis, segments, capSegments, name):
    """作成履歴をアトリビュートにつないだカプセルを作る(配置・見た目は整えない)。

    Args:
        radius (float): 半径。
        length (float): 円柱部分の長さ。
        axis (str): 軸。
        segments (int): 周りの分割数。
        capSegments (int): 半球の分割数。
        name (str): 名前。

    Returns:
        mlib.Transform: トランスフォーム。
    """
    # 大きさはシーンの単位の値をcmへ直して渡す。作成ノードの値は下でアトリビュートへつなぐので、
    # 長さ0は作成ノードの最小値(0.01)で作る(cmds.polyCylinder も高さ0をその値にする。mlib の作成関数は正の値だけを受ける)。
    shape = mlib.createPoly("cylinder", radius=units.convertDistance(radius, toUnit="cm"),
                                    height=units.convertDistance(length, toUnit="cm") if length > 0 else 0.01,
                                    axis=_AXIS_VECTORS[axis], subdivisions=(segments, 1, capSegments), roundCap=True,
                                    createUVs=0, constructionHistory=True, name=name)
    transform, node = shape.getTransform(), shape.getHistory(type="polyCylinder")[0]
    # 元の cmds.polyCylinder と同じく、作った形状を選んだ状態にする。
    mlib.select(transform)
    node.rename(name + "_polyCapsule")
    _addAttr(transform, "radius", "doubleLinear", radius, minValue=0.0)
    _addAttr(transform, "length", "doubleLinear", max(length, 0.0), minValue=0.0)
    _addAttr(transform, "segments", "long", segments, minValue=3, maxValue=128)
    _addAttr(transform, "capSegments", "long", capSegments, minValue=1, maxValue=64)
    for source, destination in (("radius", "radius"), ("length", "height"), ("segments", "subdivisionsAxis"),
                                ("capSegments", "subdivisionsCaps")):
        node.getPlug(destination).connect(transform.getPlug(source))
    return transform


def createSphere(radius=5.0, segments=16, rings=12, target=None, name=None, wireframe=True):
    """原点に球のガイドを作る。

    Args:
        radius (float): 半径(シーンの単位)。
        segments (int): 周りの分割数。
        rings (int): 縦の分割数。
        target (str): 名前に使う対象メッシュ。
        name (str): 名前。None なら ``USP_<対象>_01``。
        wireframe (bool): ワイヤーフレーム表示にするか。

    Returns:
        str: 作ったトランスフォーム。
    """
    with undoChunk("ueCollisionSphere"):
        transform = _buildSphere(radius, segments, rings, name or uniqueName("sphere", target))
        return _finish(transform, "sphere", wireframe).getName()


def _buildSphere(radius, segments, rings, name):
    """作成履歴をアトリビュートにつないだ球を作る。

    Args:
        radius (float): 半径。
        segments (int): 周りの分割数。
        rings (int): 縦の分割数。
        name (str): 名前。

    Returns:
        mlib.Transform: トランスフォーム。
    """
    shape = mlib.createPoly("sphere", radius=units.convertDistance(radius, toUnit="cm"), subdivisions=(segments, rings), createUVs=0,
                                  constructionHistory=True, name=name)
    transform, node = shape.getTransform(), shape.getHistory(type="polySphere")[0]
    # 元の cmds.polySphere と同じく、作った形状を選んだ状態にする。
    mlib.select(transform)
    node.rename(name + "_polySphere")
    _addAttr(transform, "radius", "doubleLinear", radius, minValue=0.0)
    _addAttr(transform, "segments", "long", segments, minValue=3, maxValue=128)
    _addAttr(transform, "rings", "long", rings, minValue=2, maxValue=128)
    for source, destination in (("radius", "radius"), ("segments", "subdivisionsAxis"), ("rings", "subdivisionsHeight")):
        node.getPlug(destination).connect(transform.getPlug(source))
    return transform


def createBox(sizeX=10.0, sizeY=10.0, sizeZ=10.0, target=None, name=None, wireframe=True):
    """原点に箱のガイドを作る。

    Args:
        sizeX (float): X の幅(シーンの単位)。
        sizeY (float): Y の高さ。
        sizeZ (float): Z の奥行き。
        target (str): 名前に使う対象メッシュ。
        name (str): 名前。None なら ``UBX_<対象>_01``。
        wireframe (bool): ワイヤーフレーム表示にするか。

    Returns:
        str: 作ったトランスフォーム。
    """
    with undoChunk("ueCollisionBox"):
        transform = _buildBox(sizeX, sizeY, sizeZ, name or uniqueName("box", target))
        return _finish(transform, "box", wireframe).getName()


def _buildBox(sizeX, sizeY, sizeZ, name):
    """作成履歴をアトリビュートにつないだ箱を作る。

    Args:
        sizeX (float): X の幅。
        sizeY (float): Y の高さ。
        sizeZ (float): Z の奥行き。
        name (str): 名前。

    Returns:
        mlib.Transform: トランスフォーム。
    """
    shape = mlib.createPoly("cube", width=units.convertDistance(sizeX, toUnit="cm"), height=units.convertDistance(sizeY, toUnit="cm"),
                                depth=units.convertDistance(sizeZ, toUnit="cm"), createUVs=0, constructionHistory=True, name=name)
    transform, node = shape.getTransform(), shape.getHistory(type="polyCube")[0]
    # 元の cmds.polyCube と同じく、作った形状を選んだ状態にする。
    mlib.select(transform)
    node.rename(name + "_polyBox")
    for attribute, value in (("sizeX", sizeX), ("sizeY", sizeY), ("sizeZ", sizeZ)):
        _addAttr(transform, attribute, "doubleLinear", value, minValue=0.0)
    for source, destination in (("sizeX", "width"), ("sizeY", "height"), ("sizeZ", "depth")):
        node.getPlug(destination).connect(transform.getPlug(source))
    return transform


# ---------------------------------------------------------------------------------------------------------------------
# 選択に合わせる


def selectedPoints():
    """選択しているメッシュ(または頂点・辺・面)の点を、ワールド座標(cm)で集める。

    トランスフォームを選んでいれば、その下のメッシュの全頂点を使う。辺・面を選んでいれば、その頂点を使う。

    Returns:
        tuple[list[mlib.Vector], str | None]: 点と、名前に使う最初のメッシュのトランスフォーム名。
    """
    # 選択はコンポーネント1つずつに分かれるので、同じメッシュ・同じ種類の続きを1つの選択としてまとめる。
    groups = []
    for item in Selection.capture().getItems():
        if isinstance(item, mlib.Component):
            key = (item.shape.getFullName(), type(item))
            if groups and groups[-1][0] == key:
                groups[-1][2].append(item)
            else:
                groups.append((key, item.shape, [item]))
        else:
            groups.append((None, item, None))
    points, target = [], None
    for _, node, components in groups:
        if components is None and node.getType() == "transform":
            node = node.getShape()
        if not isinstance(node, mlib.Mesh):
            continue
        if target is None:
            target = node.getParent().getName()
        meshPoints = node.getPoints(ws=True)
        if components is None:
            points.extend(Vector(point) for point in meshPoints)
        else:
            # 辺・面を選んでいても、それに属する頂点を使う。
            vertices = set()
            for component in components:
                if isinstance(component, mlib.Vertex):
                    vertices.add(component.index)
                elif isinstance(component, (mlib.Edge, mlib.Face)):
                    vertices.update(component.getVertices().indices)
            points.extend(Vector(meshPoints[index]) for index in sorted(vertices))
    return points, target


def _orientedBounds(points):
    """点を包む向き付きの箱(中心・軸・寸法)を求める。

    HTools の ``simpleCollisionFromSelection.compute_oriented_bounds`` を使う。

    Args:
        points (list[mlib.Vector]): 点(cm)。

    Returns:
        dict: ``center`` (Vector)・``axes`` (長い順の3本の Vector)・``size`` (3成分。cm)。
    """
    from HTools.rigging.simpleCollisionFromSelection import compute_oriented_bounds

    bounds = compute_oriented_bounds(points)
    # 長い順に並べ直す(1本目をカプセルの軸にする)。
    order = sorted(range(3), key=lambda index: bounds["size"][index], reverse=True)
    axes = [bounds["axes"][index] for index in order]
    # 右手系を保つ。
    if (axes[0] ^ axes[1]) * axes[2] < 0:
        axes[2] = -axes[2]
    return {"center": bounds["center"], "axes": axes, "size": [bounds["size"][index] for index in order]}


def _basisMatrix(center, axisX, axisY, axisZ):
    """3本の軸と中心からワールド行列を作る。

    Args:
        center (mlib.Vector): 中心(cm)。
        axisX (mlib.Vector): ローカル X になる向き。
        axisY (mlib.Vector): ローカル Y になる向き。
        axisZ (mlib.Vector): ローカル Z になる向き。

    Returns:
        mlib.Matrix: 行列。
    """
    return mlib.Matrix.fromAxes(axisX, axisY, axisZ, position=center)


def fitCapsule(points):
    """点をすべて包むカプセル(軸・中心・半径・円柱部分の長さ)を求める。

    軸は点を包む向き付きの箱の一番長い向き。半径は軸からの一番遠い点の距離。円柱部分の両端は、
    どの点も両端の半球に収まる範囲で、できるだけ短くする。

    Args:
        points (list[mlib.Vector]): 点(cm)。

    Returns:
        dict: ``center`` (Vector, cm)・``axis`` (Vector)・``side`` (軸に直交する Vector)・
        ``radius``・``length`` (cm)。

    Raises:
        ValueError: 点が3つ未満のとき。
    """
    bounds = _orientedBounds(points)
    axis, side = bounds["axes"][0], bounds["axes"][1]
    origin = bounds["center"]
    along, across = [], []
    for point in points:
        offset = Vector(point) - origin
        t = offset * axis
        along.append(t)
        across.append((offset - axis * t).length())
    radius = max(max(across), 1e-6)
    # 点 i が収まる条件: 円柱部分の端 a, b について a <= t_i + h_i かつ b >= t_i - h_i (h_i は半球内の余裕)。
    heads = [math.sqrt(max(radius * radius - d * d, 0.0)) for d in across]
    start = min(t + h for t, h in zip(along, heads))
    end = max(t - h for t, h in zip(along, heads))
    if start > end:
        # 円柱部分が要らない(球で収まる)ときは、軸上の中点を中心に、一番遠い点までを半径にする。
        middle = (start + end) * 0.5
        start = end = middle
        radius = max((Vector(point) - (origin + axis * middle)).length() for point in points)
    center = origin + axis * ((start + end) * 0.5)
    return {"center": center, "axis": axis, "side": side, "radius": radius, "length": end - start}


def fitToSelection(shape="capsule", segments=16, capSegments=4, wireframe=True, name=None):
    """選んでいるメッシュ・頂点を包むガイドを作る。

    Args:
        shape (str): ``"capsule"``・``"sphere"``・``"box"``。
        segments (int): 周りの分割数(球・カプセル)。
        capSegments (int): 半球の分割数(カプセル)。球では縦の分割数の半分に使う。
        wireframe (bool): ワイヤーフレーム表示にするか。
        name (str): 名前。None なら選んだ最初のメッシュの名前から決める。

    Returns:
        str | None: 作ったトランスフォーム。点が足りなければ None。
    """
    points, target = selectedPoints()
    if len(points) < 3:
        _warn("Select a mesh, or at least 3 vertices / edges / faces, to fit a collision to.")
        return None
    factor = _uiFactor()
    with undoChunk("ueCollisionFit"):
        name = name or uniqueName(shape, target)
        if shape == "capsule":
            fit = fitCapsule(points)
            transform = _buildCapsule(fit["radius"] * factor, fit["length"] * factor, "y", segments, capSegments, name)
            # カプセルのローカル Y を軸に、ローカル X を2番目に長い向きに合わせる。
            matrix = _basisMatrix(fit["center"], fit["side"], fit["axis"], fit["side"] ^ fit["axis"])
        elif shape == "sphere":
            bounds = _orientedBounds(points)
            center = bounds["center"]
            radius = max((Vector(point) - center).length() for point in points)
            transform = _buildSphere(radius * factor, segments, max(capSegments * 2, 4), name)
            matrix = _basisMatrix(center, *bounds["axes"])
        else:
            bounds = _orientedBounds(points)
            size = [value * factor for value in bounds["size"]]
            transform = _buildBox(size[0], size[1], size[2], name)
            matrix = _basisMatrix(bounds["center"], *bounds["axes"])
        transform = _finish(transform, shape, wireframe)
        _setWorldMatrix(transform, matrix)
        return transform.getName()


# ---------------------------------------------------------------------------------------------------------------------
# 2点の間


def createCapsuleBetween(start, end, radius=3.0, endPadding=0.0, segments=16, capSegments=4, name=None,
                         wireframe=True):
    """2つのトランスフォームの間にカプセルを作り、位置・向き・長さを追従させる。

    中心は2点の中点(pointConstraint)、軸(ローカル Y)は ``end`` へ向ける(aimConstraint。ねじれは ``start`` の
    回転に合わせる)。円柱部分の長さは ``2点の距離 + 2 * endPadding - 2 * radius`` (0 未満にはしない)で、
    distanceBetween などの標準ノードで計算する。``endPadding`` が 0 なら、全体の長さが2点の距離になる。

    Args:
        start (str): 根本のトランスフォーム(ジョイントなど)。
        end (str): 先端のトランスフォーム。
        radius (float): 半径(シーンの単位)。
        endPadding (float): 両端をそれぞれ延ばす量(負の値で縮める)。
        segments (int): 周りの分割数。
        capSegments (int): 半球の分割数。
        name (str): 名前。None なら ``UCP_<start>_01``。
        wireframe (bool): ワイヤーフレーム表示にするか。

    Returns:
        str: 作ったトランスフォーム。

    Raises:
        ValueError: 2点が同じ位置のとき。
    """
    startNode, endNode = mlib.getNode(start), mlib.getNode(end)
    startPosition = startNode.getTranslation(ws=True, at=1)
    endPosition = endNode.getTranslation(ws=True, at=1)
    if (endPosition - startPosition).length() < 1e-6:
        raise ValueError("The two transforms are at the same position.")
    with undoChunk("ueCollisionBetween"):
        name = name or uniqueName("capsule", start)
        transform = _buildCapsule(radius, 0.0, "y", segments, capSegments, name)
        transform = _finish(transform, "capsule", wireframe)
        _addAttr(transform, "endPadding", "doubleLinear", endPadding)

        # 長さ = max(距離 + 2 * endPadding - 2 * radius, 0) をエクスプレッションで計算する。
        # distanceBetween・addDoubleLinear などは、版によって長さ型か単位なしかが違い、つなぎ目に入る単位変換の
        # 結果がずれる(シーンの単位が cm 以外で長さが狂う)。エクスプレッションは長さのアトリビュートを常に
        # シーンの単位で読み書きするので、版にもシーンの単位にも左右されない。
        # 2点の位置は decomposeMatrix(標準の matrixNodes プラグイン)でワールド行列から取り出す。
        Plugin("matrixNodes").load(skipExisting=True)
        positions = []
        for source, label in ((startNode, "start"), (endNode, "end")):
            decompose = mlib.createNode("decomposeMatrix", name="{}_{}Position".format(name, label))
            decompose.getPlug("inputMatrix").connect(source.getPlug("worldMatrix[0]"))
            positions.append(decompose.getName())
        lines = ["float $d{0} = {2}.outputTranslate{0} - {1}.outputTranslate{0};".format(channel, *positions)
                 for channel in "XYZ"]
        lines.append("float $length = sqrt($dX * $dX + $dY * $dY + $dZ * $dZ) + 2 * {0}.endPadding - 2 * {0}.radius;"
                     .format(transform.getName()))
        lines.append("{}.length = max($length, 0);".format(transform.getName()))
        mlib.createExpression("\n".join(lines), name=name + "_lengthExpression", alwaysEvaluate=False,
                              unitConversion="all")

        transform.addConstraint([startNode, endNode], type="point", name=name + "_pointConstraint")
        transform.addConstraint(endNode, type="aim", aimVector=(0, 1, 0), upVector=(1, 0, 0),
                                worldUpType="objectrotation",
                                worldUpVector=_perpendicularUp(startNode, endPosition - startPosition),
                                worldUpObject=startNode, name=name + "_aimConstraint")
        for attribute in ("translate", "rotate"):
            for channel in "XYZ":
                transform.getPlug(attribute + channel).setFlags(keyable=False, channelBox=False)
        mlib.select(transform)
        return transform.getName()


def _perpendicularUp(start, direction):
    """``start`` のローカル軸のうち、2点を結ぶ向きと一番直交に近いものを返す(aim のねじれの基準にする)。

    Args:
        start (mlib.Transform): 根本のトランスフォーム。
        direction (mlib.Vector): 2点を結ぶ向き(ワールド)。

    Returns:
        tuple[float, float, float]: ``start`` のローカル空間の軸。
    """
    matrix = start.getMatrix(ws=True)
    direction = Vector(direction).normal()
    best = None
    for local in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        world = (Vector(*local) * matrix).normal()
        score = abs(world * direction)
        if best is None or score < best[0]:
            best = (score, local)
    return best[1]


# ---------------------------------------------------------------------------------------------------------------------
# 書き出し前


def bake(transforms=None):
    """ガイドを固定のメッシュにする(作成履歴・コンストレイント・追加のアトリビュートを消す)。

    UE は名前と形からコリジョンを作るので、普通は不要。作成履歴を残したくないときだけ使う。

    Args:
        transforms (list[str]): 対象。None なら選択しているガイド。

    Returns:
        list[str]: 固定したトランスフォーム。
    """
    if transforms:
        names = list(transforms)
        nodes = [mlib.getNode(name) for name in names]
    else:
        nodes = list(mlib.ls(selection=True, type="transform"))
        names = [node.getName() for node in nodes]
    guides = [(name, node) for name, node in zip(names, nodes) if node.hasAttr("ueCollisionShape")]
    if not guides:
        _warn("Select collision guides created by this tool to bake.")
        return []
    with undoChunk("ueCollisionBake"):
        for _, node in guides:
            constraints = node.getChildren(type="constraint")
            if constraints:
                mlib.delete(constraints)
            # 2点の間のカプセルの長さを計算しているエクスプレッションと、位置を取り出す decomposeMatrix も消す。
            expressions = node.getPlug("length").getConnections(source=True, destination=False, type="expression",
                                                                asNode=True) if node.hasAttr("length") else None
            for expression in {item.getName(): item for item in expressions or []}.values():
                inputs = expression.getConnections(source=True, destination=False, type="decomposeMatrix", asNode=True)
                mlib.delete([expression] + list({item.getName(): item for item in inputs}.values()))
            node.deleteHistory(keepDeformers=False)
            for attribute in ("radius", "length", "segments", "capSegments", "rings", "sizeX", "sizeY", "sizeZ",
                              "endPadding"):
                if node.hasAttr(attribute):
                    node.getPlug(attribute).delete()
            for attribute in ("translate", "rotate"):
                for channel in "XYZ":
                    node.getPlug(attribute + channel).setFlags(keyable=True)
        guides = [name for name, _ in guides]
        print("Baked {} collision guide(s): {}".format(len(guides), ", ".join(guides)))
        return guides


# ---------------------------------------------------------------------------------------------------------------------
# ウィンドウ


def _shapeFromUi():
    """ウィンドウで選んでいる形を返す。

    Returns:
        str: ``"capsule"``・``"sphere"``・``"box"``。
    """
    return ("capsule", "sphere", "box")[cmds.radioButtonGrp(_WINDOW + "Shape", query=True, select=True) - 1]


def _settings():
    """ウィンドウの値を読む。

    Returns:
        dict: 各値。
    """
    target = cmds.textFieldButtonGrp(_WINDOW + "Target", query=True, text=True).strip() or None
    size = cmds.floatFieldGrp(_WINDOW + "BoxSize", query=True, value=True)
    return {
        "shape": _shapeFromUi(),
        "radius": cmds.floatFieldGrp(_WINDOW + "Radius", query=True, value1=True),
        "length": cmds.floatFieldGrp(_WINDOW + "Length", query=True, value1=True),
        "box": size,
        "axis": _AXES[cmds.radioButtonGrp(_WINDOW + "Axis", query=True, select=True) - 1],
        "segments": cmds.intFieldGrp(_WINDOW + "Segments", query=True, value1=True),
        "capSegments": cmds.intFieldGrp(_WINDOW + "CapSegments", query=True, value1=True),
        "endPadding": cmds.floatFieldGrp(_WINDOW + "EndPadding", query=True, value1=True),
        "target": target,
        "wireframe": cmds.checkBoxGrp(_WINDOW + "Wireframe", query=True, value1=True),
    }


def _createAtOrigin(*_):
    """ウィンドウの値で原点にガイドを作る。"""
    values = _settings()
    if values["shape"] == "capsule":
        node = createCapsule(values["radius"], values["length"], values["axis"], values["segments"],
                             values["capSegments"], target=values["target"], wireframe=values["wireframe"])
    elif values["shape"] == "sphere":
        node = createSphere(values["radius"], values["segments"], max(values["capSegments"] * 2, 4),
                            target=values["target"], wireframe=values["wireframe"])
    else:
        node = createBox(*values["box"], target=values["target"], wireframe=values["wireframe"])
    print("Created {}. Change its radius / length / size attributes in the Channel Box.".format(node))


def _fit(*_):
    """ウィンドウの値で、選択を包むガイドを作る。"""
    values = _settings()
    node = fitToSelection(values["shape"], values["segments"], values["capSegments"], values["wireframe"],
                          name=uniqueName(values["shape"], values["target"]) if values["target"] else None)
    if node:
        print("Fitted {} to the selection.".format(node))


def _between(*_):
    """選んだ2つのトランスフォームの間に、追従するカプセルを作る。"""
    selection = [node.getName() for node in mlib.ls(selection=True, type="transform")]
    if len(selection) != 2:
        _warn("Select exactly two transforms (for example a joint, then its child joint).")
        return
    values = _settings()
    name = uniqueName("capsule", values["target"]) if values["target"] else None
    try:
        node = createCapsuleBetween(selection[0], selection[1], values["radius"], values["endPadding"],
                                    values["segments"], values["capSegments"], name=name,
                                    wireframe=values["wireframe"])
    except ValueError as error:
        _warn(str(error))
        return
    print("Created {} between {} and {}. It follows both; change radius / endPadding in the Channel Box."
          .format(node, selection[0], selection[1]))


def _pickTarget(*_):
    """選択しているオブジェクトの名前を、名前に使う対象として入れる。"""
    selection = mlib.ls(selection=True, objectsOnly=True, type="transform")
    cmds.textFieldButtonGrp(_WINDOW + "Target", edit=True, text=_shortName(selection[0].getName()) if selection else "")


def _updateEnabled(*_):
    """選んだ形に関係する欄だけを使えるようにする。"""
    shape = _shapeFromUi()
    cmds.floatFieldGrp(_WINDOW + "Radius", edit=True, enable=shape in ("capsule", "sphere"))
    cmds.floatFieldGrp(_WINDOW + "Length", edit=True, enable=shape == "capsule")
    cmds.radioButtonGrp(_WINDOW + "Axis", edit=True, enable=shape == "capsule")
    cmds.floatFieldGrp(_WINDOW + "BoxSize", edit=True, enable=shape == "box")
    cmds.intFieldGrp(_WINDOW + "Segments", edit=True, enable=shape != "box")
    cmds.intFieldGrp(_WINDOW + "CapSegments", edit=True, enable=shape != "box")
    cmds.floatFieldGrp(_WINDOW + "EndPadding", edit=True, enable=shape == "capsule")
    cmds.button(_WINDOW + "BetweenButton", edit=True, enable=shape == "capsule")


def show():
    """ウィンドウを開く。"""
    if cmds.window(_WINDOW, exists=True):
        cmds.deleteUI(_WINDOW, window=True)
    cmds.window(_WINDOW, title="UE Collision Guide", widthHeight=(440, 10), sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=5, columnAttach=("both", 8))
    cmds.separator(style="none", height=4)
    cmds.radioButtonGrp(_WINDOW + "Shape", label="Shape", labelArray3=("Capsule", "Sphere", "Box"),
                        numberOfRadioButtons=3, select=1, columnWidth4=(_LABEL_WIDTH, 80, 70, 60),
                        changeCommand=_updateEnabled)
    cmds.textFieldButtonGrp(_WINDOW + "Target", label="Target mesh", text="", buttonLabel="<<",
                            columnWidth3=(_LABEL_WIDTH, 230, 40), buttonCommand=_pickTarget,
                            annotation="Used for the name: UCP_<target>_01. Empty: the fitted mesh, or 'collision'.")
    cmds.separator(style="in", height=10)
    cmds.floatFieldGrp(_WINDOW + "Radius", label="Radius", value1=5.0, columnWidth2=(_LABEL_WIDTH, 80))
    cmds.floatFieldGrp(_WINDOW + "Length", label="Length (cylinder)", value1=10.0, columnWidth2=(_LABEL_WIDTH, 80),
                       annotation="Length of the straight part, without the two hemispheres (same as UE).")
    cmds.radioButtonGrp(_WINDOW + "Axis", label="Axis", labelArray3=("X", "Y", "Z"), numberOfRadioButtons=3,
                        select=2, columnWidth4=(_LABEL_WIDTH, 50, 50, 50))
    cmds.floatFieldGrp(_WINDOW + "BoxSize", label="Box size", numberOfFields=3, value1=10.0, value2=10.0,
                       value3=10.0, columnWidth4=(_LABEL_WIDTH, 70, 70, 70))
    cmds.intFieldGrp(_WINDOW + "Segments", label="Segments", value1=16, columnWidth2=(_LABEL_WIDTH, 80))
    cmds.intFieldGrp(_WINDOW + "CapSegments", label="Cap segments", value1=4, columnWidth2=(_LABEL_WIDTH, 80))
    cmds.floatFieldGrp(_WINDOW + "EndPadding", label="End padding", value1=0.0, columnWidth2=(_LABEL_WIDTH, 80),
                       annotation="Between two transforms: extends each end by this amount.")
    cmds.checkBoxGrp(_WINDOW + "Wireframe", label="Display", label1="Wireframe only", value1=True,
                     columnWidth2=(_LABEL_WIDTH, 200))
    cmds.separator(style="in", height=10)
    cmds.button(label="Create at origin", height=28, command=_createAtOrigin)
    cmds.button(label="Fit to selection (mesh / components)", height=28, command=_fit)
    cmds.button(_WINDOW + "BetweenButton", label="Capsule between two selected (follows)", height=28,
                command=_between)
    cmds.button(label="Bake selected guides (remove history)", height=24, command=lambda *_: bake())
    # このツールの説明ページ(Sphinx)を開く。runpy で __main__ として動くので名前は文字列で渡す。
    cmds.button(label="Help", height=24, command=lambda *_: toolHelp.openHelp("rigging", "ueCollisionGuide"))
    cmds.text(label="Guides go under {}. Edit radius / length / size / segments in the Channel Box.".format(GROUP),
              align="left", wordWrap=True)
    cmds.separator(style="none", height=6)
    _updateEnabled()
    cmds.showWindow(_WINDOW)
    cmds.window(_WINDOW, edit=True, resizeToFitChildren=True)


if __name__ == "__main__":
    show()
