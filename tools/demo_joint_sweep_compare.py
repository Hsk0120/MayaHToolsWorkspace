"""尻尾ジョイントの1軸回避方式を、方式ごとの列に横並びで比較する検証。

腕ローカルXの rotateX だけで尻尾を回し、球近似の体を避ける。各列は同じ入力
アニメーションで動き、外向き=0度とした相対角度 rel の写像だけが異なる。

- 入力: 補正なし（赤のみ）。
- 従来: 両方向・最近接接線。clamp(rel, -L, L)。rel=±180 で左右が入れ替わる。
- 外側を回す: |rel|<=L は入力のまま。禁止範囲では外側を通って反対側の接線へ運ぶ。
- 先回り: 頂点 P=1.5L-90 で折り返し、速さを抑える。
- コーン押し出し: 体の中心方向のコーンに入った量 w で、+側へ A=1.15h だけ押す。

いずれもMaya標準ノードのみで評価する。Pythonは入力アニメーションと検査用。
"""

import json
import math
import os
from pathlib import Path

from maya import cmds
from mlib import logger
from demo_top_view_moving_tangent import _line, _node, _connect
from demo_joint_twist_tangent import _sum, _multiply, _condition, _sqrt, _degrees
from verification_video import recordVideo
import demo_interactive

RADIUS = 3.0
GAP = 0.03
LENGTH = 9.0
EPSILON = 1e-4
SEGMENT_FRAMES = 36
SPACING = 22.0
# 肘は常に体の+X側にあるので、列内で体を左へ寄せて図を中央に収める。
BODY_SHIFT = -5.0
CONE_FALLOFF = 30.0
CONE_SCALE = 1.15

# (肘距離cm, 円周位置deg, 腕傾斜deg, 外向き基準の入力rel deg, 段階名)
POSES = [
    (6.5, 0, 0, -40, "1 INITIAL"),
    (6.5, 0, 0, -40, "2 SAFE TWIST"),
    (6.5, 0, 0, 100, "3 THROUGH CENTER"),
    (6.5, 0, 0, 180, "3 THROUGH CENTER"),
    (6.5, 0, 0, 260, "3 THROUGH CENTER"),
    (6.5, 0, 0, 260, "4 TWIST BACK"),
    (6.5, 0, 0, 100, "5 ELBOW NEAR"),
    (4.0, 0, 0, 100, "5 ELBOW NEAR"),
    (4.0, 0, 0, 260, "5 ELBOW NEAR"),
    (4.0, 0, 0, 170, "6 ELBOW MOVES"),
    (6.0, 30, 0, 190, "6 ELBOW MOVES"),
    (4.0, -30, 0, 170, "6 ELBOW MOVES"),
    (5.0, 0, 0, 170, "7 ARM TILT"),
    (5.0, 0, 40, 170, "7 ARM TILT"),
    (5.0, 0, 0, 170, "8 RETURN"),
    (6.5, 0, 0, -40, "8 RETURN"),
]

# 列の並び。(キー, 見出し, 式の要約, 出力の色)
METHODS = [
    ("input", "INPUT (red)", "no correction", None),
    ("nearest", "OLD: nearest side", "clamp(rel,-L,L)", (1, 0.5, 0.1)),
    ("strict", "OUTSIDE SWEEP", "|r|>L: L(180-|r|)/(180-L)", (0.1, 1, 0.1)),
    ("soft", "EARLY TURN", "fold at P=1.5L-90", (0.2, 0.9, 1)),
    ("cone", "CONE PUSH", "r + 1.15h*w, h=180-L", (1, 0.25, 0.9)),
]


def _compare(name, first, second, yes, no, operation):
    """両項・両分岐にプラグまたは定数を受け付ける比較分岐。"""
    node = _node("condition", name, operation=operation)
    for attr, value in (("firstTerm", first), ("secondTerm", second),
                        ("colorIfTrueR", yes), ("colorIfFalseR", no)):
        if isinstance(value, str):
            _connect(value, node+"."+attr)
        else:
            cmds.setAttr(node+"."+attr, value)
    return node+".outColorR"


