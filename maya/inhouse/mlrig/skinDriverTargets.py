"""登録したスキン分布を評価して補正先のスカラー値を更新する。"""

import mlib
from maya import cmds
from mlib import getNode, getPlug
from mlib.decorator import undoTransaction

from . import skinSurface


@undoTransaction("mlrigCreateSkinDriver")
def create(mesh, locator):
    """補正先とインフルエンスの対応を保存するネットワークを作る。"""
    skinSurface.sample(mesh, locator)
    node = mlib.createNode("network", name="skinDistributionDriver#").getName()
    for attr, source in (("sampleMesh", mesh), ("sampleLocator", locator)):
        cmds.addAttr(node, longName=attr, attributeType="message")
        cmds.connectAttr(source + ".message", node + "." + attr)
    for attr in ("influence", "destination"):
        cmds.addAttr(node, longName=attr, attributeType="message", multi=True)
    cmds.addAttr(node, longName="targetAttribute", dataType="string", multi=True)
    return node


def _member(plug):
    """メッセージ接続元をフルパスへ解決する。"""
    source = getPlug(plug).getConnections(source=True, destination=False, index=0)
    if source is None:
        raise ValueError("登録したノードを一意に解決できません: " + plug)
    return source.getNode().getName(full=True)


def targets(node):
    """登録番号ごとのインフルエンスと補正宛先を返す。"""
    rows = {}
    for i in cmds.getAttr(node + ".targetAttribute", multiIndices=True) or []:
        suffix = "[{}]".format(i)
        rows[i] = (_member(node + ".influence" + suffix), _member(node + ".destination" + suffix) + "." +
                   cmds.getAttr(node + ".targetAttribute" + suffix))
    return rows


@undoTransaction("mlrigAddSkinDriverTarget")
def addTarget(node, joint, destination):
    """既存の塗り分けを保持したまま補正先を登録する。"""
    obj, attr = destination.split(".", 1)
    _, weights = skinSurface.sample(_member(node + ".sampleMesh"), _member(node + ".sampleLocator"))
    matches = [item.getName(full=True) for item in mlib.ls(joint, long=True)]
    if len(matches) != 1 or matches[0] not in weights:
        raise ValueError("サンプル面のインフルエンスを指定してください")
    dest = [item.getName(full=True) for item in mlib.ls(obj, long=True)]
    if len(dest) != 1 or not cmds.objExists(destination) or cmds.getAttr(destination, type=True) not in ("double", "float"):
        raise ValueError("補正先のスカラーPlugを指定してください")
    rows = targets(node)
    if any(d == dest[0] + "." + attr for _, d in rows.values()):
        raise ValueError("補正先はすでに登録されています")
    i = max(rows, default=-1) + 1
    cmds.connectAttr(joint + ".message", "{}.influence[{}]".format(node, i))
    cmds.connectAttr(dest[0] + ".message", "{}.destination[{}]".format(node, i))
    cmds.setAttr("{}.targetAttribute[{}]".format(node, i), attr, type="string")
    return i


@undoTransaction("mlrigAddSkinDriverColumn")
def addColumn(node, destination):
    """ゼロウェイトのターゲット骨を追加し、その列を補正先へ登録する。"""
    mesh = _member(node + ".sampleMesh")
    skins = mlib.ls(cmds.listHistory(mesh, pruneDagObjects=True) or [], type="skinCluster").getNames()
    if len(skins) != 1:
        raise ValueError("単一のスキンクラスタを指定してください")
    joint = mlib.createNode("joint", name="skinDriverTarget#", skipSelect=True).getName()
    cmds.skinCluster(skins[0], edit=True, addInfluence=joint, weight=0.0)
    index = addTarget(node, joint, destination)
    cmds.addAttr(joint, longName="mlrigSkinTargetOwner", attributeType="message")
    cmds.connectAttr(node + ".message", joint + ".mlrigSkinTargetOwner")
    return index, joint


@undoTransaction("mlrigRemoveSkinDriverTarget")
def removeTarget(node, index):
    """指定した登録だけを除外する。"""
    rows = targets(node)
    if index not in rows:
        raise ValueError("未登録の番号です")
    joint, _ = rows[index]
    owned = joint + ".mlrigSkinTargetOwner"
    if cmds.objExists(owned) and cmds.isConnected(node + ".message", owned) and sum(j == joint for j, _ in rows.values()) == 1:
        mesh = _member(node + ".sampleMesh")
        skin, = mlib.ls(cmds.listHistory(mesh, pruneDagObjects=True), type="skinCluster").getNames()
        if any(weight != 0.0 for weight in getNode(skin).getWeights([joint])):
            raise ValueError("ウェイトが残っています。先に他の列へ移してください")
        cmds.skinCluster(skin, edit=True, removeInfluence=joint)
        cmds.disconnectAttr(node + ".message", owned)
    for attr in ("targetAttribute", "influence", "destination"):
        cmds.removeMultiInstance("{}.{}[{}]".format(node, attr, index), b=True)


@undoTransaction("mlrigApplySkinDriver")
def apply(node):
    """現在位置で全登録列を評価し、書き込み可能な補正先へ一括適用する。"""
    _, weights = skinSurface.sample(_member(node + ".sampleMesh"), _member(node + ".sampleLocator"))
    values = {}
    for joint, plug in targets(node).values():
        if joint not in weights or not cmds.getAttr(plug, settable=True) or cmds.connectionInfo(plug, isDestination=True):
            raise ValueError("補正先またはインフルエンスを確認してください: " + plug)
        values[plug] = weights[joint]
    for plug, value in values.items():
        cmds.setAttr(plug, value)
    return values


def show():
    """選択メッシュと位置から登録するか、既存のドライバーを編集する。"""
    selection = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
    if len(selection) == 2:
        mesh, locator = selection
        if cmds.nodeType(mesh) != "mesh":
            mesh, = cmds.listRelatives(mesh, shapes=True, noIntermediate=True, type="mesh", fullPath=True) or []
        node = create(mesh, locator)
    elif len(selection) == 1 and cmds.objExists(selection[0] + ".sampleMesh"):
        node = selection[0]
    else:
        raise ValueError("メッシュと位置、または既存ドライバーを選択してください")
    window = "mlrigSkinTargets"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="スキン分布の補正先")
    cmds.columnLayout(adjustableColumn=True)
    joint = cmds.textFieldGrp(label="インフルエンス")
    dst = cmds.textFieldGrp(label="補正先Plug")
    listing = cmds.textScrollList()
    def refresh():
        cmds.textScrollList(listing, edit=True, removeAll=True)
        for index, row in targets(node).items():
            cmds.textScrollList(listing, edit=True, append="{}  {} → {}".format(index, *row))
    def add(*_):
        addTarget(node, cmds.textFieldGrp(joint, query=True, text=True), cmds.textFieldGrp(dst, query=True, text=True))
        refresh()
    def new_column(*_):
        addColumn(node, cmds.textFieldGrp(dst, query=True, text=True))
        refresh()
    def remove(*_):
        chosen = cmds.textScrollList(listing, query=True, selectItem=True) or []
        if chosen:
            removeTarget(node, int(chosen[0].split()[0]))
            refresh()
    cmds.button(label="補正先を追加", command=add)
    cmds.button(label="新規骨とゼロウェイト列を追加", command=new_column)
    cmds.button(label="選択した登録を解除", command=remove)
    cmds.button(label="現在位置で評価・適用", command=lambda *_: apply(node))
    refresh()
    cmds.showWindow(window)
