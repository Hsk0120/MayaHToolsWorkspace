"""新規シーンに円と方向線だけの上面検証を構築し、動画を記録する。"""

import json
import math
import os
from pathlib import Path

from maya import cmds
from hlib import logger
from hrig.setups import RootDirectionLimit
from verification_video import recordVideo


def _line(name, points, color, parent=None, width=4):
    """XZ平面に表示する色付き線を作成する。"""
    node = cmds.curve(name=name, degree=1, point=points)
    if parent:
        cmds.parent(node, parent, relative=True)
    shape = cmds.listRelatives(node, shapes=True, fullPath=True)[0]
    cmds.setAttr(shape + ".overrideEnabled", True)
    cmds.setAttr(shape + ".overrideRGBColors", True)
    cmds.setAttr(shape + ".overrideColorRGB", *color)
    cmds.setAttr(shape + ".lineWidth", width)
    return node


def _circle_hit(origin, direction, length=12, radius=3):
    """表示用中心線と円の交差を検証する。リグの評価には使用しない。"""
    ox, oz = origin[0], origin[2]
    dx, dz = direction[0], direction[2]
    denominator = dx * dx + dz * dz
    distance = min(length, max(0, -(ox * dx + oz * dz) / denominator))
    return (ox + distance * dx) ** 2 + (oz + distance * dz) ** 2 < radius * radius


