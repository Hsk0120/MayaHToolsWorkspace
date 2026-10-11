"""身体に固定したコーンへの入り具合で、尻尾の rotateX をなだらかに避ける検証。

コーンは身体に固定した軸 a(身体空間の -X、体の内側へ向かう向き)と半角 γ で
決める向きだけのコーンで、尻尾の向き t と a のなす角が γ より小さいと「入っている」。
肘の位置・体との距離は使わない。

尻尾は腕ローカルXまわりにしか回らないので、t=(0, cos rx, sin rx)(腕空間)。
a を腕空間で (ax, ay, az) とすると t・a = s・cos(rx-θa)、s=√(ay²+az²)、
θa=atan2(az, ay)。コーンに入るのは rx-θa の絶対値が h 未満のとき:

    h = acos(cosγ / s)      (s <= cosγ ならコーンは回転面に届かず h=0)

外向き θo=θa+180 を基準に、折り返さない相対角 rel=rx-θo を使い、境界 L=180-h の
手前 m=min(M, h) から入り具合でブレーキをかける。

    x=|rel|、start=L-m、depth=x-start
    x <= start: 出力 x
    x >  start: 出力 start + m*depth/(depth+m)   (L に近づくが越えない)

符号は rel の符号(入ってきた側)を保つので、中心を越えてもフリップしない。
比較として、入力と球の接線止め(入った側を保持)を並べる。リグはMaya標準ノード
のみで評価し、Pythonは入力アニメーションと検査用。
"""

import json
import math
import os
from pathlib import Path

from maya import cmds
from mlib import logger
from demo_top_view_moving_tangent import _line, _node, _connect
from demo_joint_twist_tangent import _sum, _multiply, _condition, _sqrt, _degrees
from demo_joint_sweep_compare import _compare, _divide, _clampRange, _tail, RADIUS, LENGTH
import demo_joint_side_keep
from verification_video import recordVideo
import demo_interactive

SEGMENT_FRAMES = 30
CONE_ANGLE = 40.0
SOFT_MARGIN = 40.0
EPSILON = 1e-4
CONE_COLOR = (1, 0.85, 0.1)
SPACING = demo_joint_side_keep.SPACING
BODY_SHIFT = demo_joint_side_keep.BODY_SHIFT

# (肘距離cm, 円周位置deg, 腕傾斜deg, 球の外向き基準の入力rel deg, 身体の向きdeg, 段階名)
POSES = [
    (6.5, 0, 0, -40, 0, "1 INITIAL"),
    (6.5, 0, 0, -40, 0, "2 ENTER FROM +"),
    (6.5, 0, 0, 100, 0, "2 ENTER FROM +"),
    (6.5, 0, 0, 180, 0, "2 ENTER FROM +"),
    (6.5, 0, 0, 205, 0, "2 ENTER FROM +"),
    (6.5, 0, 0, 205, 0, "3 BACK"),
    (6.5, 0, 0, -40, 0, "3 BACK"),
    (6.5, 0, 0, -40, 0, "4 ENTER FROM -"),
    (6.5, 0, 0, -180, 0, "4 ENTER FROM -"),
    (6.5, 0, 0, -205, 0, "4 ENTER FROM -"),
    (6.5, 0, 0, -205, 0, "5 BACK"),
    (6.5, 0, 0, 170, 0, "6 ELBOW MOVES (+)"),
    (4.0, 0, 0, 170, 0, "6 ELBOW MOVES (+)"),
    (6.0, 30, 0, 190, 0, "6 ELBOW MOVES (+)"),
    (4.0, -30, 0, 170, 0, "6 ELBOW MOVES (+)"),
    (5.0, 0, 0, 170, 0, "7 ARM TILT"),
    (5.0, 0, 40, 170, 0, "7 ARM TILT"),
    (5.0, 0, 0, 150, 0, "8 BODY TURNS"),
    (5.0, 0, 0, 150, 25, "8 BODY TURNS"),
    (5.0, 0, 0, 150, -25, "8 BODY TURNS"),
    (5.0, 0, 0, 150, 0, "9 RETURN"),
    (6.5, 0, 0, -40, 0, "9 RETURN"),
]

