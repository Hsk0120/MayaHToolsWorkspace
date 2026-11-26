"""既存の補正ターゲットとウェイト入力を確認し、編集形状を管理する。"""

import mlib
from maya import cmds


def show():
    """単一ベースのBlendShapeを選択してターゲット管理画面を開く。"""
    nodes = cmds.ls(selection=True, type="blendShape") or []
    if len(nodes) != 1:
        raise ValueError("管理するBlendShapeノードを1つ選択してください")
    node = mlib.getNode(nodes[0])
    if len(node.getBaseGeometry()) != 1:
        raise ValueError("単一ベースのBlendShapeを指定してください")
    window = "mlrigCorrectionTargets"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="補正ターゲットの管理")
    cmds.columnLayout(adjustableColumn=True)
    listing = cmds.textScrollList(allowMultiSelection=False)
    names = []

    def refresh(*unused):
        names[:] = node.getTargetNames()
        cmds.textScrollList(listing, edit=True, removeAll=True)
        for name in names:
            geometry = node.getTargetGeometry(name)
            shape = geometry.get(6000)
            driver = cmds.connectionInfo(node.getName() + "." + name, sourceFromDestination=True)
            description = str(shape) if shape is not None else "保存差分のみ" if 6000 in geometry else "1.0の項目なし"
            cmds.textScrollList(listing, edit=True, append="{}  |  {}  |  {}".format(name, description, driver or "入力なし"))

    def act(action):
        if action in ("add", "replace"):
            selected = cmds.ls(selection=True, long=True) or []
            if len(selected) != 1:
                raise ValueError("ターゲットにするメッシュを1つ選択してください")
        if action == "add":
            node.addTarget(selected[0])
        else:
            index = cmds.textScrollList(listing, query=True, selectIndexedItem=True) or []
            if not index:
                raise ValueError("操作するターゲットを一覧から選択してください")
            name = names[index[0] - 1]
            if action == "replace":
                node.replaceTarget(name, selected[0])
            elif action == "restore":
                node.regenerateTarget(name)
            else:
                if cmds.connectionInfo(node.getName() + "." + name, isDestination=True):
                    raise ValueError("ウェイトに入力があります。形状の再登録を使用してください")
                node.removeTarget(name)
        refresh()

    for action, label in (("add", "選択メッシュを追加"), ("replace", "選択メッシュを再登録"), ("restore", "編集形状を再生成"), ("remove", "ターゲットを削除")):
        cmds.button(label=label, command=lambda *_, op=action: act(op))
    cmds.button(label="一覧を更新", command=refresh)
    refresh()
    cmds.showWindow(window)
    return window
