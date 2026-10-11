"""尻尾ジョイントの1軸回避で、入った側の接線を保持してフリップを防ぐ検証。

腕ローカルXの rotateX だけで尻尾を回し、球近似の体を接線で止める。従来の
両方向版は相対角を -180〜180 に折り返してから clamp(rel, -L, L) するため、
入力が体の中心方向(rel=±180)を越えた瞬間に左右の接線が入れ替わる。

入った側を保持する版は、外向きの角度を連続な値で求め、相対角を折り返さずに
clamp(rel, -L, L) する。+側から入れば rel は L より大きいまま増え続けるので
+側の接線に、-側から入れば -L より小さいまま -側の接線に止まり続ける。
状態を持たないので、タイムラインをどこへ飛ばしても同じ結果になる。

外向きの角度は「腕から見た体の中心方向」の反対向き。体の中心方向が腕Y軸の
+側にある前提で 180 + atan2(cz, cy) とし、cy<=0 側へ回り込むと不連続になる。

列は 入力・従来・入った側を保持 の3つ。Maya標準ノードのみで評価し、Pythonは
入力アニメーションと検査用。
"""

import json
import math
import os
from pathlib import Path

from maya import cmds
from mlib import logger
from demo_top_view_moving_tangent import _node, _connect
from demo_joint_twist_tangent import _sum, _multiply, _condition, _sqrt, _degrees
from demo_joint_sweep_compare import _tail, _oneMinus, RADIUS, GAP, LENGTH
from verification_video import recordVideo
import demo_interactive

SEGMENT_FRAMES = 30
SPACING = 26.0
BODY_SHIFT = -5.0

# (肘距離cm, 円周位置deg, 腕傾斜deg, 外向き基準の入力rel deg, 段階名)
POSES = [
    (6.5, 0, 0, -40, "1 INITIAL"),
    (6.5, 0, 0, -40, "2 ENTER FROM +"),
    (6.5, 0, 0, 100, "2 ENTER FROM +"),
    (6.5, 0, 0, 180, "2 ENTER FROM +"),
    (6.5, 0, 0, 205, "2 ENTER FROM +"),
    (6.5, 0, 0, 205, "3 BACK"),
    (6.5, 0, 0, -40, "3 BACK"),
    (6.5, 0, 0, -40, "4 ENTER FROM -"),
    (6.5, 0, 0, -180, "4 ENTER FROM -"),
    (6.5, 0, 0, -205, "4 ENTER FROM -"),
    (6.5, 0, 0, -205, "5 BACK"),
    (6.5, 0, 0, 170, "6 ELBOW MOVES (+)"),
    (4.0, 0, 0, 170, "6 ELBOW MOVES (+)"),
    (6.0, 30, 0, 190, "6 ELBOW MOVES (+)"),
    (4.0, -30, 0, 170, "6 ELBOW MOVES (+)"),
    (4.0, 0, 0, 190, "6 ELBOW MOVES (+)"),
    (5.0, 0, 0, 170, "7 ARM TILT"),
    (5.0, 0, 40, 170, "7 ARM TILT"),
    (5.0, 0, 0, 170, "8 KEEP TWISTING +"),
    (5.0, 0, 0, 290, "8 KEEP TWISTING +"),
    (5.0, 0, 0, 290, "9 RETURN"),
    (6.5, 0, 0, -40, "9 RETURN"),
]

