"""標準multMatrix追従の親逆マトリクスを除いた場合の結果を照合する。"""

from maya import cmds
from mlib.maths import Matrix


def compare(target):
    """現在時刻での実ワールド値と、末尾の親逆入力を恒等とした予測値を返す。"""
    parent = cmds.listRelatives(target, parent=True, fullPath=True) or []
    opm = target + ".offsetParentMatrix"
    source = cmds.connectionInfo(opm, sourceFromDestination=True)
    if not parent or not cmds.getAttr(target + ".inheritsTransform") or not source.endswith(".matrixSum"):
        raise ValueError("親を継承しmultMatrixで追従している対象を選択してください")
    graph = source.rsplit(".", 1)[0]
    if cmds.nodeType(graph) != "multMatrix":
        raise ValueError("標準multMatrixに対応しています")
    inputs = graph + ".matrixIn"
    indices = sorted(cmds.getAttr(inputs, multiIndices=True) or [])
    if not indices or not cmds.isConnected(parent[0] + ".worldInverseMatrix[0]", "{}[{}]".format(inputs, indices[-1])):
        raise ValueError("末尾の入力が実親の逆マトリクスではありません")
    if any(len(cmds.ls(node, allPaths=True, long=True) or []) != 1 for node in (target, parent[0])):
        raise ValueError("インスタンスには対応していません")
    predicted = Matrix(cmds.getAttr(target + ".matrix"))
    for index in indices[:-1]:
        predicted *= Matrix(cmds.getAttr("{}[{}]".format(inputs, index)))
    predicted *= Matrix(cmds.getAttr(parent[0] + ".worldMatrix[0]"))
    return tuple(cmds.getAttr(target + ".worldMatrix[0]")), tuple(predicted)


def show():
    """選択した追従先の比較結果を表示する。"""
    selected = cmds.ls(selection=True, long=True, type="transform") or []
    if len(selected) != 1:
        raise ValueError("追従先を1つ選んでください")
    actual, predicted = compare(selected[0])
    window = "mlrigLocalFollowInspection"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="ローカル追従への変換診断")
    cmds.columnLayout(adjustableColumn=True)
    cmds.text(label=selected[0])
    for label, values in (("現在", actual), ("親逆入力を除いた予測", predicted)):
        cmds.text(label=label)
        for index in range(0, 16, 4):
            cmds.text(label="  ".join("{:.6g}".format(value) for value in values[index:index + 4]))
    cmds.text(label="最大要素差 {:.6g}".format(max(abs(a - b) for a, b in zip(actual, predicted))))
    cmds.showWindow(window)
    return window
