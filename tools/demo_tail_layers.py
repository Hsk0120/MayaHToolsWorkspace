"""全身骨格(Aポーズ)の左右6本の尻尾を、効果ごとの関節を重ねたレイヤー構造で作り、ON/OFF で確かめる。

尻尾ごとに、付け根の骨(upperarm・lowerarm)の子として次の関節を重ねる。関節を重ねる順番は、回転の
順序(打ち消しは X → Y の順に戻す)に合わせている。全部 ON のとき、demo_tail_twist_cancel の
「D＋前腕のコーン＋3本共通の体の回避」と同じ向きになる。

    elbowLayer   肘のスイング打ち消し  ry = -肘の曲げ × elbowCancel(右は +。jointOrientX = 180)
    twistLayer   ツイスト打ち消し      rx = -ひねり × twistCancel(upperarm.rx、肘・手首は + lowerarm.rx)
    avoidLayer   体の食い込み避け      rx = Δ × bodyAvoid(3本共通、tail_shared_avoid)
    restLayer    初期の向き            rx = REST_RX(-120)
    tail         前腕のコーン          回転 = (前腕の軸から押し出した向き) × forearmCone(肘・手首の尻尾)

スイッチは tailLayers_CTRL の twistCancel・elbowCancel・forearmCone・bodyAvoid(0〜1)。
showStages で、同じ付け根から段階ごとの尻尾(並列のジョイント構造)を細い線で並べて表示する。
灰 = 素の状態、水色 = ＋ツイスト打ち消し、緑 = ＋肘のスイング打ち消し、橙 = ＋前腕のコーン。

体の食い込み避けの Δ は、ツイストと肘の打ち消しが ON(3本が平行)の前提で計算する。
"""

import json
import math
import os
from pathlib import Path

from maya import cmds
import maya.api.OpenMaya as om
from mlib import logger
from mlrig.examples import humanoid
from mlrig.setups.coneReader import ConeReader
from verification_video import recordVideo
import demo_interactive
import demo_tail_twist_cancel as base

WINDOW = "tailLayersWindow"
PANEL = "tailLayersPanel"
CONTROL = "tailLayers_CTRL"
SWITCHES = ("twistCancel", "elbowCancel", "forearmCone", "bodyAvoid")
# 並列表示の段階。(名前, 有効にする効果, 色)。
STAGES = [("raw", (), (0.6, 0.6, 0.6)), ("twist", ("twistCancel",), (0.2, 0.9, 1.0)),
          ("elbow", ("twistCancel", "elbowCancel"), (0.3, 1.0, 0.3)),
          ("cone", ("twistCancel", "elbowCancel", "forearmCone"), (1.0, 0.6, 0.1))]
# 交差する動きのあとに、食い込みが多い姿勢の動きをつなぐ。
KEYS = base.CROSS_KEYS+[(frame+360,)+tuple(values) for frame, *values in base.PROBLEM_KEYS[1:]]
COUNT = KEYS[-1][0]


def _node(kind, name, **values):
    """標準ノードを作り、定数を設定する。"""
    return base._node(kind, name, **values)


def _scaled(name, plug, enable, factor=1.0):
    """plug × enable × factor(度のプラグ)。enable はプラグか定数。0 なら None。"""
    if not isinstance(enable, str) and enable == 0:
        return None
    node = _node("multDoubleLinear", name, input2=factor)
    cmds.connectAttr(plug, node+".input1")
    if isinstance(enable, str):
        scale = _node("multDoubleLinear", name+"_enable", input2=factor)
        cmds.connectAttr(enable, scale+".input1")
        cmds.connectAttr(scale+".output", node+".input2")
    else:
        cmds.setAttr(node+".input2", factor*enable)
    return node+".output"


def _setAngle(name, plug, attr):
    """度のプラグを角度アトリビュートへつなぐ。plug が None なら 0 のまま。"""
    if plug is None:
        return
    radians = _node("unitConversion", name, conversionFactor=math.pi/180)
    cmds.connectAttr(plug, radians+".input")
    cmds.connectAttr(radians+".output", attr)


def _joint(name, parent, position=None, orient=0.0):
    """表示しない補助の関節。position を渡すとその位置に置く。"""
    joint = cmds.createNode("joint", name=name, parent=parent)
    if position is not None:
        cmds.xform(joint, worldSpace=True, translation=position)
    cmds.setAttr(joint+".jointOrient", orient, 0, 0)
    cmds.setAttr(joint+".drawStyle", 2)
    return joint


