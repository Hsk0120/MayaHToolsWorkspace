"""移動する肘の位置から接線限界と基準方向を標準DGで更新する上面デモ。"""

import json
import math
import os
from pathlib import Path

from maya import cmds
from hlib import logger
from verification_video import recordVideo


def _line(name, points, color, parent=None):
    """検証用の色付き方向線を作る。"""
    node = cmds.curve(name=name, degree=1, point=points)
    if parent:
        node = cmds.parent(node, parent, relative=True)[0]
    shape = cmds.listRelatives(node, shapes=True, fullPath=True)[0]
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideRGBColors", True)
    cmds.setAttr(shape + ".overrideColorRGB", *color)
    cmds.setAttr(shape + ".lineWidth", 3)
    return node


def _node(kind, name, **values):
    """標準演算ノードと定数入力を作る。"""
    node = cmds.createNode(kind, name=name)
    for attr, value in values.items():
        cmds.setAttr(node + "." + attr, value)
    return node


def _connect(source, destination):
    """検証DGのアトリビュートを接続する。"""
    cmds.connectAttr(source, destination)


def main():
    """専用GUIで肘移動・左右停止・復帰を録画し、独立計算と照合する。

    根元は半径と余裕の和より外側、XZ平面、無スケールを前提とする。
    保存したリグの補正は標準DGのみ。Pythonは入力アニメーションと検証用。
    """
    if cmds.about(batch=True):
        raise RuntimeError("専用Maya GUIで実行してください。")
    for panel in ("topTangentValidationPanel", "movingTangentPanel"):
        if panel in cmds.getPanel(allPanels=True):
            cmds.deleteUI(panel, panel=True)
    for window in ("topTangentValidationWindow", "movingTangentWindow"):
        if cmds.window(window, exists=True):
            cmds.deleteUI(window, window=True)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")
    radius, gap, length = 3.0, 0.03, 12.0
    root = cmds.createNode("transform", name="movingElbow")
    source = cmds.createNode("transform", name="requestedDirection", parent=root)
    output = cmds.createNode("transform", name="stoppedDirection", parent=root)
    radial = cmds.createNode("transform", name="outwardReference", parent=root)
    _line("bodyCircle", [(radius*math.cos(i*math.pi/48), 0, radius*math.sin(i*math.pi/48))
                         for i in range(97)], (0.65, 0.65, 0.65))
    _line("elbowMarker", [(-0.15, 0, 0), (0.15, 0, 0)], (1, 0.8, 0), root)
    _line("redRequested", [(0, 0, 0), (length, 0, 0)], (1, 0.1, 0.1), source)
    _line("greenStopped", [(0, 0, 0), (length, 0, 0)], (0.1, 1, 0.1), output)
    _line("blueOutward", [(0, 0, 0), (2, 0, 0)], (0.1, 0.65, 1), radial)

    distance = _node("distanceBetween", "centerToElbowDistance")
    _connect(root+".translate", distance+".point2")
    squared = _node("multiplyDivide", "distanceSquared")
    _connect(distance+".distance", squared+".input1X")
    _connect(distance+".distance", squared+".input2X")
    difference = _node("plusMinusAverage", "distanceSquaredMinusRadiusSquared", operation=2)
    _connect(squared+".outputX", difference+".input1D[0]")
    cmds.setAttr(difference+".input1D[1]", (radius+gap)**2)
    tangent_length = _node("multiplyDivide", "tangentLength", operation=3, input2X=0.5)
    _connect(difference+".output1D", tangent_length+".input1X")
    negative = _node("multDoubleLinear", "negativeTangentLength", input2=-1)
    _connect(tangent_length+".outputX", negative+".input1")
    # angleBetween((1,0,0),(-sqrt(d*d-R*R),R,0)) = 180 - asin(R/d)。
    tangent = _node("angleBetween", "dynamicTangentLimit", vector1X=1, vector1Y=0,
                    vector1Z=0, vector2Y=radius+gap, vector2Z=0)
    _connect(negative+".output", tangent+".vector2X")
    limit = _node("unitConversion", "limitDegrees", conversionFactor=180/math.pi)
    _connect(tangent+".angle", limit+".input")
    min_limit = _node("multDoubleLinear", "negativeLimit", input2=-1)
    _connect(limit+".output", min_limit+".input1")

    outward = _node("angleBetween", "outwardUnsignedAngle", vector1X=1, vector1Y=0, vector1Z=0)
    _connect(root+".translate", outward+".vector2")
    outward_degrees = _node("unitConversion", "outwardDegrees", conversionFactor=180/math.pi)
    _connect(outward+".angle", outward_degrees+".input")
    neg_outward = _node("multDoubleLinear", "negativeOutward", input2=-1)
    _connect(outward_degrees+".output", neg_outward+".input1")
    signed = _node("condition", "signedOutwardAngle", operation=2, secondTerm=0)
    _connect(root+".tz", signed+".firstTerm")
    _connect(neg_outward+".output", signed+".colorIfTrueR")
    _connect(outward_degrees+".output", signed+".colorIfFalseR")
    source_deg = _node("unitConversion", "requestedWorldDegrees", conversionFactor=180/math.pi)
    _connect(source+".ry", source_deg+".input")
    relative = _node("plusMinusAverage", "relativeAngle", operation=2)
    _connect(source_deg+".output", relative+".input1D[0]")
    _connect(signed+".outColorR", relative+".input1D[1]")
    # 入力の差を[-180,180]へ戻す。±180度では最近接側が入れ替わる。
    wrap_high = _node("addDoubleLinear", "subtractFullTurn", input2=-360)
    wrap_low = _node("addDoubleLinear", "addFullTurn", input2=360)
    for wrap in (wrap_high, wrap_low):
        _connect(relative+".output1D", wrap+".input1")
    high = _node("condition", "wrapAbove180", operation=2, secondTerm=180)
    _connect(relative+".output1D", high+".firstTerm")
    _connect(wrap_high+".output", high+".colorIfTrueR")
    _connect(relative+".output1D", high+".colorIfFalseR")
    low = _node("condition", "wrapBelowMinus180", operation=4, secondTerm=-180)
    _connect(relative+".output1D", low+".firstTerm")
    _connect(wrap_low+".output", low+".colorIfTrueR")
    _connect(high+".outColorR", low+".colorIfFalseR")
    clamp = _node("clamp", "dynamicAngleStop")
    _connect(low+".outColorR", clamp+".inputR")
    _connect(limit+".output", clamp+".maxR")
    _connect(min_limit+".output", clamp+".minR")
    final = _node("addDoubleLinear", "stoppedWorldDegrees")
    _connect(signed+".outColorR", final+".input1")
    _connect(clamp+".outputR", final+".input2")
    for name, plug, dest in (("outputRadians", final+".output", output+".ry"),
                              ("outwardRadians", signed+".outColorR", radial+".ry")):
        conversion = _node("unitConversion", name, conversionFactor=math.pi/180)
        _connect(plug, conversion+".input")
        _connect(conversion+".output", dest)
    for i, sign in enumerate((-1, 1)):
        boundary = cmds.createNode("transform", name="tangentBoundary{}".format(i), parent=radial)
        _line("boundaryLine{}".format(i), [(0, 0, 0), (7, 0, 0)], (0.5, 0.5, 0.5), boundary)
        conversion = _node("unitConversion", "boundaryRadians{}".format(i), conversionFactor=sign*math.pi/180)
        _connect(limit+".output", conversion+".input")
        _connect(conversion+".output", boundary+".ry")

    camera, shape = cmds.camera(name="movingTangentCamera", orthographic=True)
    cmds.setAttr(camera+".translate", 0, 30, 0)
    cmds.setAttr(camera+".rotate", -90, 0, 0)
    cmds.setAttr(shape+".orthographicWidth", 34)
    window = cmds.window("movingTangentWindow", widthHeight=(1000, 1000))
    pane = cmds.paneLayout(parent=window)
    panel = cmds.modelPanel("movingTangentPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, grid=False, cameras=False, headsUpDisplay=True,
                     selectionHiliteDisplay=False, manipulators=False)
    cmds.showWindow(window)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    for hud in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        cmds.headsUpDisplay(hud, remove=True)
    values = [""]*6
    huds = ["movingFormula{}".format(i) for i in range(6)]
    for i, hud in enumerate(huds):
        cmds.headsUpDisplay(hud, section=5, block=5-i, blockSize="large", dataFontSize="large",
                            command=lambda row=i: values[row])
    # (根元距離, 円周上の位置角, ワールドで指定する尻尾角)。近遠・上下・反対側・復帰。
    poses = [(4.5, 0, 170), (4.5, 0, 170), (3.4, 0, 170), (3.4, 0, 170),
             (7, 0, 170), (7, 0, 170), (4.5, 0, 90), (4.5, 65, 90),
             (4.5, 65, 90), (4.5, -65, -90), (4.5, -65, -90),
             (4.5, -140, -140), (4.5, -140, -140), (4.5, -140, 20),
             (4.5, -140, 20), (4.5, 0, 90)]

    def evaluate(frame):
        """実DGの角度・根元一致・円への非貫通を独立に照合する。"""
        phase = min(frame/36, len(poses)-1)
        index = min(int(phase), len(poses)-2)
        weight = phase-index
        weight = weight*weight*(3-2*weight)
        d, orbit, requested = [a+(b-a)*weight for a, b in zip(poses[index], poses[index+1])]
        x, z = d*math.cos(math.radians(orbit)), -d*math.sin(math.radians(orbit))
        cmds.currentTime(frame+1)
        actual = cmds.getAttr(output+".ry")
        actual_limit = cmds.getAttr(limit+".output")
        actual_relative = cmds.getAttr(low+".outColorR")
        expected_limit = 180-math.degrees(math.asin((radius+gap)/d))
        expected_relative = (requested-orbit+180)%360-180
        expected = orbit+max(-expected_limit, min(expected_limit, expected_relative))
        matrix = cmds.xform(output, query=True, worldSpace=True, matrix=True)
        raw_matrix = cmds.xform(source, query=True, worldSpace=True, matrix=True)

        def hit(m):
            """有限線分と円の最短距離を検証用だけに求める。"""
            t = max(0, min(length, -(x*m[0]+z*m[2])))
            return (x+t*m[0])**2+(z+t*m[2])**2 < radius**2

        raw_hit, safe_hit = hit(raw_matrix), hit(matrix)
        values[:] = [
            "BLUE = outward 0 deg | RED = input | GREEN = output",
            "d=sqrt(x*x+z*z)={:.2f} cm | r+gap=3.03 cm".format(d),
            "limit=180-asin(3.03/d)={:.2f} deg".format(actual_limit),
            "outward={:+.2f} | input world={:+.2f} deg".format(orbit, requested),
            "relative=wrap(input-outward)={:+.2f} deg".format(actual_relative),
            "output=outward+clamp(relative,+/-limit)={:+.2f}".format(actual),
        ]
        for hud in huds:
            cmds.headsUpDisplay(hud, refresh=True)
        return {"frame": frame, "distance_cm": d, "outward_degrees": orbit,
                "requested_degrees": requested, "output_degrees": actual,
                "tangent_limit_degrees": actual_limit, "relative_degrees": actual_relative,
                "raw_intersections": ["bodyCircle"] if raw_hit else [],
                "corrected_intersections": ["bodyCircle"] if safe_hit else [],
                "ok": not safe_hit and abs(actual-expected)<1e-3 and abs(actual_limit-expected_limit)<1e-3
                      and abs(matrix[12]-x)<1e-5 and abs(matrix[14]-z)<1e-5}

    # 保存シーンを開いてタイムラインだけでも再生できるよう入力をキー化する。
    for frame in range((len(poses)-1)*36+1):
        phase = min(frame/36, len(poses)-1)
        index = min(int(phase), len(poses)-2)
        weight = phase-index
        weight = weight*weight*(3-2*weight)
        d, orbit, requested = [a+(b-a)*weight for a, b in zip(poses[index], poses[index+1])]
        cmds.setKeyframe(root, attribute="tx", time=frame+1, value=d*math.cos(math.radians(orbit)))
        cmds.setKeyframe(root, attribute="tz", time=frame+1, value=-d*math.sin(math.radians(orbit)))
        cmds.setKeyframe(source, attribute="ry", time=frame+1, value=requested)
    cmds.playbackOptions(minTime=1, maxTime=(len(poses)-1)*36+1)
    folder = recordVideo("移動する肘: 距離と外向きに追従する接線停止", (len(poses)-1)*36+1,
                         24, panel, evaluate, ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"),
                         width=1000, height=1000)
    if not json.loads((folder/"result.json").read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError("移動根元の検証に失敗: {}".format(folder))
    cmds.file(rename=str(folder/"moving-tangent-stop.ma"))
    cmds.file(save=True, type="mayaAscii")
    (Path(__file__).resolve().parents[1]/".maya-output/verification/latest-moving-tangent.json").write_text(
        json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
    logger.info("移動する肘の検証を保存しました: {}".format(folder))


if __name__ == "__main__":
    main()
