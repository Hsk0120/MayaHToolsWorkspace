"""既存の補正ターゲットとウェイト入力を確認し、編集形状を管理する。"""

import mlib
from maya import cmds


def show():
    """単一ベースのBlendShapeを選択してターゲット管理画面を開く。"""
    nodes = mlib.ls(selection=True, type="blendShape").getNames()
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
            selected = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
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


def inspectOwnership(roots):
    """部位配下のベース・ターゲット元形状・ドライバーと共有先を読み取る。

    Args:
        roots (list[str]): 部位を表すDAGパス。ネストする場合は最も近い部位を使う。

    Returns:
        list[dict]: 補正先、関連する部位、ベース、共有先、ウェイト入力の一覧。
    """
    roots = sorted({mlib.getNode(node).getName(full=True) for node in roots}, key=len, reverse=True)
    if not roots or any(not path.startswith("|") for path in roots):
        raise ValueError("部位のDAGルートを選択してください")
    records = []
    users = {}
    for name in mlib.ls(type="blendShape").getNames():
        node = mlib.getNode(name)
        bases = list(node.getBaseGeometry())
        names = {node.getTargetIndex(alias): alias for alias in node.getTargetNames()}
        for index in cmds.getAttr(name + ".weight", multiIndices=True) or []:
            target = names.get(index, "weight[{}]".format(index))
            plug = "{}.weight[{}]".format(name, index)
            driver = cmds.connectionInfo(plug, sourceFromDestination=True)
            driver_paths = ([item.getName(full=True) for item in mlib.ls(driver.split(".", 1)[0], long=True)]) if driver else []
            sources = set()
            affected = set()
            for base in bases:
                number = node.getGeometryIndices(base)
                groups = "{}.inputTarget[{}].inputTargetGroup".format(name, number)
                if index not in (cmds.getAttr(groups, multiIndices=True) or []):
                    continue
                affected.add(base.getName(full=True))
                for shape in node.getTargetGeometry(index, base=base).values():
                    if shape is not None:
                        sources.add(shape.getName(full=True))
            parts = set()
            for path in affected.union(sources, driver_paths):
                closest = next((root for root in roots if path == root or path.startswith(root + "|")), None)
                if closest:
                    parts.add(closest)
            for source in sources:
                users.setdefault(source, set()).add(plug)
            records.append(dict(plug=plug, target=target, parts=sorted(parts), bases=sorted(affected),
                                sources=sorted(sources), driver=driver))
    result = []
    for row in records:
        if row["parts"]:
            others = {plug for source in row["sources"] for plug in users[source]} - {row["plug"]}
            row["sharedWith"] = sorted(others)
            result.append(row)
    return result


def showOwnership():
    """部位に関係する補正先と、入力ドライバー・共有先を表示する。"""
    window = "mlrigCorrectionOwnership"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="部位別補正ターゲット")
    cmds.columnLayout(adjustableColumn=True)
    cmds.text(label="対象の部位ルートを選択してください")
    output = cmds.scrollField(editable=False, wordWrap=False, height=260)

    def refresh(*_):
        """選択ルートと現在の接続から表示する。"""
        rows = inspectOwnership(mlib.ls(selection=True, long=True, objectsOnly=True).getNames(full=True))
        lines = []
        for row in rows:
            lines.append("{}  {}  部位 {}".format(row["target"], row["plug"], ", ".join(row["parts"])))
            lines.append("  ベース {}  ドライバー {}".format(", ".join(row["bases"]), row["driver"] or "なし"))
            lines.append("  元形状を共有する補正先 {}".format(", ".join(row["sharedWith"]) or "なし"))
        cmds.scrollField(output, edit=True, text="\n".join(lines) or "選択部位との関連を確認できた項目はありません")

    cmds.button(label="現在の部位で照会", command=refresh)
    cmds.showWindow(window)
    return window