def _display(tail, color, width):
    """尻尾の線と先端の関節を作る。"""
    tip = cmds.createNode("joint", name=tail+"_tip", parent=tail)
    cmds.setAttr(tip+".ty", base.TAIL_LENGTH)
    cmds.setAttr(tip+".drawStyle", 2)
    curve = cmds.curve(degree=1, point=[(0, 0, 0), (0, base.TAIL_LENGTH, 0)], name=tail+"_display")
    shape = cmds.listRelatives(curve, shapes=True)[0]
    cmds.parent(shape, tail, shape=True, relative=True)
    cmds.delete(curve)
    cmds.setAttr(shape+".overrideEnabled", True)
    cmds.setAttr(shape+".overrideRGBColors", True)
    cmds.setAttr(shape+".overrideColorRGB", *color)
    cmds.setAttr(shape+".lineWidth", width)
    cmds.setAttr(shape+".alwaysDrawOnTop", True)
    cmds.setAttr(tail+".drawStyle", 2)
    return shape


def layeredTail(name, joints, kind, parent, root, side, enables, twist, delta, color, width):
    """レイヤー構造の尻尾を1本作る。

    Args:
        name (str): 尻尾の関節名(レイヤーは name + "_<layer>Layer")。
        joints (dict): 骨格の関節。
        kind (str): "upperarm"・"elbow"・"hand"。
        parent (str): 付け根の骨("upperarm" か "lowerarm")。
        root (str): 付け根の位置にする関節("upperarm"・"lowerarm"・"hand")。
        side (str): "_l" か "_r"。
        enables (dict): 効果の名前 → 0〜1(プラグか定数)。
        twist (str): 打ち消すひねり(度)のプラグ。
        delta (str): 3本共通の回避角 Δ(度)のプラグ。
        color (tuple): 線の色。
        width (float): 線の太さ。

    Returns:
        str: 尻尾の関節。
    """
    bone = joints[parent+side]
    lowerarm = joints["lowerarm"+side]
    position = cmds.xform(joints[root+side], query=True, worldSpace=True, translation=True)
    orient = 180.0 if side == "_r" else 0.0
    elbow_layer = _joint(name+"_elbowLayer", bone, position, orient)
    if kind != "upperarm":
        bend = _node("unitConversion", name+"_bendDegrees", conversionFactor=180/math.pi)
        cmds.connectAttr(lowerarm+".rotateY", bend+".input")
        _setAngle(name+"_elbowRadians", _scaled(name+"_elbowCancel", bend+".output", enables["elbowCancel"],
                                                -1 if side == "_l" else 1), elbow_layer+".ry")
    twist_layer = _joint(name+"_twistLayer", elbow_layer)
    _setAngle(name+"_twistRadians", _scaled(name+"_twistCancel", twist, enables["twistCancel"], -1),
              twist_layer+".rx")
    avoid_layer = _joint(name+"_avoidLayer", twist_layer)
    _setAngle(name+"_avoidRadians", _scaled(name+"_bodyAvoid", delta, enables["bodyAvoid"]), avoid_layer+".rx")
    rest_layer = _joint(name+"_restLayer", avoid_layer)
    cmds.setAttr(rest_layer+".rx", base.REST_RX)
    tail = cmds.createNode("joint", name=name, parent=rest_layer)
    if kind != "upperarm" and not (not isinstance(enables["forearmCone"], str) and enables["forearmCone"] == 0):
        _coneLayer(name, joints, root, side, bone, lowerarm, rest_layer, tail, orient, enables, twist, delta)
    _display(tail, color, width)
    return tail


