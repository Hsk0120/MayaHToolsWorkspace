"""UEのRBFソルバー(MayaUERBFPlugin)のポーズ補間で、尻尾の rotateX を避ける検証。

腕ローカルXの rotateX だけで尻尾を回し、球近似の体を避ける。補正を計算式で
直接求める代わりに、「入力の相対角 rel と禁止範囲の半幅 h の組 → 出力の相対角」
をポーズとして並べ、UERBFSolverNode の重みで補間する。

- ドライバー: composeMatrix の移動値 (rel/20, h/10, 0)。inputMode=Translation、
  Euclidean距離。rel は外向き基準の折り返さない相対角なので、入った側を保つ。
- ポーズ: rel=-340〜340(20度刻み) × h=0〜60(10度刻み) の格子。各ポーズの値は
  なだらかに避ける出力 start+m*depth/(depth+m)(start=L-m、m=min(40,h)、L=180-h)。
  値はデータなので、ポーズごとに手で直せる。
- ソルバー: mode=Additive(連立方程式を解かず、ガウス関数の重みをそのまま使う)、
  半径0.7。Interpolative は格子が大きいと重みが0になる区間や階段状の出力が出るため使わない。
- 出力: Σ 重み_i × 値_i ÷ Σ 重み_i。補間は
  h が小さい所で接線を数度越えるため、最後に clamp(出力, -L, L) を安全装置として掛ける。

UEのソルバーは MetaHuman for Maya 同梱のプラグインで、実行時に明示的にロードする。
Pythonは入力アニメーションと検査用で、リグは標準ノードとUERBFSolverNodeで評価する。
"""

import json
import math
import os
from pathlib import Path

from maya import cmds
from mlib import logger
from demo_top_view_moving_tangent import _node, _connect
from demo_joint_twist_tangent import _sum, _multiply, _condition, _sqrt, _degrees
from demo_joint_sweep_compare import _tail, _oneMinus, _divide, _clampRange, RADIUS, GAP, LENGTH
import demo_joint_side_keep
from verification_video import recordVideo
import demo_interactive

PLUGIN = (Path(__file__).resolve().parents[1]/"maya/external/MetaHumanForMaya/lib/MayaUERBFPlugin/2.0.5"
          "/platform-windows/maya-{}/lib/MayaUERBFPlugin.mll")
REL_STEP = 20.0
H_STEP = 10.0
REL_RANGE = 17
H_RANGE = 6
RBF_RADIUS = 0.7
SOFT_MARGIN = 40.0
SPACING = demo_joint_side_keep.SPACING
POSES = demo_joint_side_keep.POSES

METHODS = [
    ("input", "INPUT (red)", "no correction", None),
    ("keep", "SPHERE: tangent stop", "clamp(rel,-L,L)", (1, 0.5, 0.1)),
    ("rbf", "UE RBF: pose interpolation", "clamp(sum(w_i * pose_i), -L, L)", (0.1, 1, 0.1)),
]
HUD_SECTIONS = (0, 2, 4)


def poseValue(rel, h):
    """ポーズに置く出力の相対角。なだらかに避ける式で初期値を作る。度。"""
    limit = 180-h
    margin = min(SOFT_MARGIN, h)
    start = limit-margin
    x = abs(rel)
    if x > start:
        depth = x-start
        x = start+margin*depth/max(depth+margin, 1e-4)
    return math.copysign(x, rel)


def poseGrid():
    """ポーズの格子。(ドライバーx, ドライバーy, 出力の相対角) の一覧。"""
    return [(i, j, poseValue(i*REL_STEP, j*H_STEP))
            for i in range(-REL_RANGE, REL_RANGE+1) for j in range(H_RANGE+1)]


