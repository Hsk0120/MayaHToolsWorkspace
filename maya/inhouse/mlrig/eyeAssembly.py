"""片眼のコントロールを親に、瞳・ハイライトの設計骨の本数を調整する。"""

from maya import cmds
from mlib.decorator import undoTransaction


def _parts(control):
    result = {"pupil": {}, "highlight": {}}
    for joint in cmds.listRelatives(control, children=True, type="joint", fullPath=True) or []:
        marker = joint + ".mlrigEyeOwner"
        if not cmds.objExists(marker) or not cmds.isConnected(control + ".message", marker):
            continue
        role = cmds.getAttr(joint + ".eyePartRole")
        index = cmds.getAttr(joint + ".eyePartIndex")
        if role not in result or index in result[role]:
            raise ValueError("眼パーツの役割または番号が重複しています")
        result[role][index] = joint
    return result


@undoTransaction("mlrigEyeAssembly")
def rebuild(control, pupils, highlights):
    """既存の役割とコントロールを保持し、欠けた骨の作成と未使用骨の除去を行う。"""
    if any(type(v) is not int or v < 0 for v in (pupils, highlights)) or not cmds.objectType(control, isAType="transform"):
        raise ValueError("眼の親と0以上の本数を指定してください")
    current = _parts(control)
    counts = {"pupil": pupils, "highlight": highlights}
    remove = []
    for role, parts in current.items():
        for index, joint in parts.items():
            if index < counts[role]:
                continue
            if cmds.listRelatives(joint, children=True) or cmds.referenceQuery(joint, isNodeReferenced=True):
                raise ValueError("子または参照がある設計骨を削除できません: " + joint)
            plugs = cmds.listConnections(joint, connections=True, plugs=True) or []
            for dest, source in zip(plugs[::2], plugs[1::2]):
                if dest.rpartition(".")[2] == "mlrigEyeOwner" or (
                    dest.rpartition(".")[2] == "inverseScale" and cmds.isConnected(control + ".scale", joint + ".inverseScale")
                ):
                    continue
                raise ValueError("使用中の設計骨を削除できません: {} / {}".format(dest, source))
            remove.append(joint)
    if remove:
        cmds.delete(remove)
    result = []
    prefix = control.rpartition("|")[2]
    for role, count in counts.items():
        for index in range(count):
            if index in current[role]:
                result.append(current[role][index])
                continue
            joint = cmds.createNode("joint", parent=control, name=":{}_{}{:02d}".format(prefix, role, index + 1))
            cmds.addAttr(joint, longName="mlrigEyeOwner", attributeType="message")
            cmds.connectAttr(control + ".message", joint + ".mlrigEyeOwner")
            cmds.addAttr(joint, longName="eyePartRole", dataType="string")
            cmds.setAttr(joint + ".eyePartRole", role, type="string", lock=True)
            cmds.addAttr(joint, longName="eyePartIndex", attributeType="long", defaultValue=index)
            cmds.setAttr(joint + ".eyePartIndex", lock=True)
            result.append(joint)
    return result


def show():
    """選択した片眼について現在の本数を表示し、必要な設計骨だけを更新する。"""
    nodes = cmds.ls(selection=True, transforms=True, long=True) or []
    if len(nodes) != 1:
        raise ValueError("組み立て先の片眼コントロールを選択してください")
    control = nodes[0]
    parts = _parts(control)
    window = "mlrigEyeAssembly"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="片眼の設計骨を再構築")
    cmds.columnLayout(adjustableColumn=True)
    cmds.text(label=control)
    counts = cmds.intFieldGrp(
        numberOfFields=2,
        label="瞳 / ハイライト",
        value1=max(parts["pupil"], default=-1) + 1,
        value2=max(parts["highlight"], default=-1) + 1,
    )
    cmds.button(
        label="設計骨を更新",
        command=lambda *_: rebuild(
            control, cmds.intFieldGrp(counts, query=True, value1=True), cmds.intFieldGrp(counts, query=True, value2=True)
        ),
    )
    cmds.showWindow(window)
    return window
