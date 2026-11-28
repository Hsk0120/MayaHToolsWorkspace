"""名前空間の異なるリグで共有する、役割名と公開チャンネルの対応定義。"""

import json
import re
import tempfile
from pathlib import Path

import mlib
import maya.cmds as cmds
from mlib.decorator import undoChunk, undoTransaction


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ATTRIBUTE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\[[0-9]+\])?")


def resolveChannels(root, definitions):
    """指定したリグの下で公開チャンネルを解決し、解決済みと欠損の辞書を返す。

    Args:
        root (str): 対象個体のルートTransform。フルDAGパスを推奨する。
        definitions (dict): 役割名から(rootからの相対DAGパス、属性名)への対応。
            各パス要素にはルートと同じ名前空間を補う。空パスはルート自身。

    Returns:
        tuple: 役割名からフルPlug名への辞書と、解決できなかった役割名から理由への辞書。
    """
    matches = mlib.ls(root, long=True, type="transform").getNames(full=True)
    if len(matches) != 1 or matches[0].split("|")[-1] != root.split("|")[-1]:
        raise ValueError("対象リグのルートを一意に指定してください")
    root_path = matches[0]
    namespace = root_path.split("|")[-1].rpartition(":")[0]
    prefix = namespace + ":" if namespace else ""
    channels = {}
    missing = {}
    for role, (relative, attribute) in definitions.items():
        parts = relative.split("|") if relative else []
        if not role or not _ATTRIBUTE.fullmatch(attribute) or not all(_IDENTIFIER.fullmatch(part) for part in parts):
            raise ValueError("相対パスと属性名に無効な名前があります: {}".format(role))
        node = root_path + "".join("|" + prefix + part for part in parts)
        plug = node + "." + attribute
        if not cmds.objExists(node):
            missing[role] = "ノードが見つかりません: " + node
        elif not cmds.objExists(plug):
            missing[role] = "属性が見つかりません: " + plug
        else:
            channels[role] = plug
    return channels, missing


_PORT_ATTRIBUTE = "mlrigPublishedChannels"


def _validatedPorts(root, ports):
    """保存形式を検証し、その個体で解決した役割と欠損を返す。"""
    if not isinstance(ports, dict):
        raise ValueError("公開チャンネルには役割をキーとする辞書を指定してください")
    definitions = {}
    for role, port in ports.items():
        if not isinstance(role, str) or not role.strip() or not isinstance(port, dict):
            raise ValueError("公開チャンネルの役割名と定義を確認してください")
        if set(port) != {"path", "attribute", "kind"} or not all(isinstance(value, str) for value in port.values()):
            raise ValueError("path、attribute、kindを文字列で指定してください")
        if port["kind"] not in ("default", "static", "constraint", "deformer", "externalRig", "irregular", "geometry"):
            raise ValueError("不明な公開チャンネル種別です: " + port["kind"])
        definitions[role] = (port["path"], port["attribute"])
    return resolveChannels(root, definitions)


def getPorts(root):
    """ルートに保存した役割別の公開チャンネル定義を取得する。"""
    resolveChannels(root, {})
    plug = root + "." + _PORT_ATTRIBUTE
    if not cmds.objExists(plug):
        return {}
    record = json.loads(cmds.getAttr(plug))
    if record.get("schema") != 1:
        raise ValueError("未対応の公開チャンネル定義です")
    ports = record["ports"]
    _validatedPorts(root, ports)
    return ports


@undoChunk("mlrigSetPublishedChannels")
def setPorts(root, ports):
    """接続先をすべて検査し、役割・種別・相対パスをルートへ保存する。"""
    _, missing = _validatedPorts(root, ports)
    if missing:
        raise ValueError("\n".join(missing.values()))
    plug = root + "." + _PORT_ATTRIBUTE
    if cmds.objExists(plug):
        getPorts(root)
    else:
        cmds.addAttr(root, longName=_PORT_ATTRIBUTE, dataType="string")
    cmds.setAttr(plug, json.dumps({"schema": 1, "ports": ports}, ensure_ascii=False), type="string")


