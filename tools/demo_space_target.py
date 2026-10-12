"""尻尾1軸回避の簡単な2案を、今の仕組み(rel・H＋UE RBF)と比べる。

シーン・動き・尻尾の入力は demo_joint_chain_rbf の case="mixed" と同じ。

共通の部品:
- 体の反対向きに向くグループ: 前腕の下に置き、お腹(spine1)の球へ aimConstraint で -Y を向ける
  (rotateX だけ。+Y が体と反対の向き)。尻尾の出力ジョイントはこのグループの下に置く。
- 止める角度 L: 肘とお腹の球の距離からドリブンキーで決める。キーは、この動きの中で距離ごとに
  一番広く体が塞いだ範囲(3球を合わせた H の最大+5度)から作る。L = 180 - H。

案1(space): グループの下のコントローラーの rotateX が、そのまま「体の反対向きから何度回したか」。
  rotateX は一周を超えても数え直さないので入った側を保つ。尻尾 = clamp(コントローラー, -L, L)。
案2(target): アニメーターはターゲット(ロケーター)を動かす。グループから見たターゲットの方向の角度
  (-180〜180)を clamp(角度, -L, L) して尻尾をそちらへ向ける。ターゲットが体の真裏を横切ると反対側へ
  切り替わる(どちら側にあるかは見て分かる)。デモではターゲットを入力の尻尾の先端に置く。

リグは標準ノード(aimConstraint・distanceBetween・ドリブンキー・clamp・angleBetween)のみ。
"""

import json
import math
import os
from pathlib import Path

from maya import cmds
import maya.api.OpenMaya as om
from mlib import logger
from demo_top_view_moving_tangent import _node, _connect
from demo_joint_twist_tangent import _sum, _multiply, _condition, _degrees
from demo_joint_sweep_compare import _tail
import demo_joint_chain_rbf as chain
import demo_joint_rbf_pose
from verification_video import recordVideo
import demo_interactive

WINDOW = "chainRbfWindow"
PANEL = "chainRbfPanel"
LIMIT_MARGIN = 5.0
LIMIT_KEYS = 6
METHODS = [
    ("input", "INPUT (red)", "hip/spine0-2/shoulder/upperArm/lowerArm", None),
    ("rbf", "CURRENT: rel/H + 385 poses", "UE RBF, keeps entry side", (1, 0.5, 0.1)),
    ("space", "PLAN 1: control in body space", "tail = clamp(control.rx, -L, L)", (0.1, 1, 0.1)),
    ("target", "PLAN 2: aim at a target", "tail = clamp(angle to target, -L, L)", (0.2, 0.9, 1)),
]
HUD_SECTIONS = (0, 1, 3, 4)


def _bodySpace(prefix, rig):
    """前腕の下に、体の反対向きに向くグループ(rotateX だけ)を作る。

    Returns:
        str: グループ。+Y が体と反対の向き。
    """
    arm = rig["joints"]["l_lowerArm"]
    belly = [ball for ball, _ in rig["balls"] if "belly" in ball][0]
    group = cmds.createNode("transform", name=prefix+"BodySpace_GRP", parent=arm)
    cmds.aimConstraint(belly, group, aimVector=(0, -1, 0), upVector=(1, 0, 0), worldUpType="objectrotation",
                       worldUpObject=arm, worldUpVector=(1, 0, 0), skip=("y", "z"))
    return group


def _limit(prefix, rig, keys):
    """肘とお腹の球の距離から、止める角度 L をドリブンキーで出す。

    Args:
        keys (list[tuple]): (距離, L) の組。

    Returns:
        str: L(度)のプラグ。
    """
    belly = [ball for ball, _ in rig["balls"] if "belly" in ball][0]
    distance = _node("distanceBetween", prefix+"BodyDistance")
    _connect(rig["joints"]["l_lowerArm"]+".worldMatrix[0]", distance+".inMatrix1")
    _connect(belly+".worldMatrix[0]", distance+".inMatrix2")
    holder = cmds.createNode("transform", name=prefix+"Limit", parent=rig["group"])
    cmds.addAttr(holder, longName="limit", attributeType="double", keyable=True)
    for d, value in keys:
        cmds.setDrivenKeyframe(holder+".limit", currentDriver=distance+".distance", driverValue=d, value=value,
                               inTangentType="linear", outTangentType="linear")
    return holder+".limit"