def _buildColumn(index, key, color, material_group):
    """RBF列の体・腕・入力尾・補正尾、球の幾何DGとUERBFSolverNodeを作る。

    Returns:
        dict: group, arm, source, output, solver, count(ポーズ数)。
    """
    p = key
    group = cmds.createNode("transform", name=p+"Column_GRP")
    cmds.setAttr(group+".tx", (index-(len(METHODS)-1)/2.0)*SPACING+demo_joint_side_keep.BODY_SHIFT)
    sphere = cmds.polySphere(name=p+"BodySphere", radius=RADIUS, subdivisionsX=40,
                            subdivisionsY=24, constructionHistory=False)[0]
    sphere = cmds.parent(sphere, group, relative=True)[0]
    cmds.sets(sphere, edit=True, forceElement=material_group)
    arm = cmds.createNode("joint", name=p+"Arm_JNT", parent=group)
    cmds.setAttr(arm+".jointOrientZ", 90)
    cmds.setAttr(arm+".radius", 0.15)
    source = _tail(p+"TailInput_JNT", (1, 0.1, 0.1), arm)
    output = _tail(p+"TailOutput_JNT", color, arm)

    # 球の断面円から接線角Lと半幅h、連続な外向き角と折り返さない相対角を求める(球の接線止めと同じ)。
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
    half = _oneMinus(p+"Half", limit, 180)
    inward = _node("angleBetween", p+"InwardAngle", vector1X=0, vector1Y=1, vector1Z=0, vector2X=0)
    _connect(cy, inward+".vector2Y")
    _connect(cz, inward+".vector2Z")
    unsigned = _degrees(p+"InUnsigned", inward+".angle")
    signed = _condition(p+"InSigned", cz, 0, unsigned, _multiply(p+"InNeg", unsigned, constant=-1))
    outward = _sum(p+"Outward", (signed,), (180,))
    requested = _degrees(p+"Requested", source+".rx")
    relative = _sum(p+"Relative", (requested, outward), subtract=True)

    # ドライバー行列。移動値に (rel/20, h/10) を入れ、格子の間隔を1にそろえる。
    driver = _node("composeMatrix", p+"Driver")
    _connect(_multiply(p+"DriverX", relative, constant=1/REL_STEP), driver+".inputTranslateX")
    _connect(_multiply(p+"DriverY", half, constant=1/H_STEP), driver+".inputTranslateY")
    solver = _node("UERBFSolverNode", p+"PoseSolver", mode=0, inputMode=0, distanceMethod=0, functionType=0,
                   normalizeMethod=1, automaticRadius=False, radius=RBF_RADIUS)
    _connect(driver+".outputMatrix", solver+".inputs[0]")
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    cmds.setAttr(solver+".inputsRest[0]", identity, type="matrix")
    blend = _node("plusMinusAverage", p+"PoseBlendSum")
    total = _node("plusMinusAverage", p+"WeightSum")
    grid = poseGrid()
    for i, (x, y, value) in enumerate(grid):
        matrix = identity[:12]+[x, y, 0, 1]
        cmds.setAttr(solver+".targets[{}].targetValues[0]".format(i), matrix, type="matrix")
        cmds.setAttr(solver+".targets[{}].targetName".format(i), "rel{:+d}_h{}".format(int(x*REL_STEP),
                                                                                    int(y*H_STEP)), type="string")
        weighted = _node("multDoubleLinear", p+"Pose{}".format(i), input2=value)
        _connect(solver+".outputs[{}]".format(i), weighted+".input1")
        _connect(weighted+".output", blend+".input1D[{}]".format(i))
        _connect(solver+".outputs[{}]".format(i), total+".input1D[{}]".format(i))
    # ソルバーの正規化後も合計がわずかに1からずれるので、重みの合計で割る。
    normalized = _divide(p+"PoseBlend", blend+".output1D", _clampRange(p+"WeightSumSafe", total+".output1D", 1e-6, 1e9))
    # 補間の行き過ぎで接線を越えないよう、標準ノードで -L〜L に制限する。
    guard = _node("clamp", p+"Guard")
    _connect(normalized, guard+".inputR")
    _connect(limit, guard+".maxR")
    _connect(_multiply(p+"NegLimit", limit, constant=-1), guard+".minR")
    corrected = _sum(p+"World", (outward, guard+".outputR"))
    radians = _node("unitConversion", p+"Radians", conversionFactor=math.pi/180)
    _connect(corrected, radians+".input")
    _connect(radians+".output", output+".rx")
    for attr in ("ry", "rz"):
        cmds.setAttr(output+"."+attr, lock=True)
    return {"group": group, "arm": arm, "source": source, "output": output, "solver": solver,
            "blend": normalized, "count": len(grid)}