def showEditor():
    """選択したルートの公開チャンネルを表示し、定義を編集する。"""
    roots = mlib.ls(selection=True, long=True, type="transform").getNames(full=True)
    if len(roots) != 1:
        raise ValueError("リグのルートを1つ選択してください")
    root = roots[0]
    ports = getPorts(root)
    window = "mlrigPublishedChannelEditor"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="公開チャンネル")
    cmds.columnLayout(adjustableColumn=True)
    cmds.text(label=root)
    cmds.text(label='記入例  "hand": {"path":"hand", "attribute":"rotateX", "kind":"default"}')
    editor = cmds.scrollField("mlrigPublishedPortDefinition", text=json.dumps(ports, indent=2, ensure_ascii=False), height=180)
    status = cmds.scrollField(editable=False, height=100)

    def inspect(*_):
        ports = json.loads(cmds.scrollField(editor, query=True, text=True))
        found, missing = _validatedPorts(root, ports)
        lines = ["{}  {}".format(role, value) for role, value in {**found, **missing}.items()]
        cmds.scrollField(status, edit=True, text="\n".join(lines))

    def save(*_):
        setPorts(root, json.loads(cmds.scrollField(editor, query=True, text=True)))
        inspect()

    cmds.button(label="対象を確認", command=inspect)
    cmds.button(label="定義を保存", command=save)
    cmds.button(label="保存済みのピッカーを開く", command=lambda *_: showPicker(root))
    inspect()
    cmds.showWindow(window)


def selectRole(root, role):
    """保存済みの役割に対応するノードと公開チャンネルを選択する。"""
    ports = getPorts(root)
    if role not in ports:
        raise ValueError("公開されていない役割です: " + role)
    resolved, missing = _validatedPorts(root, {role: ports[role]})
    if missing:
        raise ValueError(missing[role])
    plug = resolved[role]
    node = plug.rsplit(".", 1)[0]
    mlib.select(node, replace=True)
    if cmds.channelBox("mainChannelBox", exists=True):
        def highlight():
            """選択変更がChannel Boxへ反映された後に対象属性を選ぶ。"""
            if [item.getName(full=True) for item in mlib.ls(selection=True, long=True)] == [node] and cmds.objExists(plug):
                cmds.channelBox("mainChannelBox", edit=True, select=plug)

        cmds.evalDeferred(highlight, lowestPriority=True)
    return plug


@undoTransaction("mlrigCaptureChannelDefaults")
def captureDefaults(root, roles):
    """選択した公開スカラーチャンネルの現在値を役割別に記録する。"""
    ports = getPorts(root)
    found, missing = _validatedPorts(root, {role: ports[role] for role in roles})
    if missing:
        raise ValueError(str(missing))
    plug = root + ".mlrigChannelDefaults"
    values = json.loads(cmds.getAttr(plug)) if cmds.objExists(plug) else {}
    for role, source in found.items():
        value = cmds.getAttr(source)
        if not isinstance(value, (bool, int, float)):
            raise ValueError("数値チャンネルを選択してください: " + role)
        values[role] = value
    if not cmds.objExists(plug):
        cmds.addAttr(root, longName="mlrigChannelDefaults", dataType="string")
    cmds.setAttr(plug, json.dumps(values, ensure_ascii=False), type="string")
    return values


def updatePortLibrary(root, path, roles, *, remove=False):
    """ライブラリの指定役割だけを書き換え、他の登録・別ライブラリを保持する。"""
    path = Path(path)
    ports = getPorts(root)
    saved = {}
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("schema") != 1:
            raise ValueError("未対応の定義ファイルです")
        saved = record["ports"]
        _validatedPorts(root, saved)
    for role in roles:
        if remove:
            if role not in saved:
                raise ValueError("ライブラリに役割がありません: " + role)
            del saved[role]
        else:
            saved[role] = ports[role]
    data = json.dumps({"schema": 1, "ports": saved}, ensure_ascii=False, indent=2)
    with tempfile.TemporaryDirectory(dir=str(path.parent)) as directory:
        temp = Path(directory) / path.name
        temp.write_text(data, encoding="utf-8")
        temp.replace(path)
    return saved