# 列の並び。(キー, 見出し, 式の要約, 出力の色)
METHODS = [
    ("input", "INPUT (red) + body cone (yellow)", "no correction", None),
    ("keep", "SPHERE: tangent stop", "clamp(rel,-L,L), L=180-asin(rho/d)", (1, 0.5, 0.1)),
    ("cone", "BODY CONE: soft avoid", "start + m*depth/(depth+m)", (0.1, 1, 0.1)),
]
HUD_SECTIONS = (0, 2, 4)


def coneReference(rx, axis):
    """コーン方式の独立計算。

    Args:
        rx (float): 入力の rotateX。度。
        axis (tuple): 腕空間のコーン軸 (ax, ay, az)。単位ベクトル。

    Returns:
        tuple: (出力 rotateX 度, h 度, 外向き θo 度, 相対角 rel 度)。
    """
    s = math.hypot(axis[1], axis[2])
    cos_g = math.cos(math.radians(CONE_ANGLE))
    h = math.degrees(math.acos(min(1.0, cos_g/s))) if s > cos_g else 0.0
    outward = 180+math.degrees(math.atan2(axis[2], axis[1]))
    rel = rx-outward
    limit = 180-h
    margin = min(SOFT_MARGIN, h)
    start = limit-margin
    x = abs(rel)
    if x > start:
        depth = x-start
        x = start+margin*depth/max(depth+margin, EPSILON)
    return outward+math.copysign(x, rel), h, outward, rel


