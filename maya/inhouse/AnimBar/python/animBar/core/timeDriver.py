"""選んだ時間カーブに共通の編集可能な時間入力を付け外しする。"""

import maya.cmds as cmds
from mlib.decorator import undoTransaction

_MEMBERS = "animBarTimeMembers"
_EXPLICIT = "animBarExplicitTime"


@undoTransaction("animBarAttachTimeDriver")
def attachSelected():
    """選んだ時間駆動カーブを、再生範囲で等速の時間カーブにつなぐ。"""
    curves = cmds.ls(selection=True, long=True) or []
    if not curves or cmds.getAttr("time1.enableTimewarp"):
        raise ValueError("Select time animation curves in a scene without a time warp.")
    inputs = []
    for curve in curves:
        if cmds.nodeType(curve) not in ("animCurveTA", "animCurveTL", "animCurveTU"):
            raise ValueError("Select only time-driven angle, distance or numeric curves.")
        source = cmds.connectionInfo(curve + ".input", sourceFromDestination=True)
        destinations = cmds.listConnections(curve + ".output", plugs=True, destination=True, source=False) or []
        if source not in ("", "time1.outTime") or cmds.getAttr(curve + ".input", lock=True):
            raise ValueError("Time input is locked or already driven: " + curve)
        if not destinations or any(cmds.nodeType(plug.split(".")[0]).startswith(("animBlendNode", "pairBlend")) for plug in destinations):
            raise ValueError("Select directly connected animation curves outside layers: " + curve)
        inputs.append(source)
    start = cmds.playbackOptions(query=True, minTime=True)
    end = cmds.playbackOptions(query=True, maxTime=True)
    if end <= start:
        raise ValueError("Choose a playback range spanning two frames.")
    driver = cmds.createNode("animCurveTT", name="animBarTimeDriver#", skipSelect=True)
    cmds.addAttr(driver, longName=_MEMBERS, attributeType="message", multi=True)
    cmds.addAttr(driver, longName=_EXPLICIT, attributeType="bool", multi=True)
    cmds.connectAttr("time1.outTime", driver + ".input")
    for frame in (start, end):
        cmds.setKeyframe(driver, time=frame, value=frame, inTangentType="linear", outTangentType="linear")
    cmds.setInfinity(driver, preInfinite="linear", postInfinite="linear")
    for index, (curve, source) in enumerate(zip(curves, inputs)):
        cmds.connectAttr(curve + ".message", f"{driver}.{_MEMBERS}[{index}]")
        cmds.setAttr(f"{driver}.{_EXPLICIT}[{index}]", bool(source))
        cmds.connectAttr(driver + ".output", curve + ".input", force=True)
    cmds.select(driver, replace=True)
    return driver


@undoTransaction("animBarDetachTimeDriver")
def detachSelected():
    """選択した時間ドライバーの接続を検査し、全カーブの元の時間入力を戻す。"""
    selected = cmds.ls(selection=True) or []
    if len(selected) != 1 or cmds.nodeType(selected[0]) != "animCurveTT":
        raise ValueError("Select one Anim Bar time driver.")
    driver = selected[0]
    if not all(cmds.attributeQuery(attr, node=driver, exists=True) for attr in (_MEMBERS, _EXPLICIT)):
        raise ValueError("Select a time driver created by Anim Bar.")
    output = driver + ".output"
    members = {}
    for index in cmds.getAttr(driver + "." + _MEMBERS, multiIndices=True) or []:
        curves = cmds.listConnections(f"{driver}.{_MEMBERS}[{index}]", source=True, destination=False) or []
        if len(curves) != 1:
            raise ValueError("A recorded time curve is missing.")
        members[curves[0] + ".input"] = cmds.getAttr(f"{driver}.{_EXPLICIT}[{index}]")
    destinations = cmds.listConnections(output, plugs=True, source=False, destination=True) or []
    if set(destinations) != set(members):
        raise ValueError("Time driver connections have changed.")
    for plug, explicit in members.items():
        cmds.disconnectAttr(output, plug)
        if explicit:
            cmds.connectAttr("time1.outTime", plug)
    cmds.delete(driver)