def _divide(name, numerator, denominator):
    """除算。分母は呼び出し側でゼロにならないよう制限する。"""
    node = _node("multiplyDivide", name, operation=2)
    _connect(numerator, node+".input1X")
    _connect(denominator, node+".input2X")
    return node+".outputX"


def _clampRange(name, plug, minimum, maximum):
    """定数範囲へ制限する。"""
    node = _node("clamp", name, minR=minimum, maxR=maximum)
    _connect(plug, node+".inputR")
    return node+".outputR"


def _oneMinus(name, plug, constant):
    """constant - plug を求める。"""
    return _multiply(name, _sum(name+"Diff", (plug,), (-constant,)), constant=-1)


def strictReference(rel, limit):
    """外側を回す方式の独立計算。度。"""
    s = abs(rel)
    if s <= limit or 180-limit < EPSILON:
        out = s
    else:
        out = limit*(180-s)/(180-limit)
    return math.copysign(out, rel) if rel else 0.0


def softReference(rel, limit):
    """先回り方式の独立計算。度。"""
    s = abs(rel)
    peak = 1.5*limit-90
    span = 180-peak
    width = 0.25*span
    if span < EPSILON:
        out = s
    else:
        slope = peak/span
        start = peak-width
        if s <= start:
            out = s
        elif s < peak+width:
            x = s-start
            out = start+x-(1+slope)*x*x/(4*max(width, EPSILON))
        else:
            out = peak-slope*(s-peak)
    return math.copysign(out, rel) if rel else 0.0


def coneReference(rel, limit):
    """コーン押し出し方式の独立計算。度。"""
    half = 180-limit
    distance = 180-abs(rel)
    t = min(1.0, max(0.0, (half+CONE_FALLOFF-distance)/CONE_FALLOFF))
    weight = t*t*(3-2*t)
    return rel+CONE_SCALE*half*weight


def _tail(name, color, parent):
    """色付きの尻尾ジョイントと方向線を作る。"""
    joint = cmds.createNode("joint", name=name, parent=parent)
    endpoint = cmds.createNode("joint", name=name+"Tip", parent=joint)
    cmds.setAttr(endpoint+".ty", LENGTH)
    _line(name+"Display", [(0, 0, 0), (0, LENGTH, 0)], color, joint)
    for node in (joint, endpoint):
        cmds.setAttr(node+".overrideEnabled", True)
        cmds.setAttr(node+".overrideRGBColors", True)
        cmds.setAttr(node+".overrideColorRGB", *color)
        cmds.setAttr(node+".radius", 0.12)
    return joint


