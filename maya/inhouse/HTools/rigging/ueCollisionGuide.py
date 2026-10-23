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

mlib に依存せず、maya.cmds と OpenMaya(API 2.0)だけで実装している。

使い方:
    HTools > rigging > ueCollisionGuide でウィンドウを開く。スクリプトからは ``createCapsule()``・
    ``createSphere()``・``createBox()``・``fitToSelection()``・``createCapsuleBetween()`` を呼ぶ。
"""

import math

import maya.api.OpenMaya as om2
import maya.cmds as cmds


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

    OpenMaya の座標は常に cm、cmds の setAttr はシーンの単位で受け取るため、その間を直す。

    Returns:
        float: 1cm がシーンの単位でいくつか。
    """
    return om2.MDistance(1.0, om2.MDistance.kCentimeters).asUnits(om2.MDistance.uiUnit())


def _dagPath(name):
    """名前から MDagPath を得る。

    Args:
        name (str): DAG ノード名。

    Returns:
        om2.MDagPath: パス。
    """
    selection = om2.MSelectionList()
    selection.add(name)
    return selection.getDagPath(0)


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
    while cmds.objExists("{}_{:02d}".format(base, index)):
        index += 1
    return "{}_{:02d}".format(base, index)


def _group():
    """ガイドをまとめるグループを返す(無ければ原点に作る)。

    Returns:
        str: グループ名。
    """
    if not cmds.objExists(GROUP):
        cmds.group(empty=True, name=GROUP)
    return GROUP


def _addAttr(node, name, attributeType, value, minValue=None, maxValue=None):
    """チャンネルボックスに出るアトリビュートを足して値を入れる。

    Args:
        node (str): 足す先のトランスフォーム。
        name (str): アトリビュート名。
        attributeType (str): ``doubleLinear``(長さ)・``long``(整数)など。
        value (float | int): 初期値。
        minValue (float | int): 最小値。None なら制限しない。
        maxValue (float | int): 最大値。None なら制限しない。
    """
    kwargs = {"longName": name, "attributeType": attributeType, "keyable": True}
    if minValue is not None:
        kwargs["minValue"] = minValue
    if maxValue is not None:
        kwargs["maxValue"] = maxValue
    cmds.addAttr(node, **kwargs)
    cmds.setAttr("{}.{}".format(node, name), value)


def _styleGuide(transform, shape, wireframe=True):
    """ガイドとして見やすく、レンダリングに映らないようにする。

    Args:
        transform (str): ガイドのトランスフォーム。
        shape (str): ``"capsule"``・``"sphere"``・``"box"`` (色に使う)。
        wireframe (bool): True ならシェーディングせずワイヤーフレームだけで描く(中のメッシュが見える)。
    """
    meshShape = cmds.listRelatives(transform, shapes=True, fullPath=True)[0]
    cmds.setAttr(meshShape + ".overrideEnabled", True)
    cmds.setAttr(meshShape + ".overrideRGBColors", True)
    cmds.setAttr(meshShape + ".overrideColorRGB", *COLORS[shape])
    cmds.setAttr(meshShape + ".overrideShading", not wireframe)
    for attribute in ("castsShadows", "receiveShadows", "primaryVisibility", "visibleInReflections",
                      "visibleInRefractions"):
        cmds.setAttr("{}.{}".format(meshShape, attribute), False)
    # 標準のマテリアルを割り当てておく(シェーディング表示に戻したときに灰色で見える)。
    cmds.sets(meshShape, edit=True, forceElement="initialShadingGroup")
    cmds.addAttr(transform, longName="ueCollisionShape", dataType="string")
    cmds.setAttr(transform + ".ueCollisionShape", shape, type="string")


def _setWorldMatrix(transform, matrix):
    """トランスフォームのワールド行列を設定する(親の行列を打ち消して、ローカルの値にして入れる)。

    Args:
        transform (str): 対象のトランスフォーム。
        matrix (om2.MMatrix): 目標のワールド行列(移動は cm)。
    """
    path = _dagPath(transform)
    local = matrix * path.exclusiveMatrixInverse()
    om2.MFnTransform(path).setTransformation(om2.MTransformationMatrix(local))