def showPicker(root):
    """指定した個体の保存済み定義から役割ごとの選択ボタンを作る。"""
    ports = getPorts(root)
    resolved, missing = _validatedPorts(root, ports)
    window = "mlrigPublishedChannelPicker"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="公開チャンネルの選択")
    cmds.columnLayout(adjustableColumn=True)
    cmds.text(label=root)
    for role in ports:
        cmds.button(label=role, annotation=resolved.get(role) or missing[role], enable=role in resolved,
                    command=lambda *_, role=role: selectRole(root, role))
    if ports:
        listing = cmds.textScrollList(allowMultiSelection=True, append=list(ports))

        def move(offset):
            indices = cmds.textScrollList(listing, query=True, selectIndexedItem=True) or []
            if len(indices) != 1:
                raise ValueError("移動する役割を1つ選択してください")
            index = indices[0] - 1
            order = list(ports)
            if 0 <= index + offset < len(order):
                if list(getPorts(root).items()) != list(ports.items()):
                    raise ValueError("定義が変更されました。ピッカーを開き直してください")
                order.insert(index + offset, order.pop(index))
                setPorts(root, {role: ports[role] for role in order})
                showPicker(root)

        def chosen():
            roles = cmds.textScrollList(listing, query=True, selectItem=True) or []
            if not roles:
                raise ValueError("対象の役割を選択してください")
            return roles

        def library(action):
            paths = cmds.fileDialog2(fileMode=0 if action == "save" else 1, fileFilter="JSON (*.json)") or []
            if not paths:
                return
            path = Path(paths[0])
            if action in ("save", "remove"):
                updatePortLibrary(root, path, chosen(), remove=action == "remove")
                return
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("schema") != 1:
                raise ValueError("未対応の定義ファイルです")
            imported = record["ports"]
            found, absent = _validatedPorts(root, imported)
            lines = [role + " → " + target + ("（一致）" if ports.get(role) == imported[role] else "（定義差あり）")
                     for role, target in {**found, **absent}.items()]
            cmds.confirmDialog(title="公開定義の照合", message="\n".join(lines), button=["閉じる"])
            if action == "restore":
                selected = chosen()
                if any(role not in found for role in selected):
                    raise ValueError("選択した役割の復元先が見つかりません")
                setPorts(root, {**getPorts(root), **{role: imported[role] for role in selected}})
                showPicker(root)

        cmds.button(label="上へ移動", command=lambda *_: move(-1))
        cmds.button(label="下へ移動", command=lambda *_: move(1))
        cmds.button(label="選択した役割の現在値を初期値に記録", command=lambda *_: captureDefaults(root, chosen()))
        cmds.button(label="選択した定義を書き出す", command=lambda *_: library("save"))
        cmds.button(label="ライブラリから選択した登録を外す", command=lambda *_: library("remove"))
        cmds.button(label="外部定義の解決先を確認", command=lambda *_: library("compare"))
        cmds.button(label="選択した役割の定義を復元", command=lambda *_: library("restore"))
    if not ports:
        cmds.text(label="登録された役割がありません")
    cmds.showWindow(window)
    return window


def inspectExternalPorts(sourceRoot, destinationRoot):
    """二つのリグの外部ポートを役割別に照合し、対応Plug・状態・既存入力を返す。"""
    source = getPorts(sourceRoot)
    destination = getPorts(destinationRoot)
    sources, source_missing = _validatedPorts(sourceRoot, source)
    destinations, destination_missing = _validatedPorts(destinationRoot, destination)
    roles = {role for ports in (source, destination) for role, port in ports.items() if port["kind"] in ("externalRig", "geometry")}
    result = {}
    for role in sorted(roles):
        src = sources.get(role)
        dst = destinations.get(role)
        incoming = cmds.connectionInfo(dst, sourceFromDestination=True) if dst else ""
        if not src or not dst:
            state = source_missing.get(role) or destination_missing.get(role) or "役割が片側にありません"
        elif source[role]["kind"] != destination[role]["kind"]:
            state = "外部ポートの種別が一致しません"
        elif src == dst:
            state = "同一のポートです"
        elif cmds.isConnected(src, dst):
            state = "接続済み"
        elif incoming:
            state = "別の入力があります"
        elif not cmds.attributeQuery(src.split(".")[-1].partition("[")[0], node=src.split(".")[0], readable=True):
            state = "送り側から読み取れません"
        elif not cmds.attributeQuery(dst.split(".")[-1].partition("[")[0], node=dst.split(".")[0], writable=True):
            state = "宛先を書き換えられません"
        elif not cmds.getAttr(dst, settable=True):
            state = "宛先を書き換えられません"
        elif cmds.getAttr(src, type=True) != cmds.getAttr(dst, type=True):
            state = "属性型が一致しません"
        elif source[role]["kind"] == "geometry":
            source_node, target_node = src.split(".")[0], dst.split(".")[0]
            history = [item.getName(full=True) for item in mlib.ls(cmds.listHistory(source_node, pruneDagObjects=False) or [], long=True)]
            if cmds.getAttr(src, type=True) not in ("mesh", "nurbsCurve"):
                state = "未対応の形状型です"
            elif target_node == source_node or target_node in history:
                state = "形状の履歴が循環します"
            else:
                state = "接続可能"
        elif cmds.getAttr(src, type=True) not in ("double", "float", "doubleLinear", "doubleAngle", "bool", "long", "short", "byte"):
            state = "未対応の属性型です"
        else:
            state = "接続可能"
        result[role] = dict(source=src, destination=dst, state=state, incoming=incoming,
                            referenced=bool(dst and cmds.referenceQuery(dst.split(".")[0], isNodeReferenced=True)))
    return result