def _coneLayer(name, joints, root, side, bone, lowerarm, rest_layer, tail, orient, enables, twist, delta):
    """前腕のコーン: restLayer の向き d が前腕の軸に近づいたら、ConeReader の重みの分だけ押し出す。

    押し出した向き (1 - w) d + w (cos α a + sin α L) へ aimConstraint した補助の関節の回転を、
    restLayer から見た回転にして、pairBlend で forearmCone の分だけ尻尾へ入れる。L は肘のスイング打ち消しを
    入れない向き(前腕と常に直角)。
    """
    position = cmds.xform(rest_layer, query=True, worldSpace=True, translation=True)
    helper = _joint(name+"_coneLocal", bone, position, orient)
    value = _node("plusMinusAverage", name+"_coneLocalRx")
    cmds.setAttr(value+".input1D[0]", base.REST_RX)
    for i, plug in enumerate((_scaled(name+"_coneLocalTwist", twist, enables["twistCancel"], -1),
                              _scaled(name+"_coneLocalAvoid", delta, enables["bodyAvoid"])), 1):
        if plug:
            cmds.connectAttr(plug, value+".input1D[{}]".format(i))
    _setAngle(name+"_coneLocalRadians", value+".output1D", helper+".rx")
    cone_name = name+"_forearmCone"
    reader = ConeReader.create(driverJoint=rest_layer, coneJoint=lowerarm, name=cone_name,
                               coneAngle=base.FOREARM_CONE, driverAxis="y", size=8.0, falloff="smooth")
    cmds.setAttr(reader.cone+".rotate", 0, 180 if root == "hand" else 0, 0)
    for group in (cone_name+"_driver_GRP", cone_name+"_cone_GRP"):
        cmds.setAttr(group+".visibility", False)
    d = base._direction(name+"_dDirection", rest_layer, (0, 1, 0))
    local = base._direction(name+"_localDirection", helper, (0, 1, 0))
    axis = base._direction(name+"_coneAxis", lowerarm, (-1 if root == "hand" else 1, 0, 0))
    edge = _node("plusMinusAverage", name+"_coneEdge")
    angle = math.radians(base.FOREARM_CONE)
    for i, (vector, factor) in enumerate(((axis, math.cos(angle)), (local, math.sin(angle)))):
        scaled = _node("multiplyDivide", "{}_coneEdge{}".format(name, i))
        cmds.connectAttr(vector, scaled+".input1")
        cmds.setAttr(scaled+".input2", factor, factor, factor)
        cmds.connectAttr(scaled+".output", edge+".input3D[{}]".format(i))
    blend = _node("blendColors", name+"_conePush")
    cmds.connectAttr(cone_name+".weight", blend+".blender")
    cmds.connectAttr(edge+".output3D", blend+".color1")
    cmds.connectAttr(d, blend+".color2")
    target = base._aimTarget(name+"_aimTarget", joints[root+side], [blend+".output"])
    aimed = _joint(name+"_coneAim", bone, position, orient)
    cmds.aimConstraint(target, aimed, aimVector=(0, 1, 0), upVector=(1, 0, 0), worldUpType="objectrotation",
                       worldUpObject=lowerarm, worldUpVector=(1, 0, 0))
    relative = _node("multMatrix", name+"_coneRelative")
    cmds.connectAttr(aimed+".worldMatrix[0]", relative+".matrixIn[0]")
    cmds.connectAttr(rest_layer+".worldInverseMatrix[0]", relative+".matrixIn[1]")
    decompose = _node("decomposeMatrix", name+"_coneRotate")
    cmds.connectAttr(relative+".matrixSum", decompose+".inputMatrix")
    pair = _node("pairBlend", name+"_coneBlend", rotInterpolation=1)
    cmds.connectAttr(decompose+".outputRotate", pair+".inRotate2")
    enable = enables["forearmCone"]
    if isinstance(enable, str):
        cmds.connectAttr(enable, pair+".weight")
    else:
        cmds.setAttr(pair+".weight", enable)
    cmds.connectAttr(pair+".outRotate", tail+".rotate")