def _buildColumn(index, key, color, material_group):
    """入力列またはコーン列の体・コーン表示・腕・尻尾と標準DGを作る。

    Returns:
        dict: group, body, arm, source, output(補正尾、入力列はNone)。
    """
    p = key
    group = cmds.createNode("transform", name=p+"Column_GRP")
    cmds.setAttr(group+".tx", (index-(len(METHODS)-1)/2.0)*SPACING+BODY_SHIFT)
    body = cmds.createNode("transform", name=p+"Body_GRP", parent=group)
    sphere = cmds.polySphere(name=p+"BodySphere", radius=RADIUS, subdivisionsX=40,
                            subdivisionsY=24, constructionHistory=False)[0]
    sphere = cmds.parent(sphere, body, relative=True)[0]
    cmds.sets(sphere, edit=True, forceElement=material_group)
    arm = cmds.createNode("joint", name=p+"Arm_JNT", parent=group)
    cmds.setAttr(arm+".jointOrientZ", 90)
    cmds.setAttr(arm+".radius", 0.15)

    # コーンの表示。位置は肘、向きは身体に合わせる。上面(XZ)の断面として軸と境界を描く。
    display = cmds.createNode("transform", name=p+"ConeDisplay_GRP", parent=group)
    cmds.pointConstraint(arm, display)
    cmds.orientConstraint(body, display)
    g = math.radians(CONE_ANGLE)
    _line(p+"ConeAxis", [(0, 0, 0), (-LENGTH*0.6, 0, 0)], (0.6, 0.5, 0.1), display)
    for sign in (1, -1):
        _line(p+"ConeEdge{}".format("P" if sign > 0 else "N"),
              [(0, 0, 0), (-LENGTH*math.cos(g), 0, sign*LENGTH*math.sin(g))], CONE_COLOR, display)

    source = _tail(p+"TailInput_JNT", (1, 0.1, 0.1), arm)
    if color is None:
        return {"group": group, "body": body, "arm": arm, "source": source, "output": None}
    output = _tail(p+"TailOutput_JNT", color, arm)

    # 身体のコーン軸(身体空間 -X)を腕空間へ変換する。
    matrix = _node("multMatrix", p+"BodyToArm")
    _connect(body+".worldMatrix[0]", matrix+".matrixIn[0]")
    _connect(arm+".worldInverseMatrix[0]", matrix+".matrixIn[1]")
    axis = _node("vectorProduct", p+"ConeAxisInArm", operation=3, input1X=-1, input1Y=0, input1Z=0,
                 normalizeOutput=True)
    _connect(matrix+".matrixSum", axis+".matrix")
    ay, az = axis+".outputY", axis+".outputZ"

    # s=√(ay²+az²)。h=acos(cosγ/s) は (cosγ, √(s²-cos²γ)) とX軸のなす角として求める。
    s2 = _sum(p+"S2", (_multiply(p+"AY2", ay, ay), _multiply(p+"AZ2", az, az)))
    cos_g = math.cos(math.radians(CONE_ANGLE))
    reach2 = _sum(p+"Reach2", (s2,), (-cos_g**2,))
    reach = _sqrt(p+"Reach", _condition(p+"ValidReach", reach2, 0, reach2, 0))
    half = _node("angleBetween", p+"HalfAngle", vector1X=1, vector1Y=0, vector1Z=0,
                 vector2X=cos_g, vector2Z=0)
    _connect(reach, half+".vector2Y")
    h = _degrees(p+"H", half+".angle")

    # 回転面でのコーン中心方向 θa=atan2(az, ay)。軸は身体固定なので連続に変わる。
    center = _node("angleBetween", p+"CenterAngle", vector1X=0, vector1Y=1, vector1Z=0, vector2X=0)
    _connect(ay, center+".vector2Y")
    _connect(az, center+".vector2Z")
    unsigned = _degrees(p+"CenterUnsigned", center+".angle")
    signed = _condition(p+"CenterSigned", az, 0, unsigned, _multiply(p+"CenterNeg", unsigned, constant=-1))
    outward = _sum(p+"Outward", (signed,), (180,))
    requested = _degrees(p+"Requested", source+".rx")
    relative = _sum(p+"Relative", (requested, outward), subtract=True)

    # 入り具合でブレーキをかける。m=min(M,h)、start=L-m=180-h-m。
    magnitude = _condition(p+"AbsRel", relative, 0, relative, _multiply(p+"NegRel", relative, constant=-1),
                           operation=3)
    sign = _condition(p+"SignRel", relative, 0, 1, -1, operation=3)
    margin = _clampRange(p+"Margin", h, 0, SOFT_MARGIN)
    start = _multiply(p+"StartNeg", _sum(p+"HPlusM", (h, margin), (-180,)), constant=-1)
    depth = _sum(p+"Depth", (magnitude, start), subtract=True)
    soft = _sum(p+"Soft", (start, _divide(p+"Brake", _multiply(p+"MDepth", margin, depth),
                                          _clampRange(p+"DepthPlusM", _sum(p+"DPM", (depth, margin)),
                                                      EPSILON, 1e9))))
    limited = _compare(p+"Select", magnitude, start, soft, magnitude, operation=2)
    corrected = _sum(p+"World", (outward, _multiply(p+"Signed", limited, sign)))
    radians = _node("unitConversion", p+"Radians", conversionFactor=math.pi/180)
    _connect(corrected, radians+".input")
    _connect(radians+".output", output+".rx")
    for attr in ("ry", "rz"):
        cmds.setAttr(output+"."+attr, lock=True)
    return {"group": group, "body": body, "arm": arm, "source": source, "output": output}


