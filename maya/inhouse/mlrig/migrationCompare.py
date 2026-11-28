"""旧セットアップの出力と置換候補の評価値を、現在時刻を変えずに比較する。"""

import math

import mlib
from maya import cmds
from mlib import Transform, getNode
from mlib.maths import Transformation


def peaks(first, second, start, end, step):
    """各サンプルのワールド位置差(cm)、回転差(度)、線形部分の最大成分差を測定する。"""
    if not all(math.isfinite(x) for x in (start, end, step)) or end < start or step <= 0:
        raise ValueError("昇順のフレーム範囲と正の刻みを指定してください")
    nodes = [getNode(n) for n in (first, second)]
    if any(not isinstance(node, Transform) for node in nodes) or nodes[0].getName(full=True) == nodes[1].getName(full=True):
        raise ValueError("異なる2つのトランスフォームを指定してください")
    plugs = [node.getPlug("worldMatrix")[node.getInstanceIndex()] for node in nodes]
    result = {}
    for i in range(math.ceil((end - start) / step) + 1):
        t = min(end, start + i * step)
        a, b = [plug.get(time=t) for plug in plugs]
        qa, qb = Transformation(a).quaternion, Transformation(b).quaternion
        dot = min(1.0, abs(qa.x * qb.x + qa.y * qb.y + qa.z * qb.z + qa.w * qb.w))
        for name, value in (
            ("cm", (a.translate - b.translate).length()),
            ("degrees", math.degrees(2 * math.acos(dot))),
            ("linear", max(abs(a[row * 4 + col] - b[row * 4 + col]) for row in range(3) for col in range(3))),
        ):
            if name not in result or value > result[name][0]:
                result[name] = (value, t)
    return result


def show():
    """選択した旧出力・候補出力の期間内の最大誤差と発生フレームを表示する。"""
    nodes = mlib.ls(selection=True, long=True, transforms=True).getNames(full=True)
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
