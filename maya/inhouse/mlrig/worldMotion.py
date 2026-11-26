"""既存リグの1関節の移動・回転を別リグの1関節へ整数フレームで転写する。"""

from maya import cmds
from mlib.decorator import undoTransaction


@undoTransaction("mlrigTransferWorldMotion")
def transfer(source, target, first, last):
    """両者のワールドマトリクスが一致する移動・回転キーを指定範囲に作成する。"""
    if type(first) is not int or type(last) is not int or first > last:
        raise ValueError("開始・終了に昇順の整数フレームを指定してください")
    src, dst = [cmds.ls(n, long=True, transforms=True) or [] for n in (source, target)]
    if len(src) != 1 or len(dst) != 1:
        raise ValueError("送り側と受け側を一意に指定してください")
    source, target = src[0], dst[0]
    if source == target or source.startswith(target + "|") or target.startswith(source + "|"):
        raise ValueError("独立した2つの階層から指定してください")
    attrs = [p + axis for p in ("translate", "rotate") for axis in "XYZ"]
    for attr in attrs:
        plug = target + "." + attr
        driver = cmds.connectionInfo(plug, sourceFromDestination=True)
        if cmds.getAttr(plug, lock=True) or (driver and (
            not cmds.nodeType(driver.split(".")[0]).startswith("animCurveT")
            or len(cmds.connectionInfo(driver, destinationFromSource=True) or []) != 1
        )):
            raise ValueError("宛先にロック、共有カーブまたは非対応の入力があります: " + plug)
    # 現在時刻だけを写すduplicateでは、動くoffsetParentMatrix等の入力を再現できない。
    for attr in ("jointOrient", "rotateAxis", "rotateOrder", "scale", "offsetParentMatrix", "rotatePivot", "rotatePivotTranslate"):
        plug = target + "." + attr
        if cmds.objExists(plug) and cmds.listConnections(plug, source=True, destination=False):
            raise ValueError("宛先の姿勢設定に接続があります: " + plug)
    temp = cmds.duplicate(target, parentOnly=True, name="worldMotionSample#", returnRootsOnly=True)[0]
    constraint = cmds.parentConstraint(source, temp, maintainOffset=False)[0]
    samples = []
    for frame in range(first, last + 1):
        expected = cmds.getAttr(source + ".worldMatrix[0]", time=frame)
        actual = cmds.getAttr(temp + ".worldMatrix[0]", time=frame)
        if max(abs(a - b) for a, b in zip(expected, actual)) > 1e-5:
            raise ValueError("移動・回転で宛先の姿勢を再現できません: {}F".format(frame))
        samples.append((expected, [cmds.getAttr(temp + "." + attr, time=frame) for attr in attrs]))
    cmds.delete(constraint, temp)
    cmds.cutKey(target, attribute=attrs, time=(first, last), clear=True)
    for frame, (_, values) in enumerate(samples, first):
        for attr, value in zip(attrs, values):
            cmds.setKeyframe(target, attribute=attr, time=frame, value=value, inTangentType="linear", outTangentType="linear")
    for frame, (expected, _) in enumerate(samples, first):
        actual = cmds.getAttr(target + ".worldMatrix[0]", time=frame)
        if max(abs(a - b) for a, b in zip(expected, actual)) > 1e-5:
            raise ValueError("宛先の評価が転写結果と一致しません: {}F".format(frame))
    return len(samples)


def show():
    """選択した旧・新コントローラーの転写範囲を指定する。"""
    nodes = cmds.ls(selection=True, long=True, transforms=True) or []
    if len(nodes) != 2:
        raise ValueError("旧・新コントローラーの順に選択してください")
    window = "mlrigWorldMotion"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    cmds.window(window, title="ワールド軌跡の転写")
    cmds.columnLayout(adjustableColumn=True)
    cmds.text(label=" → ".join(nodes))
    fields = cmds.intFieldGrp(label="開始・終了", numberOfFields=2, value1=int(cmds.playbackOptions(query=True, minTime=True)),
                              value2=int(cmds.playbackOptions(query=True, maxTime=True)))
    cmds.button(label="指定範囲の移動・回転を転写", command=lambda *_: transfer(*nodes, cmds.intFieldGrp(fields, query=True, value1=True),
                                                             cmds.intFieldGrp(fields, query=True, value2=True)))
    cmds.showWindow(window)
    return window