def main(record=True):
    """専用GUIで3列を同じ入力で動かし、上面から録画して独立計算と照合する。

    Args:
        record (bool): True なら録画して検証する。False なら録画せず、タイムラインの
            再生・スクラブでHUDと数値が更新されるシーンを作る。
    """
    if cmds.about(batch=True):
        raise RuntimeError("専用Maya GUIで実行してください。")
    if "coneSoftPanel" in cmds.getPanel(allPanels=True):
        cmds.deleteUI("coneSoftPanel", panel=True)
    if cmds.window("coneSoftWindow", exists=True):
        cmds.deleteUI("coneSoftWindow", window=True)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")

    material = cmds.shadingNode("lambert", asShader=True, name="bodyProxyMaterial")
    cmds.setAttr(material+".color", 0.18, 0.22, 0.28, type="double3")
    cmds.setAttr(material+".transparency", 0.55, 0.55, 0.55, type="double3")
    material_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
    _connect(material+".outColor", material_group+".surfaceShader")
    columns = {}
    for i, (key, _, _, color) in enumerate(METHODS):
        if key == "keep":
            columns[key] = demo_joint_side_keep._buildColumn(i, key, color, material_group)
        else:
            columns[key] = _buildColumn(i, key, color, material_group)

    camera, camera_shape = cmds.camera(name="coneSoftCamera", orthographic=True)
    cmds.setAttr(camera+".translate", 0, 40, 0)
    cmds.setAttr(camera+".rotate", -90, 0, 0)
    cmds.setAttr(camera_shape+".orthographicWidth", SPACING*len(METHODS))
    if cmds.windowPref("coneSoftWindow", exists=True):
        cmds.windowPref("coneSoftWindow", remove=True)
    window = cmds.window("coneSoftWindow", widthHeight=(1800, 760))
    pane = cmds.paneLayout(parent=window)
    panel = cmds.modelPanel("coneSoftPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", grid=False, cameras=False,
                     joints=True, headsUpDisplay=True, manipulators=False, selectionHiliteDisplay=False)
    cmds.showWindow(window)
    cmds.window(window, edit=True, widthHeight=(1800, 760))
    cmds.setFocus(panel)
    cmds.select(clear=True)
    demo_interactive.clearHuds(window)
    rows = 3
    texts = {}
    for column, section in enumerate(HUD_SECTIONS):
        for row in range(rows):
            for prefix, base, block in (("coneTop", section, row), ("coneBottom", section+5, rows-1-row)):
                name = "{}{}_{}".format(prefix, column, row)
                texts[name] = ""
                cmds.headsUpDisplay(name, section=base, block=block, blockSize="large", dataFontSize="large",
                                    command=lambda n=name: texts[n])

    # 入力アニメーション。relは球の外向き(連続)基準で指定し、全列に同じキーを打つ。
    count = (len(POSES)-1)*SEGMENT_FRAMES+1
    stages = []
    tracks = []
    for frame in range(count):
        phase = frame/SEGMENT_FRAMES
        index = min(int(phase), len(POSES)-2)
        w = phase-index
        w = w*w*(3-2*w)
        d, orbit, tilt, rel, yaw = [a+(b-a)*w for a, b in zip(POSES[index][:5], POSES[index+1][:5])]
        tracks.append((d*math.cos(math.radians(orbit)), -d*math.sin(math.radians(orbit)), tilt, rel, yaw))
        stages.append(POSES[index][5] if frame else POSES[0][5])
    reference_center = _node("pointMatrixMult", "inputColumnCenterInArm")
    _connect(columns["input"]["arm"]+".inverseMatrix", reference_center+".inMatrix")
    for frame, (tx, tz, tilt, rel, yaw) in enumerate(tracks):
        for column in columns.values():
            for attr, value in (("tx", tx), ("tz", tz), ("rz", tilt)):
                cmds.setKeyframe(column["arm"], attribute=attr, time=frame+1, value=value)
            if "body" in column:
                cmds.setKeyframe(column["body"], attribute="ry", time=frame+1, value=yaw)
        c = cmds.getAttr(reference_center+".output", time=frame+1)[0]
        twist = 180+math.degrees(math.atan2(c[2], c[1]))+rel
        for column in columns.values():
            cmds.setKeyframe(column["source"], attribute="rx", time=frame+1, value=twist)
    cmds.playbackOptions(minTime=1, maxTime=count)

    last = {"keep": None, "cone": None}
    flash = {"keep": -1, "cone": -1}

    def hit(joint, offset):
        """リグに接続しない線分球交差の独立検査。列の原点を球中心とする。"""
        m = cmds.xform(joint, query=True, worldSpace=True, matrix=True)
        origin = (m[12]-offset, m[13], m[14])
        direction = m[4:7]
        t = max(0, min(LENGTH, -sum(a*b for a, b in zip(origin, direction))))
        return sum((a+t*b)**2 for a, b in zip(origin, direction)) < RADIUS**2

    def coneAngle(joint, body):
        """尻尾の向きと身体固定のコーン軸がなす角。度。"""
        m = cmds.xform(joint, query=True, worldSpace=True, matrix=True)
        b = cmds.xform(body, query=True, worldSpace=True, matrix=True)
        axis = [-v for v in b[0:3]]
        dot = sum(x*y for x, y in zip(m[4:7], axis))/math.sqrt(sum(v*v for v in axis))
        return math.degrees(math.acos(max(-1.0, min(1.0, dot))))

    def armAxis(arm, body):
        """コーン軸を腕空間へ変換した単位ベクトル。リグと独立に行列から求める。"""
        m = cmds.xform(arm, query=True, worldSpace=True, matrix=True)
        b = cmds.xform(body, query=True, worldSpace=True, matrix=True)
        axis = [-v for v in b[0:3]]
        local = [sum(axis[j]*m[4*i+j] for j in range(3))/math.sqrt(sum(m[4*i+j]**2 for j in range(3)))
                 for i in range(3)]
        n = math.sqrt(sum(v*v for v in local))
        return [v/n for v in local]

    def evaluate(frame):
        """球列とコーン列の標準DG出力を独立計算・交差・コーン侵入・ロック状態で検査する。"""
        demo_interactive.setTime(frame)
        c = cmds.getAttr(reference_center+".output")[0]
        r2 = (RADIUS+demo_joint_side_keep.GAP)**2-c[0]**2
        rho_value = math.sqrt(max(0, r2))
        dp = math.hypot(c[1], c[2])
        lim = 180-math.degrees(math.asin(min(1, rho_value/dp))) if r2 > 0 and dp > 1e-8 else 180
        outward = 180+math.degrees(math.atan2(c[2], c[1]))
        requested_value = cmds.getAttr(columns["input"]["source"]+".rx")
        rel = requested_value-outward
        input_column = columns["input"]
        offset = cmds.getAttr(input_column["group"]+".tx")
        input_cone = coneAngle(input_column["source"], input_column["body"])
        result = {"frame": frame, "stage": stages[frame], "requested_degrees": requested_value,
                  "sphere_relative_degrees": rel, "sphere_limit_degrees": lim,
                  "input_body_hit": hit(input_column["source"], offset),
                  "input_cone_angle_degrees": input_cone}
        ok = True

        keep = columns["keep"]
        actual = cmds.getAttr(keep["output"]+".rx")
        expected = max(-lim, min(lim, rel))
        target = outward+expected if r2 > 0 else requested_value
        keep_error = abs((actual-target+180) % 360-180)
        keep_hit = hit(keep["output"], cmds.getAttr(keep["group"]+".tx"))
        keep_step = abs((actual-last["keep"]+180) % 360-180) if last["keep"] is not None else 0.0
        last["keep"] = actual
        result["keep"] = {"output_degrees": actual, "error_degrees": keep_error, "step_degrees": keep_step,
                          "body_hit": keep_hit}

        cone = columns["cone"]
        actual = cmds.getAttr(cone["output"]+".rx")
        target, h, cone_outward, cone_rel = coneReference(requested_value, armAxis(cone["arm"], cone["body"]))
        cone_error = abs((actual-target+180) % 360-180)
        cone_angle = coneAngle(cone["output"], cone["body"])
        cone_hit = hit(cone["output"], cmds.getAttr(cone["group"]+".tx"))
        cone_step = abs((actual-last["cone"]+180) % 360-180) if last["cone"] is not None else 0.0
        last["cone"] = actual
        result["cone"] = {"output_degrees": actual, "error_degrees": cone_error, "step_degrees": cone_step,
                          "half_width_degrees": h, "relative_degrees": cone_rel,
                          "cone_angle_degrees": cone_angle, "body_hit": cone_hit}
        for key, step in (("keep", keep_step), ("cone", cone_step)):
            if step > 30:
                flash[key] = frame+24
        locked = all(cmds.getAttr(columns[k]["output"]+"."+a) == 0 for k in ("keep", "cone") for a in ("ry", "rz"))
        # 球列は球と非交差、コーン列はコーンに入らないことを保証として検査する。
        ok = (keep_error < 1e-3 and cone_error < 1e-3 and locked and not keep_hit
              and cone_angle >= CONE_ANGLE-1e-3)
        result["ok"] = ok

        margin = min(SOFT_MARGIN, h)
        start = 180-h-margin
        depth = max(0.0, abs(cone_rel)-start)
        lines = {
            "input": ("rel={:+.1f}  axis angle {:.1f}".format(rel, input_cone),
                      ("INSIDE CONE" if input_cone < CONE_ANGLE else "outside cone")
                      + ("  BODY HIT" if result["input_body_hit"] else ""),
                      "cone = {:.0f} deg around body -X".format(CONE_ANGLE)),
            "keep": ("rel={:+.1f}  L={:.1f} -> out {:+.1f}".format(rel, lim, expected),
                     ("BODY HIT" if keep_hit else "clear")
                     + "  step {:.1f}".format(keep_step) + ("  JUMP!" if frame <= flash["keep"] else ""),
                     ""),
            "cone": ("h={:.1f} m={:.1f} start={:.1f}".format(h, margin, start),
                     "rel={:+.1f} depth={:.1f} axis angle {:.1f}".format(cone_rel, depth, cone_angle),
                     "h = acos(cos{:.0f}/s)  step {:.1f}".format(CONE_ANGLE, cone_step)
                     + ("  JUMP!" if frame <= flash["cone"] else "")),
        }
        for column, (key, title, formula, _) in enumerate(METHODS):
            texts["coneTop{}_0".format(column)] = title
            texts["coneTop{}_1".format(column)] = formula
            texts["coneTop{}_2".format(column)] = lines[key][0]
            texts["coneBottom{}_0".format(column)] = lines[key][1]
            texts["coneBottom{}_1".format(column)] = lines[key][2]
            texts["coneBottom{}_2".format(column)] = stages[frame] if key == "input" else ""
        for name in texts:
            cmds.headsUpDisplay(name, refresh=True)
        return result

    if not record:
        demo_interactive.attachInteractive(window, count, evaluate, [(last, None), (flash, -1)])
        logger.info("身体固定コーンのシーンを作成しました。タイムラインで再生・スクラブして確認できます。")
        return
    folder = recordVideo("尻尾1軸回避: 身体固定コーンへの入り具合でなだらかに避ける（球の接線止めとの比較）",
                         count, 24, panel, evaluate,
                         ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"), width=1800, height=760)
    if not json.loads((folder/"result.json").read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError("身体固定コーンの検証に失敗: {}".format(folder))
    cmds.file(rename=str(folder/"joint-cone-soft.ma"))
    cmds.file(save=True, type="mayaAscii")
    (Path(__file__).resolve().parents[1]/".maya-output/verification/latest-joint-cone-soft.json").write_text(
        json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
    logger.info("身体固定コーンの検証を保存しました: {}".format(folder))


if __name__ == "__main__":
    main()