def _buildColumn(index, key, color, material_group):
    """1方式ぶんの体・腕・入力尾・補正尾と標準DGを作る。

    Returns:
        dict: group, arm, source, output(補正尾、入力列はNone)。
    """
    p = key
    group = cmds.createNode("transform", name=p+"Column_GRP")
    cmds.setAttr(group+".tx", (index-(len(METHODS)-1)/2.0)*SPACING+BODY_SHIFT)
    sphere = cmds.polySphere(name=p+"BodySphere", radius=RADIUS, subdivisionsX=40,
                            subdivisionsY=24, constructionHistory=False)[0]
    sphere = cmds.parent(sphere, group, relative=True)[0]
    cmds.sets(sphere, edit=True, forceElement=material_group)
    arm = cmds.createNode("joint", name=p+"Arm_JNT", parent=group)
    cmds.setAttr(arm+".jointOrientZ", 90)
    cmds.setAttr(arm+".radius", 0.15)
    _line(p+"ArmLocalX", [(0, 0, 0), (3, 0, 0)], (0.1, 0.65, 1), arm)
    source = _tail(p+"TailInput_JNT", (1, 0.1, 0.1), arm)
    if color is None:
        return {"group": group, "arm": arm, "source": source, "output": None}
    output = _tail(p+"TailOutput_JNT", color, arm)

    # 球中心(列の原点)を腕空間へ変換し、尻尾の回転平面(YZ)の断面円と接線角Lを求める。
    center = _node("pointMatrixMult", p+"CenterInArm")
    _connect(arm+".inverseMatrix", center+".inMatrix")
    cx, cy, cz = [center+".output"+axis for axis in "XYZ"]
    radius2 = _oneMinus(p+"SectionR2", _multiply(p+"CX2", cx, cx), (RADIUS+GAP)**2)
    section = _condition(p+"ValidR2", radius2, 0, radius2, 0)
    rho = _sqrt(p+"SectionR", section)
    planar2 = _sum(p+"Planar2", (_multiply(p+"CY2", cy, cy), _multiply(p+"CZ2", cz, cz)))
    tangent2 = _sum(p+"Tangent2", (planar2, section), subtract=True)
    tangent_length = _sqrt(p+"TangentLen", _condition(p+"ValidTangent", tangent2, 0, tangent2, 0))
    tangent = _node("angleBetween", p+"TangentAngle", vector1X=1, vector1Y=0, vector1Z=0, vector2Z=0)
    _connect(_multiply(p+"NegTangent", tangent_length, constant=-1), tangent+".vector2X")
    _connect(rho, tangent+".vector2Y")
    limit = _degrees(p+"Limit", tangent+".angle")
    outward = _node("angleBetween", p+"OutwardAngle", vector1X=0, vector1Y=1, vector1Z=0, vector2X=0)
    _connect(_multiply(p+"OutY", cy, constant=-1), outward+".vector2Y")
    _connect(_multiply(p+"OutZ", cz, constant=-1), outward+".vector2Z")
    unsigned = _degrees(p+"OutUnsigned", outward+".angle")
    signed = _condition(p+"OutSigned", cz, 0, _multiply(p+"OutNeg", unsigned, constant=-1), unsigned)
    requested = _degrees(p+"Requested", source+".rx")
    relative = _sum(p+"Relative", (requested, signed), subtract=True)
    wrapped = _condition(p+"WrapAbove", relative, 180, _sum(p+"Minus360", (relative,), (-360,)), relative)
    wrapped = _condition(p+"WrapBelow", relative, -180, _sum(p+"Plus360", (relative,), (360,)), wrapped,
                         operation=4)
    magnitude = _condition(p+"AbsRel", wrapped, 0, wrapped, _multiply(p+"NegRel", wrapped, constant=-1),
                           operation=3)
    sign = _condition(p+"SignRel", wrapped, 0, 1, -1, operation=3)
    half = _oneMinus(p+"Half", limit, 180)

    if key == "nearest":
        positive = _node("clamp", p+"Clamp")
        _connect(magnitude, positive+".inputR")
        _connect(limit, positive+".maxR")
        rel_out = _multiply(p+"Signed", positive+".outputR", sign)
    elif key == "strict":
        remaining = _oneMinus(p+"Remaining", magnitude, 180)
        sweep = _divide(p+"Sweep", _multiply(p+"Numerator", limit, remaining),
                        _clampRange(p+"HalfSafe", half, EPSILON, 1e9))
        positive = _compare(p+"Select", magnitude, limit, magnitude, sweep, operation=5)
        rel_out = _multiply(p+"Signed", positive, sign)
    elif key == "soft":
        peak = _sum(p+"Peak", (_multiply(p+"PeakScale", limit, constant=1.5),), (-90,))
        span = _oneMinus(p+"Span", peak, 180)
        width = _multiply(p+"Width", span, constant=0.25)
        slope = _divide(p+"Slope", peak, _clampRange(p+"SpanSafe", span, EPSILON, 1e9))
        start = _sum(p+"Start", (peak, width), subtract=True)
        x = _sum(p+"X", (magnitude, start), subtract=True)
        curve = _divide(p+"Curve",
                        _multiply(p+"CurveNum", _sum(p+"OnePlusSlope", (slope,), (1,)), _multiply(p+"X2", x, x)),
                        _clampRange(p+"FourWidth", _multiply(p+"FourWidthRaw", width, constant=4), EPSILON, 1e9))
        blend = _sum(p+"Blend", (_sum(p+"StartPlusX", (start, x)), curve), subtract=True)
        descent = _sum(p+"Descent", (peak, _multiply(p+"Drop", slope,
                                                      _sum(p+"PastPeak", (magnitude, peak), subtract=True))),
                       subtract=True)
        positive = _compare(p+"SelectTail", magnitude, _sum(p+"Finish", (peak, width)), blend, descent,
                            operation=4)
        positive = _compare(p+"Select", magnitude, start, magnitude, positive, operation=5)
        rel_out = _multiply(p+"Signed", positive, sign)
    else:
        # コーン: 中心方向からの角度 u=180-|rel|。u<=h で w=1、u>=h+m で w=0、間はsmoothstep。
        distance = _oneMinus(p+"Distance", magnitude, 180)
        t = _multiply(p+"TRaw", _sum(p+"TNum", (_sum(p+"HalfPlusM", (half,), (CONE_FALLOFF,)), distance),
                                     subtract=True), constant=1.0/CONE_FALLOFF)
        t = _clampRange(p+"T", t, 0, 1)
        t2 = _multiply(p+"T2", t, t)
        weight = _multiply(p+"Weight", t2, _oneMinus(p+"ThreeMinus2T", _multiply(p+"TwoT", t, constant=2), 3))
        push = _multiply(p+"Push", _multiply(p+"Amount", half, constant=CONE_SCALE), weight)
        rel_out = _sum(p+"RelOut", (wrapped, push))
    corrected = _sum(p+"World", (signed, rel_out))
    selected = _condition(p+"Bypass", section, 0, corrected, requested)
    radians = _node("unitConversion", p+"Radians", conversionFactor=math.pi/180)
    _connect(selected, radians+".input")
    _connect(radians+".output", output+".rx")
    for attr in ("ry", "rz"):
        cmds.setAttr(output+"."+attr, lock=True)
    return {"group": group, "arm": arm, "source": source, "output": output}


