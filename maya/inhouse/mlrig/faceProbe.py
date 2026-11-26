"""顔の駆動値を一時的に変え、登録した全頂点のワールド変位を調べる。"""

import math

from maya import cmds
from mlib.decorator import undoTransaction


@undoTransaction("mlrigFaceProbe")
def measure(units):
    """各ユニット単独と全ユニット同時の頂点変位をシーン単位で測定する。"""
    if not units or cmds.autoKeyframe(query=True, state=True):
        raise ValueError("ユニットを登録し、自動キーを無効にしてください")
    saved = {}
    vertices = []
    for plug, (value, points) in units.items():
        if not math.isfinite(value) or not cmds.objExists(plug) or cmds.getAttr(plug, type=True) not in ("double", "float", "doubleAngle", "doubleLinear"):
            raise ValueError("数値の駆動チャンネルと有限の値を指定してください")
        if cmds.connectionInfo(plug, isDestination=True) or not cmds.getAttr(plug, settable=True):
            raise ValueError("接続・キー・ロックのない駆動値を指定してください: " + plug)
        if not points or any(".vtx[" not in p or not cmds.objExists(p) for p in points):
            raise ValueError("測定する頂点を指定してください")
        saved[plug] = cmds.getAttr(plug)
        vertices.extend(points)
    baseline = {p: cmds.pointPosition(p, world=True) for p in dict.fromkeys(vertices)}
    groups = [(plug,) for plug in units]
    if len(units) > 1:
        groups.append(tuple(units))
    result = {}
    for group in groups:
        try:
            for plug in group:
                cmds.setAttr(plug, units[plug][0])
            result[group] = {p: math.sqrt(sum((v - b) ** 2 for v, b in zip(cmds.pointPosition(p, world=True), before))) for p, before in baseline.items()}
        finally:
            for plug in group:
                cmds.setAttr(plug, saved[plug])
    return result


def show():
    """駆動チャンネル、試験値と選択頂点を登録するウィンドウを表示する。"""
    window = "mlrigFaceProbe"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="顔ユニットの変位測定")
    cmds.columnLayout(adjustableColumn=True)
    field = cmds.textFieldGrp(label="駆動チャンネル")
    value = cmds.floatFieldGrp(label="試験値", value1=1)
    units = {}
    log = cmds.scrollField(editable=False, height=180)

    def register(*unused):
        plug = cmds.textFieldGrp(field, query=True, text=True).strip()
        points = cmds.filterExpand(selectionMask=31, expand=True, fullPath=True) or []
        if not points or not cmds.objExists(plug):
            raise ValueError("駆動チャンネルを入力し、測定する頂点を選択してください")
        units[plug] = (cmds.floatFieldGrp(value, query=True, value1=True), points)
        cmds.scrollField(log, edit=True, text="\n".join("{} = {} ({}頂点)".format(p, v, len(pts)) for p, (v, pts) in units.items()))

    def run(*unused):
        rows = []
        for group, values in measure(units).items():
            rows.append(" + ".join(group))
            rows.extend("{}  {:.6g} {}".format(p, d, cmds.currentUnit(query=True, linear=True)) for p, d in values.items())
        cmds.scrollField(log, edit=True, text="\n".join(rows))

    cmds.button(label="選択頂点と試験値を登録・更新", command=register)
    cmds.button(label="単独・複合で測定", command=run)
    cmds.showWindow(window)
    return window
