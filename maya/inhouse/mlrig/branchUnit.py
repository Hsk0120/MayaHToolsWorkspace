"""配置済みの骨・制御カーブの枝を検査し、別の親のローカル空間へ複製する。"""

import re
import tempfile
from pathlib import Path

import mlib
from maya import cmds
from mlib import getNode
from mlib.decorator import undoTransaction


def _inspect(root):
    paths = [root] + (cmds.listRelatives(root, allDescendents=True, fullPath=True) or [])
    inside = set(paths)
    internal, external, blocked = set(), set(), set()
    for path in paths:
        dag = getNode(path)
        if dag.isInstanced() or cmds.nodeType(path) not in ("joint", "transform", "nurbsCurve"):
            blocked.add(path)
        for incoming in (True, False):
            pairs = dag.getConnections(source=incoming, destination=not incoming, asPair=True)
            for own, other in pairs:
                source, dest = (other, own) if incoming else (own, other)
                src, dst = source.getNode().getName(full=True), dest.getNode().getName(full=True)
                sa, da = (plug.mplug().partialName(useLongNames=True, includeNonMandatoryIndices=True, includeInstancedIndices=True, useFullAttributePath=True)
                          for plug in (source, dest))
                edge = (src + "." + sa, dst + "." + da)
                if src in inside and dst in inside:
                    internal.add(edge)
                else:
                    external.add(edge)
                    if dst in inside and not (dst == root and da == "inverseScale" and sa == "scale" and src == root.rpartition("|")[0]):
                        blocked.add(" → ".join(edge))
    return sorted(internal), sorted(external), sorted(blocked)


@undoTransaction("mlrigInsertBranchUnit")
def insert(root, parent):
    """外部入力がない枝を複製し、役割名・内部接続とローカル姿勢を維持する。"""
    if parent == root or parent.startswith(root + "|") or not cmds.objectType(parent, isAType="transform"):
        raise ValueError("枝の外にある親を指定してください")
    internal, _, blocked = _inspect(root)
    if blocked:
        raise ValueError("解決が必要な入力または種類: " + ", ".join(blocked))
    role = root.rpartition("|")[2]
    if cmds.objExists(parent + "|" + role):
        raise ValueError("差し込み先に同名の役割があります")
    copied = mlib.duplicate(root, returnRootsOnly=True, fullPath=True).getName(full=True)
    copied = cmds.parent(copied, parent, relative=True)[0]
    cmds.rename(copied, ":" + role)
    result = parent + "|" + role
    for source, destination in internal:
        src, dst = result + source[len(root):], result + destination[len(root):]
        if not cmds.isConnected(src, dst):
            cmds.connectAttr(src, dst)
    mlib.select(result)
    return result


@undoTransaction("mlrigExportBranch")
def exportBranch(root, path):
    """検査・複製した骨と制御カーブを単独のMayaバイナリへ保存する。"""
    path = Path(path)
    if path.suffix.lower() != ".mb":
        raise ValueError("保存先には.mbファイルを指定してください")
    root, = [item.getName(full=True) for item in mlib.ls(root, long=True)]
    saved = [item.getName(full=True) for item in mlib.ls(selection=True, long=True)]
    holder = mlib.createNode("transform", name="branchExport#").getName()
    try:
        copy = insert(root, [item.getName(full=True) for item in mlib.ls(holder, long=True)][0])
        copy = cmds.parent(copy, world=True, relative=True)[0]
        try:
            cmds.addAttr(copy, longName="mlrigBranchRootName", dataType="string")
            cmds.setAttr(copy + ".mlrigBranchRootName", root.rsplit("|", 1)[-1].rsplit(":", 1)[-1], type="string")
            mlib.select(copy, replace=True)
            with tempfile.TemporaryDirectory(dir=str(path.parent)) as directory:
                temp = Path(directory) / path.name
                cmds.file(str(temp), exportSelected=True, type="mayaBinary", channels=False, constraints=False, expressions=False, constructionHistory=False)
                temp.replace(path)
        finally:
            mlib.delete(copy)
    finally:
        mlib.delete(holder)
        mlib.select(saved, replace=True) if saved else mlib.select(clear=True)


@undoTransaction("mlrigImportBranch")
def importBranch(parent, path, namespace):
    """未使用の名前空間に読み込み、単一ルートを選択した親に差し込む。"""
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z_0-9]*", namespace) or cmds.namespace(exists=":" + namespace):
        raise ValueError("未使用の名前空間を指定してください")
    if not cmds.objectType(parent, isAType="transform"):
        raise ValueError("差し込み先の親を指定してください")
    imported = cmds.file(str(path), i=True, type="mayaBinary", namespace=":" + namespace, returnNewNodes=True, executeScriptNodes=False)
    roots = mlib.ls(imported, assemblies=True, long=True).getNames(full=True)
    if len(roots) != 1:
        raise ValueError("単一の枝を含むファイルを指定してください")
    _, _, blocked = _inspect(roots[0])
    if blocked:
        raise ValueError("未解決の枝の依存: " + ", ".join(blocked))
    root = roots[0]
    if not cmds.objExists(root + ".mlrigBranchRootName"):
        raise ValueError("サブリグ部品の識別情報がありません")
    name = cmds.getAttr(root + ".mlrigBranchRootName")
    cmds.deleteAttr(root + ".mlrigBranchRootName")
    root = cmds.rename(root, ":" + namespace + ":" + name)
    return cmds.parent(root, parent, relative=True)[0]


def showLibrary():
    """枝の書き出しと別シーンへの読み込みを行う。"""
    win = "mlrigBranchLibrary"
    if cmds.window(win, exists=True):
        cmds.deleteUI(win)
    cmds.window(win, title="サブリグ部品の保存・読込")
    cmds.columnLayout(adjustableColumn=True)
    ns = cmds.textFieldGrp(label="読込先の名前空間", text="branch01")
    def browse(save):
        nodes = mlib.ls(selection=True, long=True, transforms=True).getNames(full=True)
        if len(nodes) != 1:
            raise ValueError("保存する枝または読込先の親を1つ選択してください")
        paths = cmds.fileDialog2(fileFilter="Maya binary (*.mb)", fileMode=0 if save else 1) or []
        if paths:
            if save:
                exportBranch(nodes[0], paths[0])
            else:
                importBranch(nodes[0], paths[0], cmds.textFieldGrp(ns, query=True, text=True))
    cmds.button(label="選択した枝を保存", command=lambda *_: browse(True))
    cmds.button(label="選択した親の下へ読み込む", command=lambda *_: browse(False))
    cmds.showWindow(win)


def show():
    """元の枝と差し込み先を選んで依存を表示する。"""
    nodes = mlib.ls(selection=True, long=True, transforms=True).getNames(full=True)
    if len(nodes) != 2:
        raise ValueError("元の枝と差し込み先の親を順に選択してください")
    _, external, blocked = _inspect(nodes[0])
    window = "mlrigBranchUnit"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="サブリグの枝を複製")
    cmds.columnLayout(adjustableColumn=True)
    cmds.scrollField(editable=False, text="外部接続\n" + "\n".join(" → ".join(edge) for edge in external) + "\n要解決\n" + "\n".join(blocked))
    cmds.button(label="選択した親へ差し込む", enable=not blocked, command=lambda *_: insert(*nodes))
    cmds.showWindow(window)
    return window
