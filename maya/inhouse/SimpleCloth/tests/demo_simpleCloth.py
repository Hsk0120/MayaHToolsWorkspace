"""専用Maya GUI用の布検証。新規シーンを作るため作業中のGUIへ送らない。"""

import json
from pathlib import Path
import sys

from maya import cmds
from maya.api import OpenMaya as om

from simpleCloth import api


ROOT = Path(__file__).resolve().parents[4]


def build():
    """固定辺付きの布と球、入力の往復アニメーションを作る。"""
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", time="film")
    cmds.currentTime(1)
    cmds.playbackOptions(minTime=1, maxTime=145)
    source = cmds.polyPlane(name="scDemo_input", axis=(0, 0, 1), width=8, height=10,
                            subdivisionsX=8, subdivisionsY=10, constructionHistory=False)[0]
    cmds.setAttr(source + ".translateY", 7)
    cloth = api.create(source, name="SimpleClothDemo_solver")
    output = api.getConnection(cloth, "outputMeshObject")
    reference = json.loads(cmds.getAttr(cloth + ".referenceData"))
    highest = max(point[1] for point in reference["points"])
    pins = [index for index, point in enumerate(reference["points"]) if point[1] > highest - 0.001]
    api.setVertexWeights(cloth, pins, 0)
    for name, value in {"maxDistance": 3, "iterations": 12, "solverRate": 72,
                        "damping": 3, "bendCompliance": 0.02, "collisionThickness": 0.15}.items():
        cmds.setAttr(cloth + "." + name, value)
    cmds.setAttr(cloth + ".gravity", 0, -100, 0, type="float3")
    cmds.setAttr(cloth + ".wind", 0, 0, 70, type="float3")
    sphere = api.addCollider(cloth, "sphere", radius=1.1)
    cmds.setAttr(sphere + ".translate", 0, 5, 1.4)
    for frame, value in ((1, 0), (73, 0), (97, 8), (145, 8)):
        cmds.setKeyframe(sphere, attribute="translateX", time=frame, value=value,
                         inTangentType="plateau", outTangentType="plateau")
    for frame, value in ((1, 0), (25, 0), (49, -2), (73, 2), (97, 0), (145, 0)):
        cmds.setKeyframe(source, attribute="translateX", time=frame, value=value,
                         inTangentType="plateau", outTangentType="plateau")
    for mesh, color, shaded in ((source, (1, 0.25, 0.2), False), (output, (0.1, 0.8, 0.6), True)):
        cmds.setAttr(mesh + ".overrideEnabled", True)
        cmds.setAttr(mesh + ".overrideRGBColors", True)
        cmds.setAttr(mesh + ".overrideColorRGB", *color)
        cmds.setAttr(mesh + ".overrideShading", shaded)
    material = cmds.shadingNode("lambert", asShader=True, name="scDemo_green")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
    cmds.connectAttr(material + ".outColor", group + ".surfaceShader")
    cmds.setAttr(material + ".color", 0.06, 0.6, 0.34)
    cmds.sets(output, edit=True, forceElement=group)
    return cloth, source, output, sphere, pins


def measure(frame, cloth, source, output, sphere, pins):
    """実DGメッシュから固定誤差・最大移動量・球クリアランスを測る。"""
    cmds.currentTime(frame)
    result = [om.MVector(point) for point in om.MFnMesh(api._mesh(output)).getPoints(om.MSpace.kWorld)]
    targets = [om.MVector(point) for point in om.MFnMesh(api._mesh(source)).getPoints(om.MSpace.kWorld)]
    center = om.MVector(cmds.xform(sphere, query=True, worldSpace=True, translation=True))
    radius = cmds.getAttr(sphere + ".clothRadius") + cmds.getAttr(cloth + ".collisionThickness")
    pin_error = max((result[index] - targets[index]).length() for index in pins)
    max_distance = max((point - target).length() for point, target in zip(result, targets))
    clearance = min((point - center).length() - radius for point in result)
    stretch = cmds.getAttr(cloth + ".stretchError")
    return {"frame": frame, "pin_error_cm": pin_error, "max_distance_cm": max_distance,
            "clearance_cm": clearance, "stretch_error_ratio": stretch,
            "source_x_cm": cmds.getAttr(source + ".translateX"), "tip_cm": list(result[-1]),
            "ok": pin_error < 1.0e-5 and max_distance <= 3.0001 and clearance >= -0.01 and stretch < 0.2}


