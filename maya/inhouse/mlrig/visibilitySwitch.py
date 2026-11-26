"""コントローラーの用途別スイッチと各対象のvisibilityを接続する。"""

import re

from maya import cmds
from mlib.decorator import undoTransaction


def inspect(target):
    """対象と祖先のvisibility、表示オーバーライド、レイヤー、参照元を表示する。"""
    rows = []
    node = target
    while node:
        visibility = node + ".visibility"
        driver = cmds.connectionInfo(visibility, sourceFromDestination=True)
        layers = cmds.listConnections(node + ".drawOverride", type="displayLayer", source=True, destination=False) or []
        settings = []
        for layer in layers:
            settings.append("{}={}".format(layer, int(cmds.getAttr(layer + ".visibility"))))
        rows.append("{}  visibility={}  入力={}  ロック={}  override={}/{}  レイヤー={}  参照={}".format(
            node, int(cmds.getAttr(visibility)), driver or "なし", int(cmds.getAttr(visibility, lock=True)),
            int(cmds.getAttr(node + ".overrideEnabled")), int(cmds.getAttr(node + ".overrideVisibility")),
            ", ".join(settings) or "なし", int(cmds.referenceQuery(node, isNodeReferenced=True))))
        node = node.rpartition("|")[0]
    return rows


@undoTransaction("mlrigVisibilitySwitch")
def connect(control, targets, name):
    """用途別boolを登録し、既存入力のない対象のvisibilityへまとめて接続する。"""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) or not targets:
        raise ValueError("用途名と表示対象を指定してください")
    source = control + "." + name
    exists = cmds.objExists(source)
    if exists and (name not in (cmds.listAttr(control, userDefined=True) or []) or cmds.getAttr(source, type=True) != "bool"):
        raise ValueError("用途名が別のアトリビュートと重複しています")
    for target in targets:
        dest = target + ".visibility"
        if exists and cmds.isConnected(source, dest):
            continue
        if target == control or control.startswith(target + "|") or cmds.connectionInfo(dest, isDestination=True) or not cmds.getAttr(dest, settable=True):
            raise ValueError("既存入力・階層・ロックを確認してください: " + dest)
    if not exists:
        cmds.addAttr(control, longName=name, attributeType="bool", defaultValue=True, keyable=True)
    for target in targets:
        if not cmds.isConnected(source, target + ".visibility"):
            cmds.connectAttr(source, target + ".visibility")
    return source


def show():
    """選択順にスイッチの所有者と対象を確定し、現在の表示配線を確認する。"""
    nodes = cmds.ls(selection=True, long=True, transforms=True) or []
    if len(nodes) < 2:
        raise ValueError("コントローラー、表示対象の順に2つ以上選択してください")
    window = "mlrigVisibilitySwitch"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="表示の配線と検査")
    cmds.columnLayout(adjustableColumn=True)
    name = cmds.textFieldGrp(label="用途名", text="showControls")
    field = cmds.scrollField(editable=False, height=180)

    def refresh(*_):
        cmds.scrollField(field, edit=True, text="\n".join(line for target in nodes[1:] for line in inspect(target)))

    def wire(*_):
        connect(nodes[0], nodes[1:], cmds.textFieldGrp(name, query=True, text=True))
        refresh()

    cmds.button(label="配線を確認", command=refresh)
    cmds.button(label="表示スイッチを接続", command=wire)
    refresh()
    cmds.showWindow(window)
    return window
