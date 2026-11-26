"""配置済みの骨・制御カーブの枝を検査し、別の親のローカル空間へ複製する。"""

from maya import cmds
from maya.api import OpenMaya as om2
from mlib.decorator import undoTransaction


def _address(plug):
    obj = plug.node()
    name = om2.MFnDagNode(obj).fullPathName() if obj.hasFn(om2.MFn.kDagNode) else om2.MFnDependencyNode(obj).name()
    return name, plug.partialName(useLongNames=True, includeNonMandatoryIndices=True, includeInstancedIndices=True, useFullAttributePath=True)


def _inspect(root):
    paths = [root] + (cmds.listRelatives(root, allDescendents=True, fullPath=True) or [])
    inside = set(paths)
    internal, external, blocked = set(), set(), set()
    for path in paths:
        dag = om2.MSelectionList().add(path).getDagPath(0)
        if dag.isInstanced() or cmds.nodeType(path) not in ("joint", "transform", "nurbsCurve"):
            blocked.add(path)
        for plug in om2.MFnDependencyNode(dag.node()).getConnections():
            edges = [(other, plug) for other in plug.connectedTo(True, False)]
            edges.extend((plug, other) for other in plug.connectedTo(False, True))
            for source, dest in edges:
                (src, sa), (dst, da) = _address(source), _address(dest)
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
    copied = cmds.duplicate(root, returnRootsOnly=True, fullPath=True)[0]
    copied = cmds.parent(copied, parent, relative=True)[0]
    cmds.rename(copied, ":" + role)
    result = parent + "|" + role
    for source, destination in internal:
        src, dst = result + source[len(root):], result + destination[len(root):]
        if not cmds.isConnected(src, dst):
            cmds.connectAttr(src, dst)
    cmds.select(result)
    return result


def show():
    """元の枝と差し込み先を選んで依存を表示する。"""
    nodes = cmds.ls(selection=True, long=True, transforms=True) or []
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