def _finish(transform, shape, wireframe):
    """作ったガイドの見た目を整え、グループに入れて選択する。

    Args:
        transform (str): ガイドのトランスフォーム。
        shape (str): 形の種類。
        wireframe (bool): ワイヤーフレーム表示にするか。

    Returns:
        str: グループに入れたあとのトランスフォーム名。
    """
    _styleGuide(transform, shape, wireframe)
    transform = cmds.parent(transform, _group())[0]
    cmds.select(transform)
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
    cmds.undoInfo(openChunk=True, chunkName="ueCollisionCapsule")
    try:
        transform = _buildCapsule(radius, length, axis, segments, capSegments, name or uniqueName("capsule", target))
        return _finish(transform, "capsule", wireframe)
    finally:
        cmds.undoInfo(closeChunk=True)


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
        str: トランスフォーム名。
    """
    transform, node = cmds.polyCylinder(name=name, radius=radius, height=max(length, 0.0), axis=_AXIS_VECTORS[axis],
                                        subdivisionsAxis=segments, subdivisionsHeight=1, subdivisionsCaps=capSegments,
                                        roundCap=True, createUVs=0, constructionHistory=True)
    node = cmds.rename(node, name + "_polyCapsule")
    _addAttr(transform, "radius", "doubleLinear", radius, minValue=0.0)
    _addAttr(transform, "length", "doubleLinear", max(length, 0.0), minValue=0.0)
    _addAttr(transform, "segments", "long", segments, minValue=3, maxValue=128)
    _addAttr(transform, "capSegments", "long", capSegments, minValue=1, maxValue=64)
    for source, destination in (("radius", "radius"), ("length", "height"), ("segments", "subdivisionsAxis"),
                                ("capSegments", "subdivisionsCaps")):
        cmds.connectAttr("{}.{}".format(transform, source), "{}.{}".format(node, destination))
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
    cmds.undoInfo(openChunk=True, chunkName="ueCollisionSphere")
    try:
        transform = _buildSphere(radius, segments, rings, name or uniqueName("sphere", target))
        return _finish(transform, "sphere", wireframe)
    finally:
        cmds.undoInfo(closeChunk=True)


def _buildSphere(radius, segments, rings, name):
    """作成履歴をアトリビュートにつないだ球を作る。

    Args:
        radius (float): 半径。
        segments (int): 周りの分割数。
        rings (int): 縦の分割数。
        name (str): 名前。

    Returns:
        str: トランスフォーム名。
    """
    transform, node = cmds.polySphere(name=name, radius=radius, subdivisionsAxis=segments, subdivisionsHeight=rings,
                                      createUVs=0, constructionHistory=True)
    node = cmds.rename(node, name + "_polySphere")
    _addAttr(transform, "radius", "doubleLinear", radius, minValue=0.0)
    _addAttr(transform, "segments", "long", segments, minValue=3, maxValue=128)
    _addAttr(transform, "rings", "long", rings, minValue=2, maxValue=128)
    for source, destination in (("radius", "radius"), ("segments", "subdivisionsAxis"), ("rings", "subdivisionsHeight")):
        cmds.connectAttr("{}.{}".format(transform, source), "{}.{}".format(node, destination))
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
    cmds.undoInfo(openChunk=True, chunkName="ueCollisionBox")
    try:
        transform = _buildBox(sizeX, sizeY, sizeZ, name or uniqueName("box", target))
        return _finish(transform, "box", wireframe)
    finally:
        cmds.undoInfo(closeChunk=True)


def _buildBox(sizeX, sizeY, sizeZ, name):
    """作成履歴をアトリビュートにつないだ箱を作る。

    Args:
        sizeX (float): X の幅。
        sizeY (float): Y の高さ。
        sizeZ (float): Z の奥行き。
        name (str): 名前。

    Returns:
        str: トランスフォーム名。
    """
    transform, node = cmds.polyCube(name=name, width=sizeX, height=sizeY, depth=sizeZ, createUVs=0,
                                    constructionHistory=True)
    node = cmds.rename(node, name + "_polyBox")
    for attribute, value in (("sizeX", sizeX), ("sizeY", sizeY), ("sizeZ", sizeZ)):
        _addAttr(transform, attribute, "doubleLinear", value, minValue=0.0)
    for source, destination in (("sizeX", "width"), ("sizeY", "height"), ("sizeZ", "depth")):
        cmds.connectAttr("{}.{}".format(transform, source), "{}.{}".format(node, destination))
    return transform


# ---------------------------------------------------------------------------------------------------------------------
# 選択に合わせる


def selectedPoints():
    """選択しているメッシュ(または頂点・辺・面)の点を、ワールド座標(cm)で集める。

    トランスフォームを選んでいれば、その下のメッシュの全頂点を使う。辺・面を選んでいれば、その頂点を使う。

    Returns:
        tuple[list[om2.MPoint], str | None]: 点と、名前に使う最初のメッシュのトランスフォーム名。
    """
    points, target = [], None
    iterator = om2.MItSelectionList(om2.MGlobal.getActiveSelectionList())
    while not iterator.isDone():
        try:
            path, component = iterator.getComponent()
        except RuntimeError:
            iterator.next()
            continue
        if path.apiType() == om2.MFn.kTransform:
            try:
                path.extendToShape()
            except RuntimeError:
                iterator.next()
                continue
        if path.apiType() != om2.MFn.kMesh:
            iterator.next()
            continue
        if target is None:
            parent = om2.MDagPath(path)
            parent.pop()
            target = parent.partialPathName()
        meshPoints = om2.MFnMesh(path).getPoints(om2.MSpace.kWorld)
        if component.isNull():
            points.extend(om2.MPoint(point) for point in meshPoints)
        else:
            # 辺・面を選んでいても、それに属する頂点を使う。
            vertices = set()
            componentIterator = om2.MItMeshVertex(path, component) if component.hasFn(om2.MFn.kMeshVertComponent) \
                else None
            if componentIterator is not None:
                while not componentIterator.isDone():
                    vertices.add(componentIterator.index())
                    componentIterator.next()
            elif component.hasFn(om2.MFn.kMeshEdgeComponent):
                edges = om2.MItMeshEdge(path, component)
                while not edges.isDone():
                    vertices.update((edges.vertexId(0), edges.vertexId(1)))
                    edges.next()
            elif component.hasFn(om2.MFn.kMeshPolygonComponent):
                faces = om2.MItMeshPolygon(path, component)
                while not faces.isDone():
                    vertices.update(faces.getVertices())
                    faces.next()
            points.extend(om2.MPoint(meshPoints[index]) for index in sorted(vertices))
        iterator.next()
    return points, target


def _orientedBounds(points):
    """点を包む向き付きの箱(中心・軸・寸法)を求める。

    HTools の ``simpleCollisionFromSelection.compute_oriented_bounds`` (cmds・OpenMaya のみ)を使う。

    Args:
        points (list[om2.MPoint]): 点(cm)。

    Returns:
        dict: ``center`` (MVector)・``axes`` (長い順の3本の MVector)・``size`` (3成分。cm)。
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
        center (om2.MVector): 中心(cm)。
        axisX (om2.MVector): ローカル X になる向き。
        axisY (om2.MVector): ローカル Y になる向き。
        axisZ (om2.MVector): ローカル Z になる向き。

    Returns:
        om2.MMatrix: 行列。
    """
    return om2.MMatrix([axisX.x, axisX.y, axisX.z, 0.0,
                        axisY.x, axisY.y, axisY.z, 0.0,
                        axisZ.x, axisZ.y, axisZ.z, 0.0,
                        center.x, center.y, center.z, 1.0])


def fitCapsule(points):
    """点をすべて包むカプセル(軸・中心・半径・円柱部分の長さ)を求める。

    軸は点を包む向き付きの箱の一番長い向き。半径は軸からの一番遠い点の距離。円柱部分の両端は、
    どの点も両端の半球に収まる範囲で、できるだけ短くする。

    Args:
        points (list[om2.MPoint]): 点(cm)。

    Returns:
        dict: ``center`` (MVector, cm)・``axis`` (MVector)・``side`` (軸に直交する MVector)・
        ``radius``・``length`` (cm)。

    Raises:
        ValueError: 点が3つ未満のとき。
    """
    bounds = _orientedBounds(points)
    axis, side = bounds["axes"][0], bounds["axes"][1]
    origin = bounds["center"]
    along, across = [], []
    for point in points:
        offset = om2.MVector(point) - origin
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
        radius = max((om2.MVector(point) - (origin + axis * middle)).length() for point in points)
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
    cmds.undoInfo(openChunk=True, chunkName="ueCollisionFit")
    try:
        name = name or uniqueName(shape, target)
        if shape == "capsule":
            fit = fitCapsule(points)
            transform = _buildCapsule(fit["radius"] * factor, fit["length"] * factor, "y", segments, capSegments, name)
            # カプセルのローカル Y を軸に、ローカル X を2番目に長い向きに合わせる。
            matrix = _basisMatrix(fit["center"], fit["side"], fit["axis"], fit["side"] ^ fit["axis"])
        elif shape == "sphere":
            bounds = _orientedBounds(points)
            center = bounds["center"]
            radius = max((om2.MVector(point) - center).length() for point in points)
            transform = _buildSphere(radius * factor, segments, max(capSegments * 2, 4), name)
            matrix = _basisMatrix(center, *bounds["axes"])
        else:
            bounds = _orientedBounds(points)
            size = [value * factor for value in bounds["size"]]
            transform = _buildBox(size[0], size[1], size[2], name)
            matrix = _basisMatrix(bounds["center"], *bounds["axes"])
        transform = _finish(transform, shape, wireframe)
        _setWorldMatrix(transform, matrix)
        return transform
    finally:
        cmds.undoInfo(closeChunk=True)


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
    startPosition = om2.MVector(cmds.xform(start, query=True, worldSpace=True, translation=True))
    endPosition = om2.MVector(cmds.xform(end, query=True, worldSpace=True, translation=True))
    if (endPosition - startPosition).length() < 1e-6:
        raise ValueError("The two transforms are at the same position.")
    cmds.undoInfo(openChunk=True, chunkName="ueCollisionBetween")
    try:
        name = name or uniqueName("capsule", start)
        transform = _buildCapsule(radius, 0.0, "y", segments, capSegments, name)
        transform = _finish(transform, "capsule", wireframe)
        _addAttr(transform, "endPadding", "doubleLinear", endPadding)

        # 長さ = max(距離 + 2 * endPadding - 2 * radius, 0) をエクスプレッションで計算する。
        # distanceBetween・addDoubleLinear などは、版によって長さ型か単位なしかが違い、つなぎ目に入る単位変換の
        # 結果がずれる(シーンの単位が cm 以外で長さが狂う)。エクスプレッションは長さのアトリビュートを常に
        # シーンの単位で読み書きするので、版にもシーンの単位にも左右されない。
        # 2点の位置は decomposeMatrix(標準の matrixNodes プラグイン)でワールド行列から取り出す。
        if not cmds.pluginInfo("matrixNodes", query=True, loaded=True):
            cmds.loadPlugin("matrixNodes", quiet=True)
        positions = []
        for source, label in ((start, "start"), (end, "end")):
            decompose = cmds.createNode("decomposeMatrix", name="{}_{}Position".format(name, label))
            cmds.connectAttr(source + ".worldMatrix[0]", decompose + ".inputMatrix")
            positions.append(decompose)
        lines = ["float $d{0} = {2}.outputTranslate{0} - {1}.outputTranslate{0};".format(channel, *positions)
                 for channel in "XYZ"]
        lines.append("float $length = sqrt($dX * $dX + $dY * $dY + $dZ * $dZ) + 2 * {0}.endPadding - 2 * {0}.radius;"
                     .format(transform))
        lines.append("{}.length = max($length, 0);".format(transform))
        cmds.expression(name=name + "_lengthExpression", string="\n".join(lines), alwaysEvaluate=False,
                        unitConversion="all")

        cmds.pointConstraint(start, end, transform, name=name + "_pointConstraint")
        cmds.aimConstraint(end, transform, aimVector=(0, 1, 0), upVector=(1, 0, 0), worldUpType="objectrotation",
                           worldUpVector=_perpendicularUp(start, endPosition - startPosition), worldUpObject=start,
                           name=name + "_aimConstraint")
        for attribute in ("translate", "rotate"):
            for channel in "XYZ":
                cmds.setAttr("{}.{}{}".format(transform, attribute, channel), keyable=False, channelBox=False)
        cmds.select(transform)
        return transform
    finally:
        cmds.undoInfo(closeChunk=True)


def _perpendicularUp(start, direction):
    """``start`` のローカル軸のうち、2点を結ぶ向きと一番直交に近いものを返す(aim のねじれの基準にする)。

    Args:
        start (str): 根本のトランスフォーム。
        direction (om2.MVector): 2点を結ぶ向き(ワールド)。

    Returns:
        tuple[float, float, float]: ``start`` のローカル空間の軸。
    """
    matrix = om2.MMatrix(cmds.xform(start, query=True, worldSpace=True, matrix=True))
    direction = om2.MVector(direction).normal()
    best = None
    for local in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        world = (om2.MVector(*local) * matrix).normal()
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
    transforms = transforms or cmds.ls(selection=True, type="transform") or []
    guides = [node for node in transforms if cmds.attributeQuery("ueCollisionShape", node=node, exists=True)]
    if not guides:
        _warn("Select collision guides created by this tool to bake.")
        return []
    cmds.undoInfo(openChunk=True, chunkName="ueCollisionBake")
    try:
        for node in guides:
            constraints = cmds.listRelatives(node, type="constraint") or []
            if constraints:
                cmds.delete(constraints)
            # 2点の間のカプセルの長さを計算しているエクスプレッションと、位置を取り出す decomposeMatrix も消す。
            expressions = cmds.listConnections(node + ".length", source=True, destination=False,
                                               type="expression") if cmds.attributeQuery(
                "length", node=node, exists=True) else None
            for expression in set(expressions or []):
                inputs = cmds.listConnections(expression, source=True, destination=False,
                                              type="decomposeMatrix") or []
                cmds.delete([expression] + list(set(inputs)))
            cmds.delete(node, constructionHistory=True)
            for attribute in ("radius", "length", "segments", "capSegments", "rings", "sizeX", "sizeY", "sizeZ",
                              "endPadding"):
                if cmds.attributeQuery(attribute, node=node, exists=True):
                    cmds.deleteAttr(node, attribute=attribute)
            for attribute in ("translate", "rotate"):
                for channel in "XYZ":
                    cmds.setAttr("{}.{}{}".format(node, attribute, channel), keyable=True)
        print("Baked {} collision guide(s): {}".format(len(guides), ", ".join(guides)))
        return guides
    finally:
        cmds.undoInfo(closeChunk=True)


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
    selection = cmds.ls(selection=True, type="transform") or []
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
    selection = cmds.ls(selection=True, objectsOnly=True, type="transform") or []
    cmds.textFieldButtonGrp(_WINDOW + "Target", edit=True, text=_shortName(selection[0]) if selection else "")


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
    cmds.text(label="Guides go under {}. Edit radius / length / size / segments in the Channel Box.".format(GROUP),
              align="left", wordWrap=True)
    cmds.separator(style="none", height=6)
    _updateEnabled()
    cmds.showWindow(_WINDOW)
    cmds.window(_WINDOW, edit=True, resizeToFitChildren=True)


if __name__ == "__main__":
    show()
