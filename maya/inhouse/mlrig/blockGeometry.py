"""スキンの面ウェイトを使って部位別ブロック形状を生成する。"""

from collections import defaultdict

from maya import cmds
import mlib
from mlib.decorator import undoTransaction


def classify(nodes):
    """各メッシュの面を合計ウェイト最大のインフルエンスへ分類する。

    Args:
        nodes (list[str]): スキン付きメッシュ形状またはトランスフォーム。

    Returns:
        dict: インフルエンスのフルパスから形状・面番号リストの組への対応。

    Raises:
        ValueError: 形状またはスキンが一意に決まらない、またはウェイトが空の場合。
    """
    result = defaultdict(list)
    shapes = set()
    for node in nodes:
        matches = mlib.ls(node, long=True, objectsOnly=True).getNames(full=True)
        if len(matches) != 1:
            raise ValueError("対象をフルパスで指定してください")
        node = matches[0]
        found = [node] if cmds.nodeType(node) == "mesh" else cmds.listRelatives(node, shapes=True, noIntermediate=True, type="mesh", fullPath=True)
        if not found:
            raise ValueError("メッシュを選択してください: " + node)
        shapes.update(found)
    if not shapes:
        raise ValueError("スキン付きメッシュを選択してください")
    for shape in sorted(shapes):
        skins = mlib.ls(cmds.listHistory(shape, pruneDagObjects=True) or [], type="skinCluster").getNames()
        if len(skins) != 1:
            raise ValueError("スキンを1つ持つ形状を指定してください: " + shape)
        skin = mlib.getNode(skins[0])
        influences = list(skin.getInfluences())
        paths = [joint.getName(full=True) for joint in influences]
        number = skin.getGeometryIndices(shape)
        weights = skin.getWeights(influences, rows=True, geometryIndex=number)
        mesh = mlib.getNode(shape)
        output = skin.getPlug("outputGeometry")[number]
        skinned = mesh.mfn()
        skinned.setObject(output.mplug().asMObject())
        source_faces = skinned.getVertices()
        current_faces = mesh.getTopology()
        if len(weights) != mesh.getNumVertices() or any(list(a) != list(b) for a, b in zip(source_faces, current_faces)):
            raise ValueError("スキン出力と表示形状のトポロジーが一致しません: " + shape)
        groups = defaultdict(list)
        offset = 0
        for face, count in enumerate(current_faces[0]):
            vertices = current_faces[1][offset:offset + count]
            offset += count
            sums = [sum(column) for column in zip(*(weights[i] for i in vertices))]
            if not sums or max(sums) <= 0:
                raise ValueError("ウェイトのない面があります: {}.f[{}]".format(shape, face))
            winner = sums.index(max(sums))
            groups[paths[winner]].append(face)
        for joint, faces in groups.items():
            result[joint].append((shape, faces))
    return dict(result)


@undoTransaction("mlrigBuildBlockGeometry")
def build(nodes, combine=True):
    """評価済みの面をコピーして所属骨へ配置し、必要なら同一骨の形状を統合する。

    Args:
        nodes (list[str]): スキン付きメッシュ形状またはトランスフォーム。
        combine (bool): 同じ骨に属する複数の入力形状を統合する。

    Returns:
        list[str]: 生成されたトランスフォームのフルパス。

    Raises:
        ValueError: スキンの対応が不明な場合、または所属骨がリファレンス内の場合。
    """
    # HToolsの面材質を保持する抽出操作は、ブロック生成時だけ利用する。
    from HTools.rigging.boneFacePreview import extract

    groups = classify(nodes)
    result = []
    for joint, items in groups.items():
        if cmds.referenceQuery(joint, isNodeReferenced=True):
            raise ValueError("リファレンスの骨には追加できません: " + joint)
        pieces = [extract(shape, faces) for shape, faces in items]
        if combine and len(pieces) > 1:
            pieces = [cmds.polyUnite(pieces, constructionHistory=False, mergeUVSets=1, name="blockGeometry#")[0]]
        for piece in pieces:
            node = cmds.parent(piece, joint, absolute=True)[0]
            full = joint + "|" + node.rsplit("|", 1)[-1]
            full = cmds.rename(full, "blockGeometry#")
            result.append(joint + "|" + full.rsplit("|", 1)[-1])
    return result


def show():
    """選択バインドメッシュの部位別面数を確認してブロック形状を生成する。"""
    window = "mlrigBlockGeometry"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="バインド形状からブロックを生成")
    cmds.columnLayout(adjustableColumn=True)
    combine = cmds.checkBox(label="同じ骨に属する複数メッシュを統合", value=True)
    report = cmds.scrollField(editable=False, wordWrap=False, height=150)

    def show_result(create):
        """最新の選択と評価値から分類または生成結果を表示する。"""
        nodes = mlib.ls(selection=True, long=True, objectsOnly=True).getNames(full=True)
        if create:
            lines = build(nodes, cmds.checkBox(combine, query=True, value=True))
        else:
            lines = ["{}  {}面".format(joint, sum(len(faces) for _, faces in items)) for joint, items in classify(nodes).items()]
        cmds.scrollField(report, edit=True, text="\n".join(lines))

    cmds.button(label="部位別の面数を確認", command=lambda *_: show_result(False))
    cmds.button(label="ブロック生成", command=lambda *_: show_result(True))
    cmds.showWindow(window)
    return window
