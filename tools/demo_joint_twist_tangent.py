"""腕ローカルX軸だけで尻尾ジョイントを回し、球近似の体を避ける検証。"""

import json
import math
import os
from pathlib import Path

from maya import cmds
from hlib import logger
from demo_top_view_moving_tangent import _line, _node, _connect
from verification_video import recordVideo


def _sum(name, plugs, constants=(), subtract=False):
    """検証用の加減算を標準DGで作る。"""
    node = _node("plusMinusAverage", name, operation=2 if subtract else 1)
    for i, plug in enumerate(plugs):
        _connect(plug, node+".input1D[{}]".format(i))
    for i, value in enumerate(constants, len(plugs)):
        cmds.setAttr(node+".input1D[{}]".format(i), value)
    return node+".output1D"


def _multiply(name, a, b=None, constant=1):
    """検証用の積を標準DGで作る。"""
    node = _node("multDoubleLinear", name, input2=constant)
    _connect(a, node+".input1")
    if b:
        _connect(b, node+".input2")
    return node+".output"


def _condition(name, first, second, yes, no, operation=2):
    """検証用の比較分岐を標準DGで作る。"""
    node = _node("condition", name, operation=operation, secondTerm=second)
    _connect(first, node+".firstTerm")
    for plug, value in (("colorIfTrueR", yes), ("colorIfFalseR", no)):
        if isinstance(value, str):
            _connect(value, node+"."+plug)
        else:
            cmds.setAttr(node+"."+plug, value)
    return node+".outColorR"


def _sqrt(name, plug):
    """非負値の平方根を標準DGで求める。"""
    node = _node("multiplyDivide", name, operation=3, input2X=0.5)
    _connect(plug, node+".input1X")
    return node+".outputX"


def _degrees(name, plug):
    """角度アトリビュートを演算用の度へ変換する。"""
    node = _node("unitConversion", name, conversionFactor=180/math.pi)
    _connect(plug, node+".input")
    return node+".output"