def main(record=True):
    """専用GUIで3列を同じ入力で動かし、上面から録画して検査する。

    Args:
        record (bool): True なら録画して検証する。False なら録画せず、タイムラインの
            再生・スクラブでHUDと数値が更新されるシーンを作る。
    """
    if cmds.about(batch=True):
        raise RuntimeError("専用Maya GUIで実行してください。")
    plugin = str(PLUGIN).format(cmds.about(majorVersion=True))
    if not cmds.pluginInfo("MayaUERBFPlugin", query=True, loaded=True):
        cmds.loadPlugin(plugin)
    if "rbfPosePanel" in cmds.getPanel(allPanels=True):
        cmds.deleteUI("rbfPosePanel", panel=True)
    if cmds.window("rbfPoseWindow", exists=True):
        cmds.deleteUI("rbfPoseWindow", window=True)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")

    material = cmds.shadingNode("lambert", asShader=True, name="bodyProxyMaterial")
    cmds.setAttr(material+".color", 0.18, 0.22, 0.28, type="double3")
    cmds.setAttr(material+".transparency", 0.55, 0.55, 0.55, type="double3")
    material_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
    _connect(material+".outColor", material_group+".surfaceShader")
    columns = {}
    for i, (key, _, _, color) in enumerate(METHODS):
        if key == "rbf":
            columns[key] = _buildColumn(i, key, color, material_group)
        else:
            columns[key] = demo_joint_side_keep._buildColumn(i, key, color, material_group)

    camera, camera_shape = cmds.camera(name="rbfPoseCamera", orthographic=True)
    cmds.setAttr(camera+".translate", 0, 40, 0)
    cmds.setAttr(camera+".rotate", -90, 0, 0)
    cmds.setAttr(camera_shape+".orthographicWidth", SPACING*len(METHODS))
    if cmds.windowPref("rbfPoseWindow", exists=True):
        cmds.windowPref("rbfPoseWindow", remove=True)
    window = cmds.window("rbfPoseWindow", widthHeight=(1800, 760))
    pane = cmds.paneLayout(parent=window)
    panel = cmds.modelPanel("rbfPosePanel", parent=pane, camera=camera, menuBarVisible=False)
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
            for prefix, base, block in (("rbfTop", section, row), ("rbfBottom", section+5, rows-1-row)):
                name = "{}{}_{}".format(prefix, column, row)
                texts[name] = ""
                cmds.headsUpDisplay(name, section=base, block=block, blockSize="large", dataFontSize="large",
                                    command=lambda n=name: texts[n])

    count = (len(POSES)-1)*demo_joint_side_keep.SEGMENT_FRAMES+1
    stages = []
    tracks = []
    for frame in range(count):
        phase = frame/demo_joint_side_keep.SEGMENT_FRAMES
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

    last = {"keep": None, "rbf": None}
    flash = {"keep": -1, "rbf": -1}
    rbf = columns["rbf"]

    def hit(joint, offset):
        """リグに接続しない線分球交差の独立検査。列の原点を球中心とする。"""
        m = cmds.xform(joint, query=True, worldSpace=True, matrix=True)
        origin = (m[12]-offset, m[13], m[14])
        direction = m[4:7]
        t = max(0, min(LENGTH, -sum(a*b for a, b in zip(origin, direction))))
        return sum((a+t*b)**2 for a, b in zip(origin, direction)) < RADIUS**2

    def evaluate(frame):
        """球列は計算式と照合し、RBF列は重みの合計・式との差・交差・連続性を記録する。"""
        demo_interactive.setTime(frame)
        c = cmds.getAttr(reference_center+".output")[0]
        r2 = (RADIUS+GAP)**2-c[0]**2
        rho_value = math.sqrt(max(0, r2))
        dp = math.hypot(c[1], c[2])
        lim = 180-math.degrees(math.asin(min(1, rho_value/dp))) if r2 > 0 and dp > 1e-8 else 180
        outward = 180+math.degrees(math.atan2(c[2], c[1]))
        requested_value = cmds.getAttr(columns["input"]["source"]+".rx")
        rel = requested_value-outward
        offset = cmds.getAttr(columns["input"]["group"]+".tx")
        result = {"frame": frame, "stage": stages[frame], "requested_degrees": requested_value,
                  "relative_degrees": rel, "limit_degrees": lim,
                  "input_body_hit": hit(columns["input"]["source"], offset)}

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

        actual = cmds.getAttr(rbf["output"]+".rx")
        weights = [cmds.getAttr(rbf["solver"]+".outputs[{}]".format(i)) for i in range(rbf["count"])]
        out_rel = actual-outward
        raw = cmds.getAttr(rbf["blend"])
        formula = poseValue(rel, 180-lim)
        rbf_hit = hit(rbf["output"], cmds.getAttr(rbf["group"]+".tx"))
        rbf_step = abs((actual-last["rbf"]+180) % 360-180) if last["rbf"] is not None else 0.0
        last["rbf"] = actual
        active = sorted(range(len(weights)), key=lambda i: -weights[i])[:2]
        grid = poseGrid()
        result["rbf"] = {"output_degrees": actual, "relative_output_degrees": out_rel,
                         "formula_relative_degrees": formula, "raw_relative_degrees": raw,
                         "guard_active": abs(raw) > lim, "difference_degrees": out_rel-formula,
                         "weight_sum": sum(weights), "step_degrees": rbf_step, "body_hit": rbf_hit,
                         "clearance_degrees": lim-abs(out_rel) if r2 > 0 else None}
        for key, step in (("keep", keep_step), ("rbf", rbf_step)):
            if step > 30:
                flash[key] = frame+24
        locked = all(cmds.getAttr(columns[k]["output"]+"."+a) == 0 for k in ("keep", "rbf") for a in ("ry", "rz"))
        # RBFは補間なので式との一致は求めず、重みの正規化・非交差・連続性を保証として検査する。
        result["ok"] = (keep_error < 1e-3 and locked and not keep_hit and not rbf_hit
                        and abs(sum(weights)-1) < 0.05 and rbf_step < 30)

        lines = {
            "input": ("rel={:+.1f}  L={:.1f}  h={:.1f}".format(rel, lim, 180-lim),
                      "BODY HIT" if result["input_body_hit"] else "clear",
                      "{} poses: rel -340..340 x h 0..60".format(rbf["count"])),
            "keep": ("out {:+.1f}".format(expected),
                     ("BODY HIT" if keep_hit else "clear")
                     + "  step {:.1f}".format(keep_step) + ("  JUMP!" if frame <= flash["keep"] else ""),
                     ""),
            "rbf": ("out {:+.1f}  formula {:+.1f}{}".format(out_rel, formula, "  GUARD" if abs(raw) > lim else ""),
                    ("BODY HIT" if rbf_hit else "clear")
                    + "  step {:.1f}".format(rbf_step) + ("  JUMP!" if frame <= flash["rbf"] else ""),
                    "top poses " + ", ".join("({:+.0f},{:.0f}) {:.2f}".format(grid[i][0]*REL_STEP,
                                                                               grid[i][1]*H_STEP, weights[i])
                                             for i in active)),
        }
        for column, (key, title, formula_text, _) in enumerate(METHODS):
            texts["rbfTop{}_0".format(column)] = title
            texts["rbfTop{}_1".format(column)] = formula_text
            texts["rbfTop{}_2".format(column)] = lines[key][0]
            texts["rbfBottom{}_0".format(column)] = lines[key][1]
            texts["rbfBottom{}_1".format(column)] = lines[key][2]
            texts["rbfBottom{}_2".format(column)] = stages[frame] if key == "input" else ""
        for name in texts:
            cmds.headsUpDisplay(name, refresh=True)
        return result

    if not record:
        demo_interactive.attachInteractive(window, count, evaluate, [(last, None), (flash, -1)])
        logger.info("UE RBFのポーズ補間のシーンを作成しました。タイムラインで再生・スクラブして確認できます。")
        return
    folder = recordVideo("尻尾1軸回避: UE RBFのポーズ補間（球の接線止めとの比較）",
                         count, 24, panel, evaluate,
                         ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"), width=1800, height=760)
    cmds.file(rename=str(folder/"joint-rbf-pose.ma"))
    cmds.file(save=True, type="mayaAscii")
    (Path(__file__).resolve().parents[1]/".maya-output/verification/latest-joint-rbf-pose.json").write_text(
        json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
    if not json.loads((folder/"result.json").read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError("UE RBFの検証に失敗: {}".format(folder))
    logger.info("UE RBFの検証を保存しました: {}".format(folder))


if __name__ == "__main__":
    main()