def _clampToLimit(prefix, angle, limit):
    """角度(度)を -L〜L に制限する。"""
    node = _node("clamp", prefix+"Clamp")
    _connect(angle, node+".inputR")
    _connect(limit, node+".maxR")
    _connect(_multiply(prefix+"NegLimit", limit, constant=-1), node+".minR")
    return node+".outputR"


def _drive(prefix, group, angle, color):
    """グループの下に尻尾の出力ジョイントを作り、rotateX に角度(度)をつなぐ。"""
    output = _tail(prefix+"TailOutput_JNT", color, group)
    radians = _node("unitConversion", prefix+"Radians", conversionFactor=math.pi/180)
    _connect(angle, radians+".input")
    _connect(radians+".output", output+".rx")
    for attr in ("ry", "rz"):
        cmds.setAttr(output+"."+attr, lock=True)
    return output


def _targetAngle(prefix, group, target):
    """グループの空間で見たターゲットの方向の角度(+Y から +Z へ、-180〜180、度)。"""
    local = _node("multMatrix", prefix+"TargetToSpace")
    _connect(target+".worldMatrix[0]", local+".matrixIn[0]")
    _connect(group+".worldInverseMatrix[0]", local+".matrixIn[1]")
    point = _node("decomposeMatrix", prefix+"TargetLocal")
    _connect(local+".matrixSum", point+".inputMatrix")
    between = _node("angleBetween", prefix+"TargetAngle", vector1X=0, vector1Y=1, vector1Z=0, vector2X=0)
    _connect(point+".outputTranslateY", between+".vector2Y")
    _connect(point+".outputTranslateZ", between+".vector2Z")
    unsigned = _degrees(prefix+"TargetUnsigned", between+".angle")
    return _condition(prefix+"TargetSigned", point+".outputTranslateZ", 0, unsigned,
                      _multiply(prefix+"TargetNeg", unsigned, constant=-1))


