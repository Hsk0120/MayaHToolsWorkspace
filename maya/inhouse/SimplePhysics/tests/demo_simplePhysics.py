"""専用Maya GUIでSimple Physicsの入力・出力と制限を録画する。

main()は新規シーンを作るため、作業中のユーザーGUIでは実行しない。
"""

import json
import math
from pathlib import Path
import sys

from maya import cmds
from maya.api import OpenMaya as om

from simplePhysics import api
from simplePhysics.solver import position


ROOT = Path(__file__).resolve().parents[4]


def _line(name, color, width):
    """毎フレームの実DG位置を表示するポリラインを作る。"""
    line = cmds.curve(name=name, degree=1, point=[(i * 3, 12, 0) for i in range(5)])
    shape = cmds.listRelatives(line, shapes=True)[0]
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideRGBColors", True)
    cmds.setAttr(shape + ".overrideColorRGB", *color)
    cmds.setAttr(shape + ".lineWidth", width)
    return shape


def main(record=True):
    """専用の5ボーンで重力・根元移動・接触・角度制限・復帰を検証する。"""
    if cmds.about(batch=True):
        raise RuntimeError("専用のMaya GUIで実行してください")
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", time="film")
    cmds.playbackOptions(minTime=1, maxTime=145)
    cmds.currentTime(1)
    sources = []
    for index in range(5):
        sources.append(cmds.joint(name=f"spDemo_input_{index}", position=(index * 3, 12, 0)))
    for frame, x in ((1, 0), (25, 0), (49, -3), (73, 3), (97, 0), (145, 0)):
        cmds.setKeyframe(sources[0], attribute="translateX", time=frame, value=x)
    cmds.keyTangent(sources[0], attribute="translateX", inTangentType="linear", outTangentType="linear")
    node = api.create([sources[0]], name="SimplePhysicsDemo")
    for name, value in {"damping": 0.12, "stiffness": 0.005, "radius": 0.35, "limitAngle": 60,
                        "planarConstraint": 3, "collisionIterations": 32}.items():
        cmds.setAttr(node + "." + name, value)
    cmds.setAttr(node + ".gravity", 0, -300, 0, type="float3")
    sphere_center = om.MVector(8, 8, 0)
    sphere_radius = 1.0
    sphere = api.addCollider(node, "sphere", radius=sphere_radius)
    cmds.setAttr(sphere + ".translate", *sphere_center)
    floor = api.addCollider(node, "plane")
    cmds.setAttr(floor + ".translateY", 0)
    outputs = api.connections(node, "outputBones")
    raw = _line("inputPose_red", (1, 0.25, 0.2), 3)
    simulated = _line("physicsResult_green", (0.2, 1, 0.45), 6)
    # 半径を持つ計算点を各出力ジョイントに可視化する。
    for joint in outputs:
        marker = cmds.polySphere(radius=0.35, subdivisionsX=12, subdivisionsY=8, constructionHistory=False)[0]
        marker = cmds.parent(marker, joint, relative=True)[0]
        cmds.setAttr(marker + ".overrideEnabled", True)
        cmds.setAttr(marker + ".overrideRGBColors", True)
        cmds.setAttr(marker + ".overrideColorRGB", 0.2, 1, 0.45)
        cmds.setAttr(marker + ".overrideShading", False)
    camera, shape = cmds.camera(name="spDemo_camera", orthographic=True)
    cmds.setAttr(camera + ".translate", 1, 6, 40)
    cmds.setAttr(shape + ".orthographicWidth", 34)
    for window in ("spDemoWindow", "SimplePhysicsWindow"):
        if cmds.window(window, exists=True):
            cmds.deleteUI(window)
    window = cmds.window("spDemoWindow", title="Simple Physics - Maya 2027 verification", widthHeight=(1280, 760))
    pane = cmds.paneLayout()
    panel = cmds.modelPanel(parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", grid=False, joints=False,
                     cameras=False, selectionHiliteDisplay=False, headsUpDisplay=True, manipulators=False)
    cmds.showWindow(window)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    rows = [""] * 7
    for hud in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(hud, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(hud, remove=True)
    hud_names = []
    for index in range(len(rows)):
        name = f"spDemoHUD{index}"
        cmds.headsUpDisplay(name, section=0, block=index, blockSize="large", dataFontSize="large",
                           command=lambda row=index: rows[row], event="timeChanged")
        hud_names.append(name)

    def evaluate(index):
        """毎フレームの実出力から骨長・角度・点コリジョンを独立に検査する。"""
        frame = index + 1
        cmds.currentTime(frame)
        poses = [position(om.MMatrix(cmds.getAttr(joint + ".worldMatrix[0]"))) for joint in sources]
        points = [position(om.MMatrix(cmds.getAttr(joint + ".worldMatrix[0]"))) for joint in outputs]
        for line, values in ((raw, poses), (simulated, points)):
            for number, point in enumerate(values):
                cmds.setAttr(f"{line}.controlPoints[{number}]", *point)
        length_error = max(abs((b - a).length() - 3) for a, b in zip(points, points[1:]))
        angle = max(math.degrees((b - a).angle(om.MVector(1, 0, 0))) for a, b in zip(points, points[1:]))
        clearance = min(min((point - sphere_center).length() - sphere_radius - 0.35, point.y - 0.35) for point in points[1:])
        residual = cmds.getAttr(node + ".residualPenetration")
        stage = "SETTLE" if frame <= 25 else "ROOT LEFT" if frame <= 49 else "ROOT RIGHT" if frame <= 73 else "RETURN" if frame <= 97 else "RECOVERY"
        rows[:] = [
            f"SIMPLE PHYSICS | RED input / GREEN simulated | {stage} | frame {frame}",
            "Predict: p += (p-prev)*(1-D) + g*dt^2 ; D=0.12, gY=-300 cm/s2, dt=1/60 s",
            "Pose pull: p += (target-p)*S ; S=0.005 ; root world damping=0.8",
            "Length=3 cm | angle from input +X <=60 deg | particle r=0.35 cm",
            f"INPUT rootX={poses[0].x:+.2f} cm | OUTPUT tip=({points[-1].x:.2f}, {points[-1].y:.2f}) cm",
            f"OUTPUT max angle={angle:.2f} deg | max length error={length_error:.7f} cm",
            f"OUTPUT min clearance={clearance:+.5f} cm | solver residual={residual:.5f} cm",
        ]
        for hud in hud_names:
            cmds.headsUpDisplay(hud, refresh=True)
        return {"frame": frame, "stage": stage, "angle_degrees": angle, "length_error_cm": length_error,
                "clearance_cm": clearance, "residual_cm": residual, "tip": list(points[-1]),
                "ok": length_error < 1.0e-5 and angle <= 60.0001 and clearance >= -0.01}

    evaluate(0)
    cmds.refresh(force=True)
    if record:
        # 検証用共通ツールだけを必要時に追加し、製品パッケージを依存させない。
        sys.path.insert(0, str(ROOT / "tools"))
        from verification_video import recordVideo
        folder = recordVideo("Simple Physics: gravity, collision, angle and recovery", 145, 24, panel, evaluate)
        cmds.file(rename=str(folder / "simplePhysics-demo.ma"))
        cmds.file(save=True, type="mayaAscii")
        (ROOT / ".maya-output" / "simple-physics" / "latest-video.json").write_text(
            json.dumps({"folder": str(folder)}), encoding="utf-8")
        evaluate(72)
        return folder
    return node
