"""リグ階層内のキーと色の照会、車輪の役割別ベイク。"""

import math

from maya import cmds
import mlib
from mlib.decorator import undoTransaction


def _transforms(root, descendants):
    """選択したパスを基準に、インスタンス先を混同せず子孫を列挙する。"""
    paths = cmds.ls(root, long=True, objectsOnly=True) or []
    if len(paths) != 1 or not cmds.objectType(paths[0], isAType="transform"):
        raise ValueError("Choose one transform path.")
    paths = [paths[0]]
    if descendants:
        for node in paths:
            paths.extend(child for child in cmds.listRelatives(node, children=True, fullPath=True) or []
                         if cmds.objectType(child, isAType="transform"))
    return paths


def _curveColors(node):
    """直下の制御カーブに適用される色をRGBで返す。"""
    colors = []
    for shape in cmds.listRelatives(node, shapes=True, noIntermediate=True, type="nurbsCurve", fullPath=True) or []:
        dag = mlib.getNode(shape)
        path = shape
        color = None
        while path:
            value = mlib.getNode(path).getColor()
            if value is not None:
                if isinstance(value, tuple):
                    color = value
                elif value:
                    color = cmds.colorIndex(value, query=True) or value
                break
            path = path.rpartition("|")[0]
        if color is None:
            color = dag.getDrawColor(kind="dormant")
        colors.append(color if isinstance(color, int) else tuple(color[:3]))
    return colors


def controlsByColor(sample, root, tolerance=0.0):
    """指定ルートの制御カーブを、見本とのRGBユークリッド距離で照会する。"""
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Enter a finite, nonnegative RGB distance.")
    colors = _curveColors(_transforms(sample, False)[0])
    if not colors:
        raise ValueError("The sample must have a NURBS control curve.")
    def matches(source, target):
        # GUIの色パレットが無いmayapyでは、番号色は同じ番号同士で照合する。
        if isinstance(source, int) or isinstance(target, int):
            return source == target
        return sum((a - b) ** 2 for a, b in zip(source, target)) <= tolerance ** 2

    return [node for node in _transforms(root, True)
            if any(matches(source, target) for source in colors for target in _curveColors(node))]


def previewKeyRemoval(root, start, end, *, descendants=True, published=False):
    """範囲内のキーを持つチャンネルと安全に単独編集できる時間曲線を返す。"""
    if not all(math.isfinite(value) for value in (start, end)) or start > end:
        raise ValueError("Invalid frame range.")
    nodes = _transforms(root, descendants and not published)
    if published:
        # 公開ポートの照会だけがmlrigを必要とする。
        from mlrig import publishedChannels
        ports = publishedChannels.getPorts(nodes[0])
        found, missing = publishedChannels.resolveChannels(nodes[0], {
            role: (port["path"], port["attribute"]) for role, port in ports.items()})
        if missing:
            raise ValueError("Missing published channels: " + ", ".join(missing))
        plugs = sorted(set(found.values()))
    else:
        plugs = [node + "." + attr for node in nodes for attr in (cmds.listAttr(node, keyable=True, scalar=True) or [])]
    rows = []
    for plug in plugs:
        source = cmds.connectionInfo(plug, sourceFromDestination=True)
        if not source:
            continue
        curve = source.split(".", 1)[0]
        if cmds.nodeType(curve) not in ("animCurveTA", "animCurveTL", "animCurveTT", "animCurveTU"):
            continue
        times = cmds.keyframe(curve, query=True, time=(start, end), timeChange=True) or []
        if times:
            shared = len(cmds.connectionInfo(source, destinationFromSource=True) or []) != 1
            locked = cmds.lockNode(curve, query=True, lock=True)[0] or cmds.getAttr(plug, lock=True)
            protected = shared or locked or cmds.referenceQuery(curve, isNodeReferenced=True)
            rows.append((plug, curve, tuple(times), protected))
    return rows


@undoTransaction("animBarRemoveScopedKeys")
def removePreviewedKeys(root, start, end, rows, **scope):
    """表示後に変化があれば中止し、編集可能な曲線の範囲内のキーだけを除く。"""
    current = previewKeyRemoval(root, start, end, **scope)
    if rows != current:
        raise ValueError("The preview changed. Preview the keys again.")
    for _, curve, _, protected in rows:
        if not protected:
            cmds.cutKey(curve, time=(start, end), clear=True, animation="objects")


@undoTransaction("animBarBakeWheelChannels")
def bakeWheelChannels(wheel, start, end, *, axle=None, roll=True, yaw=True, heave=True):
    """車輪のX回転と、車軸のY回転・移動のうち指定したローカル成分をベイクする。"""
    wheel = _transforms(wheel, False)[0]
    axle = _transforms(axle, False)[0] if axle else wheel
    if axle != wheel and not wheel.startswith(axle + "|"):
        raise ValueError("Choose an axle above the wheel in the same hierarchy.")
    if not all(math.isfinite(value) for value in (start, end)) or start > end:
        raise ValueError("Invalid frame range.")
    plugs = ([wheel + ".rotateX"] if roll else []) + ([axle + ".rotateY"] if yaw else [])
    if heave:
        plugs.extend(axle + ".translate" + axis for axis in "XYZ")
    if not plugs or any(cmds.getAttr(plug, lock=True) for plug in plugs):
        raise ValueError("Choose at least one unlocked wheel channel.")
    driven = {}
    frames = [start + offset for offset in range(math.floor(end - start) + 1)]
    if frames[-1] != end:
        frames.append(end)
    for plug in plugs:
        node, attr = plug.split(".", 1)
        if cmds.connectionInfo(plug, isDestination=True):
            driven.setdefault(node, []).append(attr)
        else:
            value = cmds.getAttr(plug)
            for frame in frames:
                cmds.setKeyframe(plug, time=frame, value=value)
    for node, attrs in driven.items():
        cmds.bakeResults(node, attribute=attrs, time=(start, end), sampleBy=1, preserveOutsideKeys=True,
                         hierarchy="none", shape=False, simulation=False)
    if any(not cmds.keyframe(plug, query=True, time=(start, end), keyframeCount=True) for plug in plugs):
        raise RuntimeError("Maya did not bake every requested channel.")
    return plugs
