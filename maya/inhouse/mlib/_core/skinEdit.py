"""skinClusterのウェイト移送とinfluence解除をOpenMayaで実行する。"""

import maya.api.OpenMaya as om2

from .nodeEdit import require_editable


def transfer_weights(skin, pairs):
    """skinPercentの移送とinteractive正規化を再現する。

    Args:
        skin (SkinCluster): 更新先。
        pairs (list[tuple[str, str]]): 検証済みのinfluence名ペア。
    """
    if len(skin.fn.getOutputGeometry()) != 1:
        raise NotImplementedError("fast weight transfer requires one geometry")
    names, values = skin._editable_weights()
    influences = skin.getInfluences()
    ids = [node.getUuid() for node in influences]
    width = len(names)
    from ..nodes.node import Node
    indices = [(ids.index(Node(source).getUuid()), ids.index(Node(target).getUuid()))
               for source, target in pairs]
    normalize = skin.getPlug("normalizeWeights").get() == 1
    for source, target in indices:
        for offset in range(0, len(values), width):
            if values[offset + source] <= 0:
                continue
            # MayaのtransformMoveWeightsは既存targetへ加算せず、
            # source値で置き換えてから正規化する。通常経路と同じ結果にする。
            values[offset + target] = values[offset + source]
            values[offset + source] = 0.0
            if normalize:
                total = sum(values[offset:offset + width])
                if total > 0:
                    values[offset:offset + width] = [v / total for v in values[offset:offset + width]]
    skin.setWeights(names, values)


def remove_influence(skin, source):
    """残存ウェイトとbindPoseの構造を検査後にinfluenceを登録解除する。

    Args:
        skin (SkinCluster): 対象skinCluster。単一meshに限定する。
        source (Joint): 登録解除するinfluence。
    """
    require_editable(skin.mnode())
    names, values = skin._editable_weights()
    if len(skin.fn.getOutputGeometry()) != 1:
        raise NotImplementedError("fast influence removal requires one geometry")
    om2.MFnMesh(skin.mesh_path)
    influences = skin.getInfluences()
    index = next(i for i, node in enumerate(influences) if node.getUuid() == source.getUuid())
    logical = skin.fn.indexForInfluenceObject(influences[index].mpath())
    width = len(influences)
    normalize = skin.getPlug("normalizeWeights").get() == 1
    modified_vertices = []
    for offset in range(0, len(values), width):
        if values[offset + index] == 0:
            continue
        modified_vertices.append(offset // width)
        values[offset + index] = 0.0
        total = sum(values[offset:offset + width])
        for column in range(width):
            if column == index:
                continue
            if total <= 0:
                values[offset + column] = 1.0 / (width - 1)
            elif normalize:
                values[offset + column] /= total
    remove = _removal_structure(skin, source, logical)
    weight_list = skin.getPlug("weightList").mplug()
    for vertex in modified_vertices:
        row = weight_list.elementByLogicalIndex(vertex).child(0)
        if logical in row.getExistingArrayAttributeIndices():
            remove.append(row.elementByLogicalIndex(logical))
    _validate_removal_locks(remove)
    skin.setWeights(names, values)
    # 切断・配列削除は一つのmodifierで実行する。ノード削除はこの中へ混在させない。
    modifier = om2.MDGModifier()
    for plug in remove:
        modifier.removeMultiInstance(plug, True)
    modifier.doIt()


def _removal_structure(skin, source, logical):
    """influenceとbindPoseの除去対象を、値を変更せず解決する。

    Args:
        skin (SkinCluster): 対象。
        source (Joint): 除去するinfluence。
        logical (int): influenceの論理番号。

    Returns:
        list[MPlug]: 除去する構造プラグ。
    """
    remove = []
    for attr in ("matrix", "lockWeights", "influenceColor"):
        array = skin.getPlug(attr).mplug()
        if logical in array.getExistingArrayAttributeIndices():
            remove.append(array.elementByLogicalIndex(logical))
    pose_source = skin.getPlug("bindPose").getSource(skipConversionNodes=False)
    if pose_source is not None:
        pose = pose_source.getNode()
        require_editable(pose.mnode())
        members = pose.getPlug("members").mplug()
        for member_index in members.getExistingArrayAttributeIndices():
            member = members.elementByLogicalIndex(member_index)
            origins = member.connectedTo(True, False)
            if not origins or origins[0].node() != source.mnode():
                continue
            for attr in ("members", "worldMatrix", "xformMatrix", "global", "parents"):
                array = pose.getPlug(attr).mplug()
                if member_index in array.getExistingArrayAttributeIndices():
                    remove.append(array.elementByLogicalIndex(member_index))
    return remove


def _validate_removal_locks(remove):
    """親を含むロックを、全ての配列削除より前に確認する。

    Args:
        remove (list[MPlug]): 除去予定の配列要素。
    """
    for plug in remove:
        current = plug
        while True:
            if current.isLocked:
                raise RuntimeError("Attribute is locked: " + plug.name())
            if current.isChild:
                current = current.parent()
            elif current.isElement:
                current = current.array()
            else:
                break


def validate_removal(skin, source):
    """ウェイト移送・修復前に構造の変更可否を確認する。

    Args:
        skin (SkinCluster): 対象。
        source (Joint): 除去するinfluence。
    """
    require_editable(skin.mnode())
    if len(skin.fn.getOutputGeometry()) != 1:
        raise NotImplementedError("fast influence removal requires one geometry")
    om2.MFnMesh(skin.mesh_path)
    skin._editable_weight_list()
    logical = skin.fn.indexForInfluenceObject(source.mpath())
    _validate_removal_locks(_removal_structure(skin, source, logical))