# 列の並び。(キー, 見出し, 式の要約, 出力の色)
METHODS = [
    ("input", "INPUT (red)", "no correction", None),
    ("nearest", "OLD: nearest side", "clamp(wrap180(rel),-L,L)", (1, 0.5, 0.1)),
    ("keep", "NEW: keep entry side", "clamp(rel,-L,L), rel not wrapped", (0.1, 1, 0.1)),
]
# HUDの5区画のうち、列の中心に近い区画(左・中央・右)を使う。
HUD_SECTIONS = (0, 2, 4)


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

    # 外向き = 180 + (腕Y軸から体の中心方向までの符号付き角度)。体が腕Yの+側にある間は連続。
    inward = _node("angleBetween", p+"InwardAngle", vector1X=0, vector1Y=1, vector1Z=0, vector2X=0)
    _connect(cy, inward+".vector2Y")
    _connect(cz, inward+".vector2Z")
    unsigned = _degrees(p+"InUnsigned", inward+".angle")
    signed = _condition(p+"InSigned", cz, 0, unsigned, _multiply(p+"InNeg", unsigned, constant=-1))
    outward = _sum(p+"Outward", (signed,), (180,))
    requested = _degrees(p+"Requested", source+".rx")
    relative = _sum(p+"Relative", (requested, outward), subtract=True)

    if key == "nearest":
        # 従来: -180〜180 へ折り返してから接線で止める。
        wrapped = _condition(p+"WrapAbove", relative, 180, _sum(p+"Minus360", (relative,), (-360,)), relative)
        relative = _condition(p+"WrapBelow", relative, -180, _sum(p+"Plus360", (relative,), (360,)), wrapped,
                              operation=4)
    # 折り返さない相対角を -L〜L に制限する。入ってきた側の接線に止まり続ける。
    clamp = _node("clamp", p+"Clamp")
    _connect(relative, clamp+".inputR")
    _connect(limit, clamp+".maxR")
    _connect(_multiply(p+"NegLimit", limit, constant=-1), clamp+".minR")
    corrected = _sum(p+"World", (outward, clamp+".outputR"))
    selected = _condition(p+"Bypass", section, 0, corrected, requested)
    radians = _node("unitConversion", p+"Radians", conversionFactor=math.pi/180)
    _connect(selected, radians+".input")
    _connect(radians+".output", output+".rx")
    for attr in ("ry", "rz"):
        cmds.setAttr(output+"."+attr, lock=True)
    return {"group": group, "arm": arm, "source": source, "output": output}