@undoChunk("mlrigConnectExternalPorts")
def connectExternalPorts(sourceRoot, destinationRoot, roles):
    """明示した役割の外部ポートを、全件の入力状態を検査してから接続する。"""
    rows = inspectExternalPorts(sourceRoot, destinationRoot)
    chosen = [rows[role] for role in dict.fromkeys(roles)]
    edges = {}
    for row in chosen:
        if row["state"] not in ("接続可能", "接続済み"):
            raise ValueError(row["state"])
        previous = edges.setdefault(row["destination"], row["source"])
        if previous != row["source"]:
            raise ValueError("同じ宛先に複数の入力が指定されています")
    added = []
    try:
        for dst, src in edges.items():
            if not cmds.isConnected(src, dst):
                cmds.connectAttr(src, dst)
                added.append((src, dst))
    except RuntimeError:
        for src, dst in reversed(added):
            cmds.disconnectAttr(src, dst)
        raise
    return added


@undoTransaction("mlrigDisconnectExternalPorts")
def disconnectExternalPorts(sourceRoot, destinationRoot, roles):
    """指定した役割の現在の直接接続だけを解除する。"""
    rows = inspectExternalPorts(sourceRoot, destinationRoot)
    edges = set()
    for role in roles:
        row = rows[role]
        if row["state"] != "接続済み":
            raise ValueError("直接接続を確認できません: " + role)
        edges.add((row["source"], row["destination"]))
    for src, dst in sorted(edges):
        cmds.disconnectAttr(src, dst)


@undoChunk("mlrigBakeExternalPorts")
def bakeExternalPorts(sourceRoot, destinationRoot, roles, startFrame, endFrame):
    """選択した直接接続の宛先を指定した整数フレーム範囲で毎コマベイクする。"""
    if type(startFrame) is not int or type(endFrame) is not int or startFrame > endFrame:
        raise ValueError("開始・終了フレームを昇順の整数で指定してください")
    rows = inspectExternalPorts(sourceRoot, destinationRoot)
    destinations = []
    for role in dict.fromkeys(roles):
        row = rows[role]
        dst = row["destination"]
        if row["state"] != "接続済み" or cmds.getAttr(dst, lock=True) or cmds.getAttr(dst, type=True) in ("mesh", "nurbsCurve"):
            raise ValueError("ベイクできる直接接続がありません: " + role)
        if dst not in destinations:
            destinations.append(dst)
    if destinations:
        cmds.bakeResults(destinations, animation="objects", time=(startFrame, endFrame), sampleBy=1,
                         simulation=False, sparseAnimCurveBake=False, shape=False, controlPoints=False)
    return destinations


def showExternalPorts():
    """送り側、受け側の順に選んだリグの外部ポートを確認・接続する。"""
    roots = mlib.ls(selection=True, long=True, type="transform").getNames(full=True)
    if len(roots) != 2:
        raise ValueError("送り側、受け側の順にリグのルートを2つ選択してください")
    window = "mlrigExternalPortEditor"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="外部ポートを接続")
    cmds.columnLayout(adjustableColumn=True)
    cmds.text(label="{} → {}".format(*roots))
    listing = cmds.textScrollList(allowMultiSelection=True)
    roles = []

    def refresh(*_):
        rows = inspectExternalPorts(*roots)
        roles[:] = list(rows)
        cmds.textScrollList(listing, edit=True, removeAll=True)
        for role, row in rows.items():
            text = "{}  {} → {}  {}{}".format(role, row["source"], row["destination"], row["state"],
                                             " (参照編集)" if row["referenced"] else "")
            if row["incoming"]:
                text += "  入力: " + row["incoming"]
            cmds.textScrollList(listing, edit=True, append=text)

    def connect(*_, disconnect=False):
        indices = cmds.textScrollList(listing, query=True, selectIndexedItem=True) or []
        if not indices:
            raise ValueError("接続する役割を選択してください")
        selected = [roles[index - 1] for index in indices]
        if disconnect:
            disconnectExternalPorts(*roots, selected)
        else:
            connectExternalPorts(*roots, roles=selected)
        refresh()

    cmds.button(label="選択した役割を接続", command=connect)
    cmds.button(label="選択した直接接続を解除", command=lambda *_: connect(disconnect=True))
    frames = cmds.intFieldGrp(numberOfFields=2, label="ベイク開始・終了", value1=int(cmds.playbackOptions(query=True, minTime=True)),
                              value2=int(cmds.playbackOptions(query=True, maxTime=True)))

    def bake(*_):
        indices = cmds.textScrollList(listing, query=True, selectIndexedItem=True) or []
        if not indices:
            raise ValueError("ベイクする役割を選択してください")
        bakeExternalPorts(*roots, [roles[index - 1] for index in indices],
                          cmds.intFieldGrp(frames, query=True, value1=True), cmds.intFieldGrp(frames, query=True, value2=True))
        refresh()

    cmds.button(label="選択した接続をベイクして切断", command=bake)
    cmds.button(label="再表示", command=refresh)
    refresh()
    cmds.showWindow(window)
    return window