def build(prefix="", offset=0.0, stages=True):
    """Aポーズの骨格、スイッチの CTRL、6本のレイヤー構造の尻尾と、段階ごとの尻尾(並列)を作る。

    Returns:
        dict: joints、tails(名前 → 尻尾)、stages(段階 → 名前 → 尻尾)、control、avoid(Δ のプラグ)。
    """
    for plugin in ("matrixNodes", "quatNodes"):
        if not cmds.pluginInfo(plugin, query=True, loaded=True):
            cmds.loadPlugin(plugin, quiet=True)
    result = humanoid.build(prefix=prefix, pose="A")
    joints = result["joints"]
    cmds.setAttr(prefix+"humanProxy_mat.transparency", 0.6, 0.6, 0.6, type="double3")
    cmds.setAttr(result["root"]+".tx", offset)
    for side in base.SIDES:
        for attr in ("rx", "rz"):
            cmds.setAttr(joints["lowerarm"+side]+"."+attr, lock=True)

    control = cmds.circle(name=prefix+CONTROL, normal=(0, 0, 1), radius=8, constructionHistory=False)[0]
    cmds.setAttr(control+".translate", offset+45, 185, 0)
    for attr in ("translate", "rotate", "scale"):
        for axis in "XYZ":
            cmds.setAttr(control+"."+attr+axis, lock=True, keyable=False, channelBox=False)
    cmds.setAttr(control+".visibility", keyable=False, channelBox=False)
    for switch in SWITCHES:
        cmds.addAttr(control, longName=switch, attributeType="double", minValue=0, maxValue=1, defaultValue=1,
                     keyable=True)
    cmds.addAttr(control, longName="showStages", attributeType="bool", defaultValue=stages, keyable=True)
    enables = {switch: control+"."+switch for switch in SWITCHES}

    deltas = base._bodyAvoid(prefix, joints, offset)
    tails, stage_tails = {}, {name: {} for name, _, _ in STAGES}
    for side in base.SIDES:
        twists = base.localTwistPlugs(prefix, joints, side)
        delta = deltas[side]["delta"]
        for kind, parent, root, color in base.TAILS:
            twist = twists[parent+side]
            tails[kind+side] = layeredTail("{}tail_{}{}".format(prefix, kind, side), joints, kind, parent, root,
                                           side, enables, twist, delta, color, 4)
            for stage, on, stage_color in STAGES:
                constants = {switch: 1.0 if switch in on else 0.0 for switch in SWITCHES}
                tail = layeredTail("{}stage_{}_{}{}".format(prefix, stage, kind, side), joints, kind, parent,
                                   root, side, constants, twist, delta, stage_color, 1.5)
                stage_tails[stage][kind+side] = tail
                # 線の表示だけを showStages に合わせる(関節は骨の子のまま)。
                shape = cmds.listRelatives(tail, shapes=True, fullPath=True)[0]
                cmds.connectAttr(control+".showStages", shape+".visibility")
    return {"joints": joints, "tails": tails, "stages": stage_tails, "control": control, "avoid": deltas}