def main(record=True):
    """専用GUIで3列を同じ入力で動かし、上面から録画して独立計算と照合する。

    Args:
        record (bool): True なら録画して検証する。False なら録画せず、タイムラインの
            再生・スクラブでHUDと数値が更新されるシーンを作る。
    """
    if cmds.about(batch=True):
        raise RuntimeError("専用Maya GUIで実行してください。")
    if "sideKeepPanel" in cmds.getPanel(allPanels=True):
        cmds.deleteUI("sideKeepPanel", panel=True)
    if cmds.window("sideKeepWindow", exists=True):
        cmds.deleteUI("sideKeepWindow", window=True)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")

    material = cmds.shadingNode("lambert", asShader=True, name="bodyProxyMaterial")
    cmds.setAttr(material+".color", 0.18, 0.22, 0.28, type="double3")
    cmds.setAttr(material+".transparency", 0.55, 0.55, 0.55, type="double3")
    material_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
    _connect(material+".outColor", material_group+".surfaceShader")
    columns = {key: _buildColumn(i, key, color, material_group)
               for i, (key, _, _, color) in enumerate(METHODS)}

    camera, camera_shape = cmds.camera(name="sideKeepCamera", orthographic=True)
    cmds.setAttr(camera+".translate", 0, 40, 0)
    cmds.setAttr(camera+".rotate", -90, 0, 0)
    cmds.setAttr(camera_shape+".orthographicWidth", SPACING*len(METHODS))
    if cmds.windowPref("sideKeepWindow", exists=True):
        cmds.windowPref("sideKeepWindow", remove=True)
    window = cmds.window("sideKeepWindow", widthHeight=(1800, 760))
    pane = cmds.paneLayout(parent=window)
    panel = cmds.modelPanel("sideKeepPanel", parent=pane, camera=camera, menuBarVisible=False)
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
            for prefix, base, block in (("keepTop", section, row), ("keepBottom", section+5, rows-1-row)):
                name = "{}{}_{}".format(prefix, column, row)
                texts[name] = ""
                cmds.headsUpDisplay(name, section=base, block=block, blockSize="large", dataFontSize="large",
                                    command=lambda n=name: texts[n])

    # 入力アニメーション。relは外向き基準(折り返さない)で指定し、連続な外向き角へ足してrxにする。
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
    for frame, (tx, tz, tilt, rel) in enumerate(tracks):
        for column in columns.values():
            for attr, value in (("tx", tx), ("tz", tz), ("rz", tilt)):
                cmds.setKeyframe(column["arm"], attribute=attr, time=frame+1, value=value)
        c = cmds.getAttr(reference_center+".output", time=frame+1)[0]
        twist = 180+math.degrees(math.atan2(c[2], c[1]))+rel
        for column in columns.values():
            cmds.setKeyframe(column["source"], attribute="rx", time=frame+1, value=twist)
    cmds.playbackOptions(minTime=1, maxTime=count)

    last = {"nearest": None, "keep": None}
    flash = {"nearest": -1, "keep": -1}

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
        outward = 180+math.degrees(math.atan2(c[2], c[1]))
        requested_value = cmds.getAttr(columns["input"]["source"]+".rx")
        rel = requested_value-outward
        wrapped = (rel+180) % 360-180
        offset = cmds.getAttr(columns["input"]["group"]+".tx")
        result = {"frame": frame, "stage": stages[frame], "requested_degrees": requested_value,
                  "relative_degrees": rel, "wrapped_relative_degrees": wrapped, "limit_degrees": lim,
                  "section_active": r2 > 0, "input_body_hit": hit(columns["input"]["source"], offset)}
        ok = True
        lines = {"input": ("rel={:+.1f}  L={:.1f}".format(rel, lim),
                           "BODY HIT" if result["input_body_hit"] else "clear")}
        for key, value in (("nearest", wrapped), ("keep", rel)):
            column = columns[key]
            actual = cmds.getAttr(column["output"]+".rx")
            expected = max(-lim, min(lim, value))
            target = outward+expected if r2 > 0 else requested_value
            error = abs((actual-target+180) % 360-180)
            if key == "nearest" and r2 > 0 and abs(abs(wrapped)-180) < 1e-6:
                # rel=±180は同じ向き。最近接側の左右はどちらも正解とする。
                error = min(error, abs((actual-(outward-expected)+180) % 360-180))
            step = abs((actual-last[key]+180) % 360-180) if last[key] is not None else 0.0
            last[key] = actual
            body = hit(column["output"], cmds.getAttr(column["group"]+".tx"))
            if step > 30:
                flash[key] = frame+24
            result[key] = {"output_degrees": actual, "relative_output_degrees": expected,
                           "error_degrees": error, "step_degrees": step, "body_hit": body}
            locked = cmds.getAttr(column["output"]+".ry") == 0 and cmds.getAttr(column["output"]+".rz") == 0
            ok = ok and error < 1e-3 and locked and not body
            if r2 <= 0:
                side = "no section: input"
            elif value > lim:
                side = "+ tangent"
            elif value < -lim:
                side = "- tangent"
            else:
                side = "free"
            lines[key] = ("rel={:+.1f} -> out {:+.1f}".format(value, expected),
                          "{}  step {:.1f}".format(side, step) + ("  JUMP!" if frame <= flash[key] else ""))
        result["ok"] = ok
        for column, (key, title, formula, _) in enumerate(METHODS):
            texts["keepTop{}_0".format(column)] = title
            texts["keepTop{}_1".format(column)] = formula
            texts["keepTop{}_2".format(column)] = lines[key][0]
            texts["keepBottom{}_0".format(column)] = lines[key][1]
            texts["keepBottom{}_1".format(column)] = "L = 180 - asin(rho/d)" if key == "input" else ""
            texts["keepBottom{}_2".format(column)] = stages[frame] if key == "input" else ""
        for name in texts:
            cmds.headsUpDisplay(name, refresh=True)
        return result

    if not record:
        demo_interactive.attachInteractive(window, count, evaluate, [(last, None), (flash, -1)])
        logger.info("入った側の保持のシーンを作成しました。タイムラインで再生・スクラブして確認できます。")
        return
    folder = recordVideo("尻尾1軸回避: 入った側の接線を保持（従来との比較）",
                         count, 24, panel, evaluate,
                         ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"), width=1800, height=760)
    if not json.loads((folder/"result.json").read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError("入った側の保持の検証に失敗: {}".format(folder))
    cmds.file(rename=str(folder/"joint-side-keep.ma"))
    cmds.file(save=True, type="mayaAscii")
    (Path(__file__).resolve().parents[1]/".maya-output/verification/latest-joint-side-keep.json").write_text(
        json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
    logger.info("入った側の保持の検証を保存しました: {}".format(folder))


if __name__ == "__main__":
    main()
