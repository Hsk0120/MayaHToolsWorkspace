"""旧セットアップの出力と置換候補の評価値を、現在時刻を変えずに比較する。"""

import math

from maya import cmds
from maya.api import OpenMaya as om2


def peaks(first, second, start, end, step):
    """各サンプルのワールド位置差(cm)、回転差(度)、線形部分の最大成分差を測定する。"""
    if not all(math.isfinite(x) for x in (start, end, step)) or end < start or step <= 0:
        raise ValueError("昇順のフレーム範囲と正の刻みを指定してください")
    paths = [om2.MSelectionList().add(n).getDagPath(0) for n in (first, second)]
    if paths[0] == paths[1] or any(not p.node().hasFn(om2.MFn.kTransform) for p in paths):
        raise ValueError("異なる2つのトランスフォームを指定してください")
    plugs = [om2.MSelectionList().add("{}.worldMatrix[{}]".format(p.fullPathName(), p.instanceNumber())).getPlug(0) for p in paths]
    result = {}
    for i in range(math.ceil((end - start) / step) + 1):
        t = min(end, start + i * step)
        ctx = om2.MDGContext(om2.MTime(t, om2.MTime.uiUnit()))
        a, b = [om2.MFnMatrixData(p.asMObject(ctx)).matrix() for p in plugs]
        qa, qb = [om2.MTransformationMatrix(m).rotation(asQuaternion=True) for m in (a, b)]
        dot = min(1.0, abs(qa.x * qb.x + qa.y * qb.y + qa.z * qb.z + qa.w * qb.w))
        for name, value in (
            ("cm", (om2.MPoint() * a).distanceTo(om2.MPoint() * b)),
            ("degrees", math.degrees(2 * math.acos(dot))),
            ("linear", max(abs(a[row * 4 + col] - b[row * 4 + col]) for row in range(3) for col in range(3))),
        ):
            if name not in result or value > result[name][0]:
                result[name] = (value, t)
    return result


def show():
    """選択した旧出力・候補出力の期間内の最大誤差と発生フレームを表示する。"""
    nodes = cmds.ls(selection=True, long=True, transforms=True) or []
    if len(nodes) != 2:
        raise ValueError("旧出力と置換候補を順に選択してください")
    window = "mlrigMigrationCompare"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="旧出力と置換候補を比較")
    cmds.columnLayout(adjustableColumn=True)
    times = cmds.floatFieldGrp(
        label="開始 / 終了 / 刻み",
        numberOfFields=3,
        value1=cmds.playbackOptions(query=True, minTime=True),
        value2=cmds.playbackOptions(query=True, maxTime=True),
        value3=1,
    )
    report = cmds.scrollField(editable=False, height=100)

    def sample(*_):
        values = peaks(*nodes, *cmds.floatFieldGrp(times, query=True, value=True)[:3])
        labels = {"cm": "位置差(cm)", "degrees": "回転差(度)", "linear": "回転・スケール・シアーを含む3×3成分差"}
        cmds.scrollField(report, edit=True, text="\n".join("{}  {:.6g}  @ {:g}F".format(labels[k], v, t) for k, (v, t) in values.items()))

    cmds.button(label="最大差を測定", command=sample)
    cmds.showWindow(window)
    return window