def main(record=True):
    """専用GUIで4列を同じ入力で動かし、正面から録画して検査する。

    Args:
        record (bool): False なら録画せず、タイムラインで確認できるシーンを作る。
    """
    if cmds.about(batch=True):
        raise RuntimeError("専用Maya GUIで実行してください。")
    plugin = str(demo_joint_rbf_pose.PLUGIN).format(cmds.about(majorVersion=True))
    if not cmds.pluginInfo("MayaUERBFPlugin", query=True, loaded=True):
        cmds.loadPlugin(plugin)
    if PANEL in cmds.getPanel(allPanels=True):
        cmds.deleteUI(PANEL, panel=True)
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW, window=True)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")

    material = cmds.shadingNode("lambert", asShader=True, name="bodyProxyMaterial")
    cmds.setAttr(material+".color", 0.18, 0.22, 0.28, type="double3")
    cmds.setAttr(material+".transparency", 0.55, 0.55, 0.55, type="double3")
    material_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
    _connect(material+".outColor", material_group+".surfaceShader")
    rigs = {key: chain._buildRig(key, i, material_group, chain.BODY, len(METHODS))
            for i, (key, *_) in enumerate(METHODS)}
    input_geometry = chain._buildGeometry("input", rigs["input"])
    geometry = chain._buildGeometry("rbf", rigs["rbf"], soft=True)
    rbf_plug, rbf_solver, rbf_grid = chain._buildRbf("rbf", geometry, rigs["rbf"])
    outputs = {"rbf": chain._finish("rbf", rigs["rbf"], geometry, rbf_plug, METHODS[1][3])}

    # 体と腕の動き。
    count = (len(chain.INPUT)-1)*chain.SEGMENT_FRAMES+1
    for rig in rigs.values():
        for joint, attr, amplitude, period, phase, offset in chain.MOTION:
            for frame in range(0, count, 3):
                value = offset+amplitude*math.sin(2*math.pi*frame/period+phase)
                cmds.setKeyframe(rig["joints"][joint], attribute=attr, time=frame+1, value=value)

    # 共通の部品(体の反対向きのグループ)と、止める角度のドリブンキー。キーはこの動きの距離ごとの最大 H から作る。
    spaces = {key: _bodySpace(key, rigs[key]) for key in ("space", "target")}
    samples = []
    rig = rigs["space"]
    belly = [ball for ball, _ in rig["balls"] if "belly" in ball][0]
    for frame in range(0, count, 3):
        cmds.currentTime(frame+1)
        elbow = om.MVector(*cmds.xform(rig["joints"]["l_lowerArm"], query=True, worldSpace=True, translation=True))
        center = om.MVector(*cmds.xform(belly, query=True, worldSpace=True, translation=True))
        _, half, _ = chain.referenceGeometry(rig)
        samples.append(((elbow-center).length(), half))
    lo, hi = min(d for d, _ in samples), max(d for d, _ in samples)
    keys = []
    for k in range(LIMIT_KEYS):
        d = lo+(hi-lo)*k/(LIMIT_KEYS-1)
        width = (hi-lo)/(LIMIT_KEYS-1)
        near = [h for dd, h in samples if abs(dd-d) <= width]
        keys.append((d, 180-(max(near)+LIMIT_MARGIN)))
    limits = {key: _limit(key, rigs[key], keys) for key in ("space", "target")}

    # 案1: コントローラー(rotateX が体の反対向きからの角度)。
    control = cmds.createNode("transform", name="spaceTail_CTRL", parent=spaces["space"])
    outputs["space"] = _drive("space", spaces["space"], _clampToLimit("space", control+".rx", limits["space"]),
                              METHODS[2][3])
    # 案2: ターゲット(列のグループの下のロケーター)。
    target = cmds.spaceLocator(name="targetTail_LOC")[0]
    target = cmds.parent(target, rigs["target"]["group"], relative=True)[0]
    outputs["target"] = _drive("target", spaces["target"],
                               _clampToLimit("target", _targetAngle("target", spaces["target"], target),
                                             limits["target"]), METHODS[3][3])

    # 尻尾の入力。今の仕組みと入力列は rotateX、案1はコントローラー、案2はターゲットの位置に同じ向きを入れる。
    stages = []
    group_x = cmds.getAttr(rigs["target"]["group"]+".tx")
    for frame in range(count):
        phase = frame/chain.SEGMENT_FRAMES
        index = min(int(phase), len(chain.INPUT)-2)
        w = phase-index
        w = w*w*(3-2*w)
        rel = chain.INPUT[index][0]+(chain.INPUT[index+1][0]-chain.INPUT[index][0])*w
        stages.append(chain.INPUT[index][1] if frame else chain.INPUT[0][1])
        outward = cmds.getAttr(input_geometry["outward"], time=frame+1)
        for key in ("input", "rbf", "space", "target"):
            cmds.setKeyframe(rigs[key]["source"], attribute="rx", time=frame+1, value=outward+rel)
        # 案1: 体の反対向きのグループから見た角度。グループの向きは今の仕組みの外向きと少し違うので、
        # 入力の尻尾と同じワールドの向きになるよう、グループに対する角度へ直す。
        cmds.currentTime(frame+1)
        arm_matrix = om.MMatrix(cmds.getAttr(rigs["space"]["joints"]["l_lowerArm"]+".worldMatrix[0]"))
        direction = (om.MVector(0, math.cos(math.radians(outward+rel)), math.sin(math.radians(outward+rel)))
                     * arm_matrix)
        space_matrix = om.MMatrix(cmds.getAttr(spaces["space"]+".worldMatrix[0]")).inverse()
        local = direction*space_matrix
        angle = math.degrees(math.atan2(local.z, local.y))
        # 一周を超える分は、今の rel の回転数をそのまま足して数え直さない。
        angle += 360*round((rel-angle)/360)
        cmds.setKeyframe(control, attribute="rx", time=frame+1, value=angle)
        # 案2: ターゲットを入力の尻尾の先端に置く(列のグループの空間)。
        target_arm = om.MMatrix(cmds.getAttr(rigs["target"]["joints"]["l_lowerArm"]+".worldMatrix[0]"))
        tip = om.MPoint(0, chain.LENGTH*math.cos(math.radians(outward+rel)),
                        chain.LENGTH*math.sin(math.radians(outward+rel)))*target_arm
        for attr, value in zip(("tx", "ty", "tz"), (tip.x-group_x, tip.y, tip.z)):
            cmds.setKeyframe(target, attribute=attr, time=frame+1, value=value)
    cmds.playbackOptions(minTime=1, maxTime=count)

    camera, camera_shape = cmds.camera(name="spaceTargetCamera", orthographic=True)
    cmds.setAttr(camera+".translate", 0, 12.5, 60)
    cmds.setAttr(camera_shape+".orthographicWidth", chain.SPACING*len(METHODS))
    if cmds.windowPref(WINDOW, exists=True):
        cmds.windowPref(WINDOW, remove=True)
    window = cmds.window(WINDOW, widthHeight=(1800, 760))
    pane = cmds.paneLayout(parent=window)
    panel = cmds.modelPanel(PANEL, parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", grid=False, cameras=False,
                     joints=True, headsUpDisplay=True, manipulators=False, selectionHiliteDisplay=False,
                     locators=True)
    cmds.showWindow(window)
    cmds.window(window, edit=True, widthHeight=(1800, 760))
    cmds.setFocus(panel)
    cmds.select(clear=True)
    demo_interactive.clearHuds(window)
    texts = {}
    for column, section in enumerate(HUD_SECTIONS):
        for row in range(3):
            for prefix, base, block in (("chainTop", section, row), ("chainBottom", section+5, 2-row)):
                name = "{}{}_{}".format(prefix, column, row)
                texts[name] = ""
                cmds.headsUpDisplay(name, section=base, block=block, blockSize="large", dataFontSize="large",
                                    command=lambda n=name: texts[n])

    keys_compared = ("rbf", "space", "target")
    last = dict.fromkeys(keys_compared)
    flash = dict.fromkeys(keys_compared, -1)

    def penetration(rig, joint):
        """リグに接続しない線分と球の交差検査。最も深い食い込み(cm)。交差しなければ0。"""
        m = cmds.xform(joint, query=True, worldSpace=True, matrix=True)
        deepest = 0.0
        for ball, radius in rig["balls"]:
            c = cmds.xform(ball, query=True, worldSpace=True, translation=True)
            o = [a-b for a, b in zip(m[12:15], c)]
            t = max(0, min(chain.LENGTH, -sum(a*b for a, b in zip(o, m[4:7]))))
            deepest = max(deepest, radius-math.sqrt(sum((a+t*b)**2 for a, b in zip(o, m[4:7]))))
        return deepest

    def evaluate(frame):
        """各列の出力・食い込み・変化量を記録する。"""
        demo_interactive.setTime(frame)
        requested = cmds.getAttr(rigs["input"]["source"]+".rx")
        outward, half, _ = chain.referenceGeometry(rigs["input"])
        rel = requested-outward if outward is not None else None
        result = {"frame": frame, "stage": stages[frame], "relative_degrees": rel, "half_width_degrees": half,
                  "input_penetration_cm": penetration(rigs["input"], rigs["input"]["source"]),
                  "limit_degrees": cmds.getAttr(limits["space"]), "control_degrees": cmds.getAttr(control+".rx"),
                  "target_angle_degrees": cmds.getAttr("targetTargetSigned.outColorR")}
        lines = {}
        for key in keys_compared:
            m = cmds.xform(outputs[key], query=True, worldSpace=True, matrix=True)
            arm = om.MMatrix(cmds.xform(rigs[key]["joints"]["l_lowerArm"], query=True, worldSpace=True, matrix=True))
            local = om.MVector(*m[4:7])*arm.inverse()
            depth = penetration(rigs[key], outputs[key])
            # 前腕の空間で、尻尾の回転面(YZ)の角度。列どうしで比べられる。
            angle = math.degrees(math.atan2(local.z, local.y))
            step = abs((angle-last[key]+180) % 360-180) if last[key] is not None else 0.0
            last[key] = angle
            if step > 15:
                flash[key] = frame+24
            result[key] = {"world_angle_degrees": angle, "penetration_cm": depth, "step_degrees": step}
            lines[key] = ("BODY HIT {:.2f}cm".format(depth) if depth > 0 else "clear") \
                + "  step {:.1f}".format(step) + ("  JUMP!" if frame <= flash[key] else "")
        rbf_weights = sum(cmds.getAttr(rbf_solver+".outputs[{}]".format(i)) for i in range(len(rbf_grid)))
        result["ok"] = result["rbf"]["penetration_cm"] <= 0 and abs(rbf_weights-1) < 0.05
        info = {
            "input": ("rel={}  H={:.1f}".format("{:+.1f}".format(rel) if rel is not None else "-", half),
                      "BODY HIT" if result["input_penetration_cm"] > 0 else "clear", stages[frame]),
            "rbf": ("", lines["rbf"], ""),
            "space": ("control.rx {:+.1f}  L {:.1f}".format(result["control_degrees"], result["limit_degrees"]),
                      lines["space"], "L from elbow-belly distance (driven key)"),
            "target": ("target angle {:+.1f}  L {:.1f}".format(result["target_angle_degrees"],
                                                                result["limit_degrees"]),
                       lines["target"], "target = input tail tip"),
        }
        for column, (key, title, formula, _) in enumerate(METHODS):
            texts["chainTop{}_0".format(column)] = title
            texts["chainTop{}_1".format(column)] = formula
            texts["chainTop{}_2".format(column)] = info[key][0]
            texts["chainBottom{}_0".format(column)] = info[key][1]
            texts["chainBottom{}_1".format(column)] = info[key][2] if key != "input" else ""
            texts["chainBottom{}_2".format(column)] = info[key][2] if key == "input" else ""
        for name in texts:
            cmds.headsUpDisplay(name, refresh=True)
        return result

    if not record:
        demo_interactive.attachInteractive(window, count, evaluate, [(last, None), (flash, -1)])
        logger.info("案1・案2のシーンを作成しました。タイムラインで確認できます。")
        return
    folder = recordVideo("尻尾1軸回避: 案1（体基準の空間のコントローラー）と案2（ターゲット）", count, 24, panel, evaluate,
                         ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"), width=1800, height=760)
    cmds.file(rename=str(folder/"space-target.ma"))
    cmds.file(save=True, type="mayaAscii")
    (Path(__file__).resolve().parents[1]/".maya-output/verification/latest-space-target.json").write_text(
        json.dumps({"folder": str(folder), "limit_keys": keys}, ensure_ascii=False), encoding="utf-8")
    if not json.loads((folder/"result.json").read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError("案1・案2の検証に失敗: {}".format(folder))
    logger.info("案1・案2の検証を保存しました: {}".format(folder))


if __name__ == "__main__":
    main()