def main():
    """専用Maya GUIのデータをゼロから作り直して上面動画を保存する。"""
    if cmds.about(batch=True):
        raise RuntimeError("専用のMaya GUIで実行してください。")
    for panel in ("rootLimitValidationPanel", "topViewValidationPanel"):
        if panel in cmds.getPanel(allPanels=True):
            cmds.deleteUI(panel, panel=True)
    for window in ("rootLimitValidationWindow", "topViewValidationWindow"):
        if cmds.window(window, exists=True):
            cmds.deleteUI(window, window=True)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")
    guides = [cmds.createNode("transform", name="bodyGuideLower"),
              cmds.createNode("transform", name="bodyGuideUpper")]
    cmds.setAttr(guides[0] + ".ty", -2)
    cmds.setAttr(guides[1] + ".ty", 2)
    body = cmds.polyCylinder(name="bodyDisk", radius=3, height=0.03, axis=(0, 1, 0),
                            subdivisionsX=96, constructionHistory=False)[0]
    cmds.setAttr(body + ".ty", -0.08)
    shader = cmds.shadingNode("surfaceShader", asShader=True, name="bodyDiskMaterial")
    cmds.setAttr(shader + ".outColor", 0.25, 0.28, 0.32, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="bodyDiskSG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    cmds.sets(body, edit=True, forceElement=group)
    _line("bodyBoundary", [(3 * math.cos(i * math.pi / 48), 0, 3 * math.sin(i * math.pi / 48))
                           for i in range(97)], (0.65, 0.67, 0.7), width=2)
    arm = cmds.createNode("transform", name="armOrbit")
    elbow = cmds.createNode("transform", name="elbowDirection", parent=arm)
    cmds.setAttr(elbow + ".tx", 4.5)
    _line("bentArm", [(2.5, 0, -2), (4.5, 0, 0), (6.5, 0, -2)], (0.2, 0.65, 1), arm)
    marker = cmds.polyCylinder(name="elbowPoint", radius=0.18, height=0.03, axis=(0, 1, 0),
                              constructionHistory=False)[0]
    cmds.parent(marker, elbow, relative=True)
    cmds.setAttr(marker + ".overrideEnabled", True)
    cmds.setAttr(marker + ".overrideRGBColors", True)
    cmds.setAttr(marker + ".overrideColorRGB", 1, 0.85, 0)
    marker_shader = cmds.shadingNode("surfaceShader", asShader=True, name="elbowPointMaterial")
    cmds.setAttr(marker_shader + ".outColor", 1, 0.85, 0, type="double3")
    marker_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="elbowPointSG")
    cmds.connectAttr(marker_shader + ".outColor", marker_group + ".surfaceShader")
    cmds.sets(marker, edit=True, forceElement=marker_group)
    graph = RootDirectionLimit.create(elbow, guides, name="topViewDirectionLimit", angle=45)
    _line("redOriginalDirection", [(0, 0, 0), (12, 0, 0)], (1, 0.12, 0.12), elbow, 5)
    _line("greenCorrectedDirection", [(0, 0, 0), (12, 0, 0)], (0.1, 1, 0.1), graph.output.getFullName(), 5)
    camera, camera_shape = cmds.camera(name="topViewCamera", orthographic=True)
    cmds.setAttr(camera + ".translate", 4, 30, 0)
    cmds.setAttr(camera + ".rotate", -90, 0, 0)
    cmds.setAttr(camera_shape + ".orthographicWidth", 28)
    window = cmds.window("topViewValidationWindow", title="2D Top View - Root Direction Limit", widthHeight=(900, 950))
    layout = cmds.columnLayout(adjustableColumn=True)
    cmds.text(label="TOP VIEW ONLY | Circle = body | Yellow = elbow | Blue = bent arm", height=30)
    pane = cmds.paneLayout(parent=layout, height=850)
    panel = cmds.modelPanel("topViewValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default",
                     grid=False, selectionHiliteDisplay=False, cameras=False, joints=False,
                     headsUpDisplay=False, manipulators=False)
    cmds.showWindow(window)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    # 動きは上面平面の回転2つだけ。体の円とカメラは固定する。
    poses = [(0, 0), (0, 0), (0, 165), (0, 165), (25, 165), (25, 165),
             (-25, 165), (-25, 165), (0, 0), (0, 0)]

    def evaluate(frame):
        """平面回転を補間し、円への交差と補正方向の平面性を確認する。"""
        phase = min(frame / 36, len(poses) - 1)
        index = min(int(phase), len(poses) - 2)
        weight = phase - index
        weight = weight * weight * (3 - 2 * weight)
        orbit, twist = [a + (b - a) * weight for a, b in zip(poses[index], poses[index + 1])]
        cmds.setAttr(arm + ".ry", orbit)
        cmds.setAttr(elbow + ".ry", twist)
        source_matrix = cmds.xform(elbow, query=True, worldSpace=True, matrix=True)
        output_matrix = cmds.xform(graph.output.getFullName(), query=True, worldSpace=True, matrix=True)
        raw = source_matrix[:3]
        safe = output_matrix[:3]
        root = source_matrix[12:15]
        raw_hit = _circle_hit(root, raw)
        safe_hit = _circle_hit(root, safe)
        after = math.degrees(math.acos(max(-1, min(1, graph.container.getPlug("resultDot").get()))))
        error = math.sqrt(sum((a - b) ** 2 for a, b in zip(root, output_matrix[12:15])))
        return {"frame": frame, "arm_orbit_degrees": orbit, "input_direction_degrees": twist,
                "raw_intersections": ["bodyCircle"] if raw_hit else [],
                "corrected_intersections": ["bodyCircle"] if safe_hit else [],
                "output_angle": after, "root_position_error_cm": error, "direction_y": safe[1],
                "ok": not safe_hit and after <= 45.002 and error < 1e-5 and abs(safe[1]) < 1e-5}

    folder = recordVideo("2D上面: 円の胴体と尻尾方向の補正", 325, 24, panel, evaluate,
                         ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"), width=900, height=900)
    record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    if not record["ok"] or not any(frame["raw_intersections"] for frame in record["frames"]):
        raise RuntimeError("上面検証の数値判定に失敗しました。")
    cmds.file(rename=str(folder / "top-view.ma"))
    cmds.file(save=True, type="mayaAscii")
    latest = Path(__file__).resolve().parents[1] / ".maya-output/verification/latest-top-view.json"
    latest.write_text(json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
    logger.info("新規上面検証シーンと動画を保存しました: {}".format(folder))


if __name__ == "__main__":
    main()