def main(record=True, view="back"):
    """レイヤー構造の尻尾を1体に作り、交差する動き → 食い込みが多い姿勢の動きで動かす。

    Args:
        record (bool): False なら録画せず、スイッチを触って確かめられるシーンを作る(CTRL を選択する)。
        view (str): "back"(斜め後ろの透視投影)・"top"・"front"。
    """
    if cmds.about(batch=True):
        raise RuntimeError("専用Maya GUIで実行してください。")
    if PANEL in cmds.getPanel(allPanels=True):
        cmds.deleteUI(PANEL, panel=True)
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW, window=True)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")
    rig = build()
    joints = rig["joints"]
    for side in base.SIDES:
        for frame, rx, ry, rz, bend in KEYS:
            for joint, attr, value in (("upperarm", "rx", rx), ("upperarm", "ry", ry), ("upperarm", "rz", rz),
                                       ("lowerarm", "ry", bend)):
                cmds.setKeyframe(joints[joint+side], attribute=attr, time=frame, value=value)
    cmds.playbackOptions(minTime=1, maxTime=COUNT)
    meshes = base._bodyMeshes("")

    if view == "top":
        camera, shape = cmds.camera(name="tailLayersCamera", orthographic=True)
        cmds.setAttr(camera+".translate", 0, 400, -10)
        cmds.setAttr(camera+".rotate", -90, 0, 0)
        cmds.setAttr(shape+".orthographicWidth", 330)
    elif view == "front":
        camera, shape = cmds.camera(name="tailLayersCamera", orthographic=True)
        cmds.setAttr(camera+".translate", 0, 115, 400)
        cmds.setAttr(shape+".orthographicWidth", 330)
    else:
        camera, shape = cmds.camera(name="tailLayersCamera")
        cmds.setAttr(camera+".translate", 170, 250, -300)
        cmds.setAttr(camera+".rotate", -18, 150, 0)
        cmds.setAttr(shape+".focalLength", 32)
    if cmds.windowPref(WINDOW, exists=True):
        cmds.windowPref(WINDOW, remove=True)
    window = cmds.window(WINDOW, widthHeight=(1600, 860))
    pane = cmds.paneLayout(parent=window)
    panel = cmds.modelPanel(PANEL, parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", grid=view == "back", cameras=False,
                     joints=True, headsUpDisplay=True, manipulators=False, selectionHiliteDisplay=False,
                     locators=False)
    cmds.showWindow(window)
    cmds.window(window, edit=True, widthHeight=(1600, 860))
    cmds.setFocus(panel)
    demo_interactive.clearHuds(window)
    texts = {}
    for section, rows in ((0, 3), (5, 5)):
        for row in range(rows):
            name = "layersHud{}_{}".format(section, row)
            texts[name] = ""
            cmds.headsUpDisplay(name, section=section, block=row if section == 0 else rows-1-row, blockSize="large",
                                dataFontSize="large", command=lambda n=name: texts[n])
    control = rig["control"]
    labels = {"raw": "gray   raw", "twist": "cyan   + twist cancel", "elbow": "green  + elbow swing cancel",
              "cone": "orange + forearm cone"}

    def describe(tails):
        """左の3本の、付け根から ROOT_ZONE より先の食い込みと、upperarm の尻尾との最短距離。"""
        deep = [kind for kind in ("upperarm", "elbow", "hand")
                if (base.bodyHit(tails[kind+"_l"], meshes) or 0) > base.ROOT_ZONE]
        gap = min(base.segmentDistance(tails["upperarm_l"], tails[kind+"_l"]) for kind in ("elbow", "hand"))
        return deep, gap

    def evaluate(frame):
        """スイッチの状態と、段階ごと・本番の尻尾の食い込みと交差を記録する。"""
        demo_interactive.setTime(frame)
        result = {"frame": frame, "switches": {s: cmds.getAttr(control+"."+s) for s in SWITCHES}}
        for stage, _, _ in STAGES:
            deep, gap = describe(rig["stages"][stage])
            result[stage] = {"deep_hits": deep, "min_gap_cm": gap}
        deep, gap = describe(rig["tails"])
        result["main"] = {"deep_hits": deep, "min_gap_cm": gap,
                          "delta": cmds.getAttr(rig["avoid"]["_l"]["delta"])}
        result["ok"] = True
        switches = result["switches"]
        texts["layersHud0_0"] = "tailLayers_CTRL  twist {twistCancel:.0f}  elbow {elbowCancel:.0f}  " \
                                "cone {forearmCone:.0f}  avoid {bodyAvoid:.0f}".format(**switches)
        texts["layersHud0_1"] = "thick = layered tail (switches)   thin = stages in parallel"
        texts["layersHud0_2"] = "MAIN  body hit: {}   tail gap {:.1f}cm{}   delta {:+.0f}".format(
            ", ".join(deep) if deep else "none", gap, "  CROSS!" if gap < base.CROSS_DISTANCE else "",
            result["main"]["delta"])
        for row, (stage, _, _) in enumerate(STAGES):
            r = result[stage]
            texts["layersHud5_{}".format(row)] = "{:28s} body hit: {}   tail gap {:.1f}cm{}".format(
                labels[stage], ", ".join(r["deep_hits"]) if r["deep_hits"] else "none", r["min_gap_cm"],
                "  CROSS!" if r["min_gap_cm"] < base.CROSS_DISTANCE else "")
        texts["layersHud5_4"] = "body avoid assumes twist + elbow cancel ON (3 tails parallel)"
        for name in texts:
            cmds.headsUpDisplay(name, refresh=True)
        return result

    if not record:
        demo_interactive.attachInteractive(window, COUNT, evaluate)
        cmds.select(control)
        logger.info("Built the layered tails. Toggle the switches on tailLayers_CTRL in the Channel Box.")
        return
    folder = recordVideo("全身骨格(Aポーズ): 尻尾のレイヤー構造と段階ごとの並列表示", COUNT, 24, panel, evaluate,
                         ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"), width=1600, height=860)
    cmds.file(rename=str(folder/"tail-layers-{}.ma".format(view)))
    cmds.file(save=True, type="mayaAscii")
    (Path(__file__).resolve().parents[1]/".maya-output/verification/latest-tail-layers-{}.json".format(view)).write_text(
        json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved the layered tail recording: {}".format(folder))
    return folder


if __name__ == "__main__":
    main()