def main(record=True):
    """固定カメラと数値HUDを作り、実viewportを145フレーム録画する。"""
    values = build()
    cloth, source, output, sphere, pins = values
    for window in ("spDemoWindow", "SimplePhysicsWindow", "scDemoWindow", "SimpleClothWindow"):
        if cmds.window(window, exists=True):
            cmds.deleteUI(window)
    camera, shape = cmds.camera(name="scDemo_camera", orthographic=True)
    cmds.setAttr(camera + ".translate", 18, 14, 30)
    target = cmds.spaceLocator()[0]
    cmds.setAttr(target + ".translate", 0, 8, 0)
    constraint = cmds.aimConstraint(target, camera, aimVector=(0, 0, -1), upVector=(0, 1, 0), worldUpType="vector")[0]
    cmds.delete(constraint, target)
    cmds.setAttr(shape + ".orthographicWidth", 30)
    window = cmds.window("scDemoWindow", title="Simple Cloth — Maya 2027 verification", widthHeight=(1280, 760))
    pane = cmds.paneLayout()
    panel = cmds.modelPanel(parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", wireframeOnShaded=True, grid=False,
                     cameras=False, selectionHiliteDisplay=False, headsUpDisplay=True, manipulators=False)
    cmds.showWindow(window)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    rows = [""] * 6
    for hud in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(hud, query=True, section=True) in (0, 5):
            cmds.headsUpDisplay(hud, remove=True)
    hud_names = []
    for index in range(len(rows)):
        name = f"scDemoHUD{index}"
        cmds.headsUpDisplay(name, section=0, block=index, blockSize="large", dataFontSize="large",
                           command=lambda row=index: rows[row], event="timeChanged")
        hud_names.append(name)

    def evaluate(index):
        """実出力の数値をHUDへ表示し、録画共通処理へ検査結果を返す。"""
        frame = index + 1
        result = measure(frame, *values)
        stage = "SETTLE" if frame <= 25 else "MOVE LEFT" if frame <= 49 else "MOVE RIGHT" if frame <= 73 else "RETURN" if frame <= 97 else "RECOVERY"
        rows[:] = [
            f"SIMPLE CLOTH | RED input / GREEN cloth / BLUE collider | {stage} | frame {frame}",
            "XPBD: C=length-rest, alpha=compliance/dt^2 | dt=1/72 s, iterations=12 (fixed)",
            "p += v*dt + (gravity+wind)*dt^2 | gravityY=-100, windZ=70 cm/s2 (fixed)",
            f"Max Distance: |p-input| <= 3*map cm | top map=0 | actual max={result['max_distance_cm']:.4f} cm",
            f"INPUT x={result['source_x_cm']:+.2f} cm | OUTPUT pin error={result['pin_error_cm']:.6f} cm",
            f"OUTPUT sphere clearance={result['clearance_cm']:+.5f} cm | max stretch error={result['stretch_error_ratio']:.5f}",
        ]
        for hud in hud_names:
            cmds.headsUpDisplay(hud, refresh=True)
        return result

    evaluate(0)
    cmds.refresh(force=True)
    if not record:
        return cloth
    # 検証用共通ツールだけを必要時に読み、製品パッケージからは依存させない。
    sys.path.insert(0, str(ROOT / "tools"))
    from verification_video import recordVideo
    folder = recordVideo("Simple Cloth: pinned mesh, max distance, sphere collision and recovery", 145, 24, panel, evaluate)
    cmds.file(rename=str(folder / "simpleCloth-demo.ma"))
    cmds.file(save=True, type="mayaAscii")
    local = ROOT / ".maya-output" / "simple-cloth"
    local.mkdir(parents=True, exist_ok=True)
    (local / "latest-video.json").write_text(json.dumps({"folder": str(folder)}), encoding="utf-8")
    evaluate(72)
    return folder