def main(record=True):
    """専用GUIで5列を同じ入力で動かし、上面から録画して独立計算と照合する。

    Args:
        record (bool): True なら録画して検証する。False なら録画せず、タイムラインの
            再生・スクラブでHUDと数値が更新されるシーンを作る。
    """
    if cmds.about(batch=True):
        raise RuntimeError("専用Maya GUIで実行してください。")
    if "sweepComparePanel" in cmds.getPanel(allPanels=True):
        cmds.deleteUI("sweepComparePanel", panel=True)
    if cmds.window("sweepCompareWindow", exists=True):
        cmds.deleteUI("sweepCompareWindow", window=True)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")

    material = cmds.shadingNode("lambert", asShader=True, name="bodyProxyMaterial")
    cmds.setAttr(material+".color", 0.18, 0.22, 0.28, type="double3")
    cmds.setAttr(material+".transparency", 0.55, 0.55, 0.55, type="double3")
    material_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
    _connect(material+".outColor", material_group+".surfaceShader")
    columns = {key: _buildColumn(i, key, color, material_group)
               for i, (key, _, _, color) in enumerate(METHODS)}

    camera, camera_shape = cmds.camera(name="sweepCompareCamera", orthographic=True)
    cmds.setAttr(camera+".translate", 0, 40, 0)
    cmds.setAttr(camera+".rotate", -90, 0, 0)
    cmds.setAttr(camera_shape+".orthographicWidth", SPACING*len(METHODS))
    if cmds.windowPref("sweepCompareWindow", exists=True):
        cmds.windowPref("sweepCompareWindow", remove=True)
    window = cmds.window("sweepCompareWindow", widthHeight=(1800, 760))
    pane = cmds.paneLayout(parent=window)
    panel = cmds.modelPanel("sweepComparePanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", grid=False, cameras=False,
                     joints=True, headsUpDisplay=True, manipulators=False, selectionHiliteDisplay=False)
    cmds.showWindow(window)
    cmds.window(window, edit=True, widthHeight=(1800, 760))
    cmds.setFocus(panel)
    cmds.select(clear=True)
    demo_interactive.clearHuds(window)
    # 上段(section 0〜4)と下段(5〜9)が画面を5列に分けるので、列と方式を対応させる。
    top_rows, bottom_rows = 3, 3
    texts = {}
    for column in range(len(METHODS)):
        for row in range(top_rows):
            name = "sweepTop{}_{}".format(column, row)
            texts[name] = ""
            cmds.headsUpDisplay(name, section=column, block=row, blockSize="large", dataFontSize="large",
                                command=lambda n=name: texts[n])
        for row in range(bottom_rows):
            name = "sweepBottom{}_{}".format(column, row)
            texts[name] = ""
            cmds.headsUpDisplay(name, section=column+5, block=bottom_rows-1-row, blockSize="large",
                                dataFontSize="large", command=lambda n=name: texts[n])

    # 入力アニメーション。relは外向き基準で指定し、実際のrxへ変換して全列に同じキーを打つ。
    count = (len(POSES)-1)*SEGMENT_FRAMES+1
    stages = []
    tracks = []
    for frame in range(count):
        phase = frame/SEGMENT_FRAMES
        index = min(int(phase), len(POSES)-2)
        w = phase-index
        w = w*w*(3-2*w)
        d, orbit, tilt, rel = [a+(b-a)*w for a, b in zip(POSES[index][:4], POSES[index+1][:4])]
        tracks.append((d*math.cos(math.radians(orbit)), -d*math.sin(math.radians(orbit)), tilt, rel))
        stages.append(POSES[index][4] if frame else POSES[0][4])
    reference_center = _node("pointMatrixMult", "inputColumnCenterInArm")
    _connect(columns["input"]["arm"]+".inverseMatrix", reference_center+".inMatrix")
    previous_twist = None
    for frame, (tx, tz, tilt, rel) in enumerate(tracks):
        for column in columns.values():
            for attr, value in (("tx", tx), ("tz", tz), ("rz", tilt)):
                cmds.setKeyframe(column["arm"], attribute=attr, time=frame+1, value=value)
        c = cmds.getAttr(reference_center+".output", time=frame+1)[0]
        twist = math.degrees(math.atan2(-c[2], -c[1]))+rel
        if previous_twist is not None:
            twist += 360*round((previous_twist-twist)/360)
        previous_twist = twist
        for column in columns.values():
            cmds.setKeyframe(column["source"], attribute="rx", time=frame+1, value=twist)
    cmds.playbackOptions(minTime=1, maxTime=count)

    functions = {"nearest": lambda r, l: math.copysign(min(abs(r), l), r),
                 "strict": strictReference, "soft": softReference, "cone": coneReference}
    last = {key: None for key in functions}
    flash = {key: -1 for key in functions}

    def hit(joint, offset):
        """リグに接続しない線分球交差の独立検査。列の原点を球中心とする。"""
        m = cmds.xform(joint, query=True, worldSpace=True, matrix=True)
        origin = (m[12]-offset, m[13], m[14])
        direction = m[4:7]
        t = max(0, min(LENGTH, -sum(a*b for a, b in zip(origin, direction))))
        return sum((a+t*b)**2 for a, b in zip(origin, direction)) < RADIUS**2

    def evaluate(frame):
        """各列の標準DG出力を独立計算・線分球交差・ロック状態で検査する。"""
        demo_interactive.setTime(frame)
        c = cmds.getAttr(reference_center+".output")[0]
        r2 = (RADIUS+GAP)**2-c[0]**2
        rho_value = math.sqrt(max(0, r2))
        dp = math.hypot(c[1], c[2])
        lim = 180-math.degrees(math.asin(min(1, rho_value/dp))) if r2 > 0 and dp > 1e-8 else 180
        reference = math.degrees(math.atan2(-c[2], -c[1]))
        requested_value = cmds.getAttr(columns["input"]["source"]+".rx")
        rel = (requested_value-reference+180) % 360-180
        offset = cmds.getAttr(columns["input"]["group"]+".tx")
        result = {"frame": frame, "stage": stages[frame], "requested_degrees": requested_value,
                  "relative_degrees": rel, "limit_degrees": lim, "section_active": r2 > 0,
                  "input_body_hit": hit(columns["input"]["source"], offset)}
        ok = True
        lines = {"input": ("rel={:+.1f}  L={:.1f}".format(rel, lim),
                           stages[frame],
                           "BODY HIT" if result["input_body_hit"] else "clear")}
        for key, function in functions.items():
            column = columns[key]
            actual = cmds.getAttr(column["output"]+".rx")
            expected = function(rel, lim)
            target = reference+expected if r2 > 0 else requested_value
            error = abs((actual-target+180) % 360-180)
            if key == "nearest" and r2 > 0 and abs(abs(rel)-180) < 1e-6:
                # rel=±180は同じ向き。最近接側の左右はどちらも正解とする。
                error = min(error, abs((actual-(reference-expected)+180) % 360-180))
            step = abs((actual-last[key]+180) % 360-180) if last[key] is not None else 0.0
            last[key] = actual
            body = hit(column["output"], cmds.getAttr(column["group"]+".tx"))
            if step > 30:
                flash[key] = frame+24
            result[key] = {"output_degrees": actual, "relative_output_degrees": expected,
                           "error_degrees": error, "step_degrees": step, "body_hit": body}
            locked = cmds.getAttr(column["output"]+".ry") == 0 and cmds.getAttr(column["output"]+".rz") == 0
            # 非貫通を保証する方式だけ交差を失敗扱いにする。従来とコーンは貫通を許容する。
            ok = ok and error < 1e-3 and locked and (key in ("nearest", "cone") or not body)
            lines[key] = ("out rel={:+.1f}".format(((expected+180) % 360-180) if r2 > 0 else rel),
                          "step {:.1f} deg".format(step)
                          + ("  JUMP!" if frame <= flash[key] and key == "nearest" else ""),
                          "BODY HIT" if body else "clear")
        result["ok"] = ok
        for column, (key, title, formula, _) in enumerate(METHODS):
            texts["sweepTop{}_0".format(column)] = title
            texts["sweepTop{}_1".format(column)] = formula
            texts["sweepTop{}_2".format(column)] = lines[key][0]
            texts["sweepBottom{}_0".format(column)] = lines[key][1] if key != "input" else ""
            texts["sweepBottom{}_1".format(column)] = lines[key][2]
            texts["sweepBottom{}_2".format(column)] = stages[frame] if key == "input" else ""
        for name in texts:
            cmds.headsUpDisplay(name, refresh=True)
        return result

    if not record:
        demo_interactive.attachInteractive(window, count, evaluate, [(last, None), (flash, -1)])
        logger.info("方式比較のシーンを作成しました。タイムラインで再生・スクラブして確認できます。")
        return
    folder = recordVideo("尻尾1軸回避の方式比較: 入力・従来・外側を回す・先回り・コーン押し出し",
                         count, 24, panel, evaluate,
                         ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"), width=1800, height=760)
    if not json.loads((folder/"result.json").read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError("方式比較の検証に失敗: {}".format(folder))
    cmds.file(rename=str(folder/"joint-sweep-compare.ma"))
    cmds.file(save=True, type="mayaAscii")
    (Path(__file__).resolve().parents[1]/".maya-output/verification/latest-joint-sweep-compare.json").write_text(
        json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
    logger.info("方式比較を保存しました: {}".format(folder))


if __name__ == "__main__":
    main()