def main(*, topView=False, fixedElbowSide=False, reproduceFlip=False,
         continuousElbowSide=False, maximumAngle=60.0, largeMotion=False):
    """専用GUIで移動・腕傾斜・1軸停止・非接触時の復帰を実録画する。

    体は固定半径の球、根元は球の外側、尻尾は腕Xに垂直な直線とする。
    補正ジョイントのrotateY/ZとjointOrientはゼロのまま保持する。

    Args:
        topView (bool): Trueなら上面の固定正投影で録画する。既定は斜め表示。
        fixedElbowSide (bool): Trueなら初期の肘ガイド側へ回避接線を固定する。
        reproduceFlip (bool): 固定側の逆境界を入力・距離・位置・傾斜で横切る。
        continuousElbowSide (bool): 肘側の負回転範囲を連続制限し、貫通を許容する。
        maximumAngle (float): 最大負回転量。度、0より大きく180未満。
        largeMotion (bool): 初期姿勢から安全・大回転・上限貫通・復帰を順に見せる。
    """
    if reproduceFlip and not fixedElbowSide:
        raise ValueError("reproduceFlipにはfixedElbowSide=Trueが必要です。")
    if continuousElbowSide and (not fixedElbowSide or not 0<maximumAngle<180):
        raise ValueError("連続制限にはfixedElbowSide=Trueと0<maximumAngle<180が必要です。")
    if largeMotion and not continuousElbowSide:
        raise ValueError("largeMotionにはcontinuousElbowSide=Trueが必要です。")
    if cmds.about(batch=True):
        raise RuntimeError("専用Maya GUIで実行してください。")
    for panel in ("movingTangentPanel", "jointTwistPanel"):
        if panel in cmds.getPanel(allPanels=True):
            cmds.deleteUI(panel, panel=True)
    for window in ("movingTangentWindow", "jointTwistWindow"):
        if cmds.window(window, exists=True):
            cmds.deleteUI(window, window=True)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")
    radius, gap, length = 3.0, 0.03, 12.0
    sphere = cmds.polySphere(name="bodySphereProxy", radius=radius, subdivisionsX=40,
                            subdivisionsY=24, constructionHistory=False)[0]
    material = cmds.shadingNode("lambert", asShader=True, name="bodyProxyMaterial")
    cmds.setAttr(material+".color", 0.18, 0.22, 0.28, type="double3")
    cmds.setAttr(material+".transparency", 0.55, 0.55, 0.55, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
    _connect(material+".outColor", group+".surfaceShader")
    cmds.sets(sphere, edit=True, forceElement=group)
    arm = cmds.createNode("joint", name="armTwistAxis_JNT")
    cmds.setAttr(arm+".jointOrientZ", 90)
    cmds.setAttr(arm+".tx", 4.5)
    tip = cmds.createNode("joint", name="armAxisTip_JNT", parent=arm)
    cmds.setAttr(tip+".tx", 3)
    for joint in (arm, tip):
        cmds.setAttr(joint+".radius", 0.15)
        cmds.setAttr(joint+".overrideEnabled", True)
        cmds.setAttr(joint+".overrideRGBColors", True)
        cmds.setAttr(joint+".overrideColorRGB", 0.1, 0.65, 1)
    source = cmds.createNode("joint", name="tailRequested_JNT", parent=arm)
    output = cmds.createNode("joint", name="tailCorrected_JNT", parent=arm)
    for node, color in ((source, (1, 0.1, 0.1)), (output, (0.1, 1, 0.1))):
        endpoint = cmds.createNode("joint", name=node.replace("_JNT", "Tip_JNT"), parent=node)
        cmds.setAttr(endpoint+".ty", length)
        _line(node+"Display", [(0, 0, 0), (0, length, 0)], color, node)
        for joint in (node, endpoint):
            cmds.setAttr(joint+".overrideEnabled", True)
            cmds.setAttr(joint+".overrideRGBColors", True)
            cmds.setAttr(joint+".overrideColorRGB", *color)
            cmds.setAttr(joint+".radius", 0.12)
    _line("blueArmLocalX", [(0, 0, 0), (3, 0, 0)], (0.1, 0.65, 1), arm)
    _line("twistPlaneRing", [(0, 1.3*math.cos(i*math.pi/24), 1.3*math.sin(i*math.pi/24))
                            for i in range(49)], (0.4, 0.4, 0.4), arm)
    for attr in ("ry", "rz"):
        cmds.setAttr(output+"."+attr, lock=True)

    # 球中心を腕のローカル空間へ変換し、尻尾の回転平面(YZ)の断面を求める。
    center = _node("pointMatrixMult", "sphereCenterInArm")
    _connect(arm+".worldInverseMatrix[0]", center+".inMatrix")
    cx, cy, cz = [center+".output"+axis for axis in "XYZ"]
    cx2 = _multiply("centerX2", cx, cx)
    cy2 = _multiply("centerY2", cy, cy)
    cz2 = _multiply("centerZ2", cz, cz)
    plane_radius2 = _sum("sectionRadiusSquared", (), ((radius+gap)**2,))
    plane_radius2 = _sum("radiusSquaredMinusCenterX2", (plane_radius2, cx2), subtract=True)
    nonnegative_radius2 = _condition("validRadiusSquared", plane_radius2, 0, plane_radius2, 0)
    plane_radius = _sqrt("sectionRadius", nonnegative_radius2)
    planar_distance2 = _sum("planarCenterDistanceSquared", (cy2, cz2))
    planar_distance = _sqrt("planarCenterDistance", planar_distance2)
    tangent_length2 = _sum("tangentLengthSquared", (planar_distance2, nonnegative_radius2), subtract=True)
    tangent_length = _sqrt("tangentLength", _condition("validTangentLength", tangent_length2, 0, tangent_length2, 0))
    negative_tangent = _multiply("negativeTangent", tangent_length, constant=-1)
    tangent = _node("angleBetween", "sectionTangentAngle", vector1X=1, vector1Y=0,
                    vector1Z=0, vector2Z=0)
    _connect(negative_tangent, tangent+".vector2X")
    _connect(plane_radius, tangent+".vector2Y")
    limit = _degrees("sectionLimitDegrees", tangent+".angle")

    outward = _node("angleBetween", "outwardLocalAngle", vector1X=0, vector1Y=1,
                    vector1Z=0, vector2X=0)
    neg_y = _multiply("outwardY", cy, constant=-1)
    neg_z = _multiply("outwardZ", cz, constant=-1)
    _connect(neg_y, outward+".vector2Y")
    _connect(neg_z, outward+".vector2Z")
    unsigned = _degrees("outwardUnsignedDegrees", outward+".angle")
    negative_outward = _multiply("negativeOutwardAngle", unsigned, constant=-1)
    signed = _condition("signedOutwardDegrees", cz, 0, negative_outward, unsigned)
    requested = _degrees("requestedTwistDegrees", source+".rx")
    relative = _sum("relativeTwist", (requested, signed), subtract=True)
    above = _sum("subtract360", (relative,), (-360,))
    below = _sum("add360", (relative,), (360,))
    wrapped = _condition("wrapAbove180", relative, 180, above, relative)
    wrapped = _condition("wrapBelowMinus180", relative, -180, below, wrapped, operation=4)
    clamp = _node("clamp", "twistOnlyLimit")
    _connect(wrapped, clamp+".inputR")
    _connect(limit, clamp+".maxR")
    _connect(_multiply("negativeTwistLimit", limit, constant=-1), clamp+".minR")
    world_twist = _sum("correctedTwistDegrees", (signed, clamp+".outputR"))
    comparison = None
    elbow_side = 1
    if fixedElbowSide:
        # 肘の曲がる側を示すガイド。初期姿勢で接線側を選び、実行中は変えない。
        hint = cmds.createNode("joint", name="elbowDirection_JNT", parent=arm)
        cmds.setAttr(hint+".tz", -2)
        cmds.setAttr(hint+".radius", 0.15)
        _line("yellowElbowDirection", [(0, 0, 0), (0, 0, -2)], (1, 0.8, 0.1), arm)
        initial_center = cmds.getAttr(center+".output")[0]
        n_y, n_z = -initial_center[1], -initial_center[2]
        guide = cmds.getAttr(hint+".translate")[0]
        side_dot = -n_z*guide[1]+n_y*guide[2]
        if abs(side_dot)<1e-8:
            raise RuntimeError("肘ガイドから接線側を判定できません。")
        elbow_side = 1 if side_dot>0 else -1
        cmds.addAttr(arm, longName="elbowAvoidSide", attributeType="long", defaultValue=elbow_side)
        cmds.setAttr(arm+".elbowAvoidSide", lock=True)
        comparison = cmds.createNode("joint", name="nearestSideComparison_JNT", parent=arm)
        _line("orangeNearestSide", [(0, 0, 0), (0, length, 0)], (1, 0.5, 0.1), comparison)
        comparison_conversion = _node("unitConversion", "nearestComparisonRadians", conversionFactor=math.pi/180)
        comparison_degrees = _condition("nearestComparisonActive", plane_radius2, 0, world_twist, requested)
        _connect(comparison_degrees, comparison_conversion+".input")
        _connect(comparison_conversion+".output", comparison+".rx")
        fixed_offset = _multiply("elbowSideLimit", limit, constant=elbow_side)
        fixed_tangent = _sum("elbowSideTangentDegrees", (signed, fixed_offset))
        absolute = _condition("absoluteRelative", wrapped, 0, wrapped,
                              _multiply("negativeRelative", wrapped, constant=-1))
        unsafe_margin = _sum("unsafeAngleMargin", (absolute, limit), subtract=True)
        world_twist = _condition("useFixedElbowTangent", unsafe_margin, 0, fixed_tangent, requested)
    # 球が回転平面に届かない場合は、入力をそのまま通す。
    selected = _condition("planeIntersectsSphere", plane_radius2, 0, world_twist, requested)
    if continuousElbowSide:
        # 橙は旧固定側の出力。同じ入力で不連続との差を示す。
        cmds.connectAttr(world_twist, comparison_degrees.replace(".outColorR", ".colorIfTrueR"), force=True)
        # ±180度の符号折り返しを避け、接線と初期尾(+Y)の無符号角を求める。
        tangent_radians = _node("unitConversion", "targetTangentRadians", conversionFactor=math.pi/180)
        _connect(fixed_tangent, tangent_radians+".input")
        target_matrix = _node("composeMatrix", "targetTangentMatrix")
        _connect(tangent_radians+".output", target_matrix+".inputRotateX")
        target_direction = _node("vectorProduct", "targetTangentDirection", operation=3,
                                 input1X=0, input1Y=1, input1Z=0)
        _connect(target_matrix+".outputMatrix", target_direction+".matrix")
        magnitude = _node("angleBetween", "unsignedElbowMagnitude", vector1X=0, vector1Y=1, vector1Z=0)
        _connect(target_direction+".output", magnitude+".vector2")
        magnitude_degrees = _degrees("elbowMagnitudeDegrees", magnitude+".angle")
        cap = _node("clamp", "maximumElbowMagnitude", minR=0, maxR=maximumAngle)
        _connect(magnitude_degrees, cap+".inputR")
        bound_plug = _multiply("negativeElbowBound", cap+".outputR", constant=-1)
        continuous = _node("clamp", "continuousElbowOutput", minR=-maximumAngle)
        _connect(bound_plug, continuous+".maxR")
        _connect(requested, continuous+".inputR")
        # 球の断面がない状態でも制限を維持し、突然bypassへ復帰しない。
        selected = continuous+".outputR"
    radians = _node("unitConversion", "correctedTwistRadians", conversionFactor=math.pi/180)
    _connect(selected, radians+".input")
    _connect(radians+".output", output+".rx")

    camera, camera_shape = cmds.camera(name="jointTwistCamera", orthographic=True)
    if topView:
        cmds.setAttr(camera+".translate", 0, 30, 0)
        cmds.setAttr(camera+".rotate", -90, 0, 0)
    else:
        cmds.setAttr(camera+".translate", 14, 25, 18)
        # カメラだけの向きを設定する。回避リグにはconstraintを使用しない。
        camera_constraint = cmds.aimConstraint(sphere, camera, aimVector=(0, 0, -1),
                                               upVector=(0, 1, 0), worldUpType="vector",
                                               worldUpVector=(0, 1, 0))[0]
        cmds.delete(camera_constraint)
    cmds.setAttr(camera_shape+".orthographicWidth", 34)
    if largeMotion and topView:
        cmds.setAttr(camera+".tz", -2)
        cmds.setAttr(camera_shape+".orthographicWidth", 30)
    window = cmds.window("jointTwistWindow", widthHeight=(1000, 1000))
    pane = cmds.paneLayout(parent=window)
    panel = cmds.modelPanel("jointTwistPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", grid=False,
                     cameras=False, joints=True, headsUpDisplay=True, manipulators=False,
                     selectionHiliteDisplay=False)
    cmds.showWindow(window)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    for hud in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        cmds.headsUpDisplay(hud, remove=True)
    values = [""]*6
    huds = ["jointTwistFormula{}".format(i) for i in range(6)]
    for i, hud in enumerate(huds):
        cmds.headsUpDisplay(hud, section=5, block=5-i, blockSize="large", dataFontSize="large",
                            command=lambda row=i: values[row])
    # 根元位置・腕傾斜は入力。補正は子ジョイントのrxだけ。
    poses = [(4.5, 0, 0, 90), (4.5, 0, 0, 90), (4.5, 0, 0, 10),
             (3.4, 0, 0, 10), (3.4, 0, 0, 10), (7, 0, 0, 10),
             (4.5, 50, 0, 30), (4.5, -50, 0, -30), (4.5, 0, 25, 10),
             (4.5, 0, 25, 10), (4.5, 0, 60, 10), (4.5, 0, 60, 10),
             (4.5, 0, -25, -10), (4.5, 0, -25, -10), (4.5, 0, 0, 90)]
    if fixedElbowSide:
        # 優先側から入り、中心方向を往復しても同じ接線を保持する比較。
        poses = [(4.5, 0, 0, -90), (4.5, 0, 0, -90), (4.5, 0, 0, -10),
                 (4.5, 0, 0, 10), (4.5, 0, 0, 10), (3.4, 0, 0, 10),
                 (7, 0, 0, 10), (4.5, 25, 0, 10), (4.5, -25, 0, -10),
                 (4.5, 0, 25, 10), (4.5, 0, 25, -10), (4.5, 0, 0, -10),
                 (4.5, 0, 0, 10), (4.5, 0, 0, -10), (4.5, 0, 0, -90)]
    if reproduceFlip:
        poses = [(4.5, 0, 0, 44), (4.5, 0, 0, 44), (4.5, 0, 0, 40),
                 (4.5, 0, 0, 40), (4.5, 0, 0, 44),
                 (4.3, 0, 0, 43), (4.3, 0, 0, 43), (4.7, 0, 0, 43),
                 (4.7, 0, 0, 43), (4.3, 0, 0, 43),
                 (4.5, -2, 0, 43), (4.5, -2, 0, 43), (4.5, 2, 0, 43),
                 (4.5, 2, 0, 43), (4.5, -2, 0, 43),
                 (4.5, 0, 0, 40), (4.5, 0, 0, 40), (4.5, 0, 25, 40),
                 (4.5, 0, 25, 40), (4.5, 0, 0, 40),
                 (4.5, 0, 0, -10), (4.5, 0, 0, -10), (4.5, 0, 0, 10),
                 (4.5, 0, 0, 10), (4.5, 0, 0, -10)]
    if continuousElbowSide:
        poses += [(3.2, 0, 0, 10), (3.2, 0, 0, 10), (4.5, 0, 0, -10)]
    if largeMotion:
        poses = [(6.5, 0, 0, -55), (6.5, 0, 0, -55), (8, -25, 0, -55),
                 (8, 25, 0, -55), (6.5, 0, 30, -55), (6.5, 0, 0, -55),
                 (6.5, 0, 0, -100), (6.5, 0, 0, 100), (6.5, 0, 0, -100),
                 (6.5, 0, 0, -55), (6.5, 0, 0, 10),
                 (3.2, 0, 0, 10), (3.2, 0, 0, 10), (3.2, 0, 0, 10),
                 (6.5, 0, 0, 10), (6.5, 0, 0, -55), (6.5, 0, 0, -55)]
        ghost = _line("initialPoseGhost", [(6.5, 0, 0),
            (6.5-length*math.cos(math.radians(-55)), 0, length*math.sin(math.radians(-55)))],
            (0.45, 0.45, 0.45))
        ghost_shape = cmds.listRelatives(ghost, shapes=True, fullPath=True)[0]
        cmds.setAttr(ghost_shape+".lineWidth", 1)
    segment_frames = 48 if largeMotion else 36
    count = (len(poses)-1)*segment_frames+1
    for frame in range(count):
        phase = frame/segment_frames
        index = min(int(phase), len(poses)-2)
        w = phase-index
        w = w*w*(3-2*w)
        d, orbit, tilt, twist = [a+(b-a)*w for a, b in zip(poses[index], poses[index+1])]
        for attr, value in (("tx", d*math.cos(math.radians(orbit))),
                            ("tz", -d*math.sin(math.radians(orbit))), ("rz", tilt)):
            cmds.setKeyframe(arm, attribute=attr, time=frame+1, value=value)
        cmds.setKeyframe(source, attribute="rx", time=frame+1, value=twist)
    cmds.playbackOptions(minTime=1, maxTime=count)
    previous = {"angle": None, "flash_until": -1, "jump": 0}

    def evaluate(frame):
        """保存可能な標準DG出力を独立した数学と線分球距離で検査する。"""
        cmds.currentTime(frame+1)
        c = cmds.getAttr(center+".output")[0]
        r2 = (radius+gap)**2-c[0]**2
        rho = math.sqrt(max(0, r2))
        dp = math.hypot(c[1], c[2])
        requested_value = cmds.getAttr(source+".rx")
        reference = math.degrees(math.atan2(-c[2], -c[1]))
        reference = 180 if abs(abs(reference)-180)<1e-6 else reference
        lim = 180-math.degrees(math.asin(min(1, rho/dp))) if dp>1e-8 else 180
        rel = (requested_value-reference+180)%360-180
        expected = reference+max(-lim, min(lim, rel)) if r2>0 else requested_value
        if fixedElbowSide:
            expected = reference+elbow_side*lim if r2>0 and abs(rel)>lim else requested_value
        bound = None
        if continuousElbowSide:
            magnitude_value = abs((reference+elbow_side*lim+180)%360-180)
            bound = -min(maximumAngle, magnitude_value)
            expected = max(-maximumAngle, min(bound, requested_value))
        actual = cmds.getAttr(output+".rx")
        step = abs((actual-previous["angle"]+180)%360-180) if previous["angle"] is not None else 0
        previous["angle"] = actual
        if step>30:
            previous["flash_until"] = frame+24
            previous["jump"] = step

        def hit(joint):
            """リグに接続しない線分球交差の独立検査。"""
            m = cmds.xform(joint, query=True, worldSpace=True, matrix=True)
            origin, direction = m[12:15], m[4:7]
            t = max(0, min(length, -sum(a*b for a, b in zip(origin, direction))))
            return sum((a+t*b)**2 for a, b in zip(origin, direction)) < radius**2

        raw_hit, safe_hit = hit(source), hit(output)
        values[:] = [
            "JOINTS | BLUE = arm local X | only tail.rotateX changes",
            "c in arm=({:+.2f},{:+.2f},{:+.2f}) cm".format(*c),
            "rho=sqrt(max(0,R*R-cx*cx))={:.2f} cm".format(rho),
            "dYZ={:.2f} | limit=180-asin(rho/dYZ)={:.2f}".format(dp, lim),
            "input RX={:+.2f} | {}".format(requested_value, "SECTION ACTIVE" if r2>0 else "NO SECTION: BYPASS"),
            "output RX={:+.2f} | RY=0.00 RZ=0.00".format(actual),
        ]
        if fixedElbowSide:
            values[0] = "GREEN=fixed elbow side | ORANGE=nearest | YELLOW=elbow"
            values[2] = "fixed side s={:+d} | limit={:.2f} deg".format(elbow_side, lim)
            values[3] = "unsafe: output=outward+s*limit | safe: input"
            values[4] = "input RX={:+.2f} | relative={:+.2f}".format(requested_value, rel)
        if reproduceFlip:
            case = min(int(frame/36)//5, 4)
            labels = ["A: INPUT 44 -> 40 deg", "B: ELBOW DISTANCE 4.3 -> 4.7",
                      "C: ELBOW POSITION -2 -> +2 deg", "D: ARM TILT 0 -> 25 deg",
                      "CONTROL: inward crossing (no side switch)"]
            values[1] = labels[case]
            values[2] = "opposite boundary=outward-limit={:+.2f} deg".format(reference-lim)
            values[3] = "dYZ={:.2f} | limit={:.2f} | {}".format(dp, lim,
                "FIXED TANGENT" if r2>0 and abs(rel)>lim else "SAFE: INPUT")
            values[5] = "RX={:+.2f} | {}".format(actual,
                "FLIP {:.2f} deg / 1 frame".format(previous["jump"]) if frame<=previous["flash_until"]
                else "step={:.3f} deg | RY=RZ=0".format(step))
        if continuousElbowSide:
            values[0] = "GREEN=continuous cap | ORANGE=old fixed | penetration allowed"
            if frame>=25*36:
                values[1] = "CAP TEST: near body, required angle > 60 deg"
            values[2] = "bound=-min({:.0f}, unsigned tangent angle)={:.2f}".format(maximumAngle, bound)
            values[3] = "output=clamp(input, -{:.0f}, bound)".format(maximumAngle)
            values[4] = "input={:+.2f} | GREEN {} (allowed)".format(requested_value, "BODY HIT" if safe_hit else "CLEAR")
            values[5] = "RX={:+.2f} | step={:.3f} deg | RY=RZ=0".format(actual, step)
        stage = None
        if largeMotion:
            if frame<48:
                stage = "01 INITIAL POSE - grey line is the starting pose"
            elif frame<240:
                stage = "02 SAFE - move elbow and tilt arm"
            elif frame<432:
                stage = "03 NO FLIP - input sweeps -100 to +100 deg"
            elif frame<672:
                stage = "04 CAP + PENETRATION - approach body, stop at -60 deg"
            else:
                stage = "05 RETURN - move away and recover starting pose"
            cmds.setAttr(comparison+".visibility", 240<=frame<432)
            values[0] = "GREEN=output | RED=input | GREY=initial | ORANGE=old (stage 3)"
            values[1] = stage
            values[2] = "elbow distance={:.2f} cm | limit RX=-60..0 deg".format(math.sqrt(sum(v*v for v in c)))
            values[3] = "input RX={:+.2f} | output RX={:+.2f}".format(requested_value, actual)
            values[4] = "GREEN: {} | 1-frame step={:.3f} deg".format("BODY HIT - ALLOWED" if safe_hit else "CLEAR", step)
        for hud in huds:
            cmds.headsUpDisplay(hud, refresh=True)
        angle_error = abs((actual-expected+180)%360-180)
        return {"frame": frame, "requested_degrees": requested_value, "output_degrees": actual,
                "section_radius_cm": rho, "section_active": r2>0, "limit_degrees": lim,
                "angle_error_degrees": angle_error,
                "output_step_degrees": step,
                "reproduction_case": case if reproduceFlip else None,
                "continuous_bound_degrees": bound,
                "penetration_allowed": continuousElbowSide,
                "presentation_stage": stage,
                "fixed_elbow_side": elbow_side if fixedElbowSide else None,
                "nearest_output_degrees": cmds.getAttr(comparison+".rx") if comparison else actual,
                "raw_intersections": ["bodySphere"] if raw_hit else [],
                "corrected_intersections": ["bodySphere"] if safe_hit else [],
                "ok": (continuousElbowSide or not safe_hit) and angle_error<1e-3
                      and cmds.getAttr(output+".ry")==0 and cmds.getAttr(output+".rz")==0
                      and cmds.getAttr(output+".translate")[0]==(0, 0, 0)}

    title = "ジョイント: 腕ローカルXの1軸だけで尻尾を回避" + (" (上面)" if topView else "")
    if fixedElbowSide:
        title = "上面: 肘側の接線へ固定 (緑) と最近接側 (橙)"
    if reproduceFlip:
        title = "フリップ再現: 固定肘側とは逆の安全境界を横切る"
    if continuousElbowSide:
        title = "フリップ優先回避: 肘側の回転上限で停止し貫通を許容"
    if largeMotion:
        title = "初期姿勢から大きく動かす: 安全・フリップなし・上限で貫通"
    folder = recordVideo(title, count, 24, panel, evaluate,
                         ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"), width=1000, height=1000)
    if not json.loads((folder/"result.json").read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError("ジョイント1軸回避の検証に失敗: {}".format(folder))
    scene_name = "joint-twist-fixed-elbow.ma" if fixedElbowSide else "joint-twist-tangent.ma"
    if reproduceFlip:
        scene_name = "joint-fixed-side-flip-repro.ma"
    if continuousElbowSide:
        scene_name = "joint-continuous-elbow-cap.ma"
    if largeMotion:
        scene_name = "joint-continuous-cap-large-motion.ma"
    cmds.file(rename=str(folder/scene_name))
    cmds.file(save=True, type="mayaAscii")
    latest = "latest-joint-twist-top.json" if topView else "latest-joint-twist.json"
    if fixedElbowSide:
        latest = "latest-joint-fixed-elbow.json"
    if reproduceFlip:
        latest = "latest-joint-flip-repro.json"
    if continuousElbowSide:
        latest = "latest-joint-continuous-cap.json"
    if largeMotion:
        latest = "latest-joint-large-motion.json"
    (Path(__file__).resolve().parents[1]/".maya-output/verification"/latest).write_text(
        json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
    logger.info("ジョイント1軸回避を保存しました: {}".format(folder))


if __name__ == "__main__":
    main()
