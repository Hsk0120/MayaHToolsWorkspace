"""キャラクタライズ調整部品・ベース骨・バインド骨の追従経路を管理する。"""

import mlib
from maya import cmds
from mlib.decorator import undoTransaction


_ROUTES = {"調整部品 → ベース骨": (1, 2), "ベース骨 → バインド骨": (2, 3), "調整部品 → バインド骨": (1, 3)}
_OWNER = "mlrigPreviewRoot"
_CHANNELS = [name + axis for name in ("translate", "rotate") for axis in "XYZ"]


def inspectRoute(nodes, route):
    """選択リグと経路の送り側・受け側・管理中のコンストレイントを解決する。

    Args:
        nodes (list[str]): ルート、調整部品、ベース骨、バインド骨。
        route (str): 切替対象の経路の表示名。

    Returns:
        tuple: ルート、送り側、受け側、受け側の管理中コンストレイント。

    Raises:
        ValueError: 対象・経路・既存入力が不正な場合。
    """
    paths = []
    for node in nodes:
        matches = mlib.ls(node, long=True, objectsOnly=True).getNames(full=True)
        if len(matches) != 1 or not cmds.objectType(matches[0], isAType="transform"):
            raise ValueError("各役割にトランスフォームを1つ指定してください")
        paths.append(matches[0])
    if route not in _ROUTES or len(paths) != 4 or len(set(paths)) != 4:
        raise ValueError("ルート、調整部品、ベース骨、バインド骨の4つを指定してください")
    root = paths[0]
    if any(not path.startswith(root + "|") for path in paths[1:]):
        raise ValueError("指定したリグ内の役割を選択してください")
    source_index, target_index = _ROUTES[route]
    source, target = paths[source_index], paths[target_index]
    if source.startswith(target + "|") or cmds.referenceQuery(target, isNodeReferenced=True):
        raise ValueError("循環する経路またはリファレンスの宛先は変更できません")
    owned = set()
    for attr in _CHANNELS:
        plug = target + "." + attr
        driver = cmds.connectionInfo(plug, sourceFromDestination=True)
        if cmds.getAttr(plug, lock=True):
            raise ValueError("宛先がロックされています: " + plug)
        if driver:
            node = driver.split(".", 1)[0]
            owner = node + "." + _OWNER
            owners = cmds.listConnections(owner, source=True, destination=False) if cmds.objExists(owner) else []
            if cmds.nodeType(node) != "parentConstraint" or not owners or [item.getName(full=True) for item in mlib.ls(owners[0], long=True)] != [root]:
                raise ValueError("管理外の入力があります: " + plug)
            owned.add(node)
    if len(owned) > 1:
        raise ValueError("宛先の複数経路を解決できません")
    return root, source, target, next(iter(owned), None)


@undoTransaction("mlrigSwitchPreviewRoute")
def switch(nodes, route, disconnect=False):
    """現在の移動・回転を保持して指定経路に切り替える。解除時は専用ノードだけを削除する。

    Args:
        nodes (list[str]): ルート、調整部品、ベース骨、バインド骨。
        route (str): 操作する経路の表示名。
        disconnect (bool): Trueで選択経路を解除する。

    Returns:
        str | None: 接続中の専用コンストレイント。解除するとNone。

    Raises:
        ValueError: 管理外の接続、ロックまたは循環する親子関係がある場合。
    """
    root, source, target, old = inspectRoute(nodes, route)
    if cmds.autoKeyframe(query=True, state=True):
        raise ValueError("自動キーをオフにしてください")
    if old:
        plugs = cmds.listConnections(old, connections=True, plugs=True, source=False, destination=True) or []
        for dest in plugs[1::2]:
            node = dest.split(".", 1)[0]
            if node == old:
                continue
            if [item.getName(full=True) for item in mlib.ls(node, long=True)] != [target] or cmds.attributeName(dest, long=True) not in _CHANNELS:
                raise ValueError("専用コンストレイントに別の出力があります: " + dest)
        drivers = cmds.parentConstraint(old, query=True, targetList=True) or []
        same = len(drivers) == 1 and [item.getName(full=True) for item in mlib.ls(drivers[0], long=True)] == [source]
        if same and not disconnect:
            return old
        if disconnect and not same:
            raise ValueError("指定した経路は接続されていません")
        pose = {attr: cmds.getAttr(target + "." + attr) for attr in _CHANNELS}
        mlib.delete(old)
        for attr, value in pose.items():
            cmds.setAttr(target + "." + attr, value)
    if disconnect:
        return None
    constraint = cmds.parentConstraint(source, target, maintainOffset=True, name="mlrigPreviewRoute#")[0]
    cmds.addAttr(constraint, longName=_OWNER, attributeType="message")
    cmds.connectAttr(root + ".message", constraint + "." + _OWNER)
    return constraint


def show():
    """ルート・調整部品・ベース骨・バインド骨を選び、経路を確認・切替する。"""
    window = "mlrigPreviewRouteEditor"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="プレビューリグの経路")
    cmds.columnLayout(adjustableColumn=True)
    cmds.text(label="ルート・調整部品・ベース骨・バインド骨の順で選択")
    field = cmds.optionMenu(label="経路")
    for route in _ROUTES:
        cmds.menuItem(label=route)
    status = cmds.text(label="")

    def run(action):
        """現在の選択範囲だけを確認または変更する。"""
        nodes = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
        route = cmds.optionMenu(field, query=True, value=True)
        _, source, target, old = inspectRoute(nodes, route)
        if action != "inspect":
            old = switch(nodes, route, disconnect=action == "disconnect")
        cmds.text(status, edit=True, label="{} → {}\n{}".format(source, target, old or "接続なし"))

    for action, label in (("inspect", "確認"), ("switch", "姿勢を保持して接続"), ("disconnect", "解除")):
        cmds.button(label=label, command=lambda *_, a=action: run(a))
    cmds.showWindow(window)
    return window
