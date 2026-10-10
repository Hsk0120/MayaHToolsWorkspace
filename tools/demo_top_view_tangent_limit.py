"""固定半径・固定根元距離の上面検証で、接線角に回転を止める。"""

import json
import math
import os
from pathlib import Path

from maya import cmds
from hlib import logger
from demo_top_view_root_limit import _line, _circle_hit
from verification_video import recordVideo


def main():
    """専用GUIに新規シーンを作成し、左右の接線停止と復帰を検証する。

    円半径と肘の距離が一定の最小検証。演算はunitConversionとclampだけ。
    3Dメッシュへのコリジョンや以前の外向きcone補正は使用しない。
    """
    if cmds.about(batch=True):
        raise RuntimeError("専用のMaya GUIで実行してください。")
    for panel in ("topViewValidationPanel", "topTangentValidationPanel"):
        if panel in cmds.getPanel(allPanels=True):
            cmds.deleteUI(panel, panel=True)
    for window in ("topViewValidationWindow", "topTangentValidationWindow"):
        if cmds.window(window, exists=True):
            cmds.deleteUI(window, window=True)
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm", angle="deg", time="film")
    radius, distance, length, clearance = 3.0, 4.5, 12.0, 0.03
    # 薄い表示線にも余裕を持たせるため、円の外側0.03cmで停止する。
    limit = 180 - math.degrees(math.asin((radius + clearance) / distance))
    body = cmds.polyCylinder(name="bodyDisk", radius=radius, height=0.03, axis=(0, 1, 0),
                            subdivisionsX=96, constructionHistory=False)[0]
    cmds.setAttr(body + ".ty", -0.08)
    shader = cmds.shadingNode("surfaceShader", asShader=True, name="bodyDiskMaterial")
    cmds.setAttr(shader + ".outColor", 0.25, 0.28, 0.32, type="double3")
    group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="bodyDiskSG")
    cmds.connectAttr(shader + ".outColor", group + ".surfaceShader")
    cmds.sets(body, edit=True, forceElement=group)
    _line("bodyBoundary", [(radius * math.cos(i * math.pi / 48), 0, radius * math.sin(i * math.pi / 48))
                           for i in range(97)], (0.65, 0.67, 0.7), width=2)
    arm = cmds.createNode("transform", name="armOrbit")
    source = cmds.createNode("transform", name="originalDirection", parent=arm)
    output = cmds.createNode("transform", name="tangentStoppedDirection", parent=arm)
    for node in (source, output):
        cmds.setAttr(node + ".tx", distance)
    _line("bentArm", [(2.5, 0, -2), (distance, 0, 0), (6.5, 0, -2)], (0.2, 0.65, 1), arm)
    _line("elbowPoint", [(distance - 0.15, 0, 0), (distance + 0.15, 0, 0)], (1, 0.85, 0), arm, 8)
    _line("redOriginalDirection", [(0, 0, 0), (length, 0, 0)], (1, 0.12, 0.12), source, 5)
    _line("greenStoppedDirection", [(0, 0, 0), (length, 0, 0)], (0.1, 1, 0.1), output, 5)
    for sign in (-1, 1):
        theta = math.radians(limit * sign)
        _line("tangentBoundaryLeft" if sign < 0 else "tangentBoundaryRight", [(distance, 0, 0),
                                  (distance + 7 * math.cos(theta), 0, -7 * math.sin(theta))],
              (0.7, 0.7, 0.7), arm, 1)
    # 明示した変換係数でMaya内部のradianとclampのdegree値を接続する。
    to_degrees = cmds.createNode("unitConversion", name="directionRadiansToDegrees")
    limiter = cmds.createNode("clamp", name="circleTangentAngleStop")
    to_radians = cmds.createNode("unitConversion", name="stoppedDegreesToRadians")
    cmds.setAttr(to_degrees + ".conversionFactor", 180 / math.pi)
    cmds.setAttr(to_radians + ".conversionFactor", math.pi / 180)
    cmds.setAttr(limiter + ".minR", -limit)
    cmds.setAttr(limiter + ".maxR", limit)
    cmds.connectAttr(source + ".rotateY", to_degrees + ".input")
    cmds.connectAttr(to_degrees + ".output", limiter + ".inputR")
    cmds.connectAttr(limiter + ".outputR", to_radians + ".input")
    cmds.connectAttr(to_radians + ".output", output + ".rotateY")
    camera, camera_shape = cmds.camera(name="topTangentCamera", orthographic=True)
    cmds.setAttr(camera + ".translate", 1, 30, 0)
    cmds.setAttr(camera + ".rotate", -90, 0, 0)
    cmds.setAttr(camera_shape + ".orthographicWidth", 32)
    window = cmds.window("topTangentValidationWindow", title="Top view - Stop at circle tangent", widthHeight=(900, 950))
    layout = cmds.columnLayout(adjustableColumn=True)
    cmds.text(label="RED = requested | GREEN = stopped at tangent | Thin grey = angle boundary", height=30)
    pane = cmds.paneLayout(parent=layout, height=850)
    panel = cmds.modelPanel("topTangentValidationPanel", parent=pane, camera=camera, menuBarVisible=False)
    cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", displayLights="default", grid=False,
                     selectionHiliteDisplay=False, cameras=False, joints=False, headsUpDisplay=True, manipulators=False)
    cmds.showWindow(window)
    cmds.setFocus(panel)
    cmds.select(clear=True)
    # Maya自身のHUDを実フレームに描画する。値は実際のDG出力を毎フレーム読む。
    hud_values = [""] * 6
    hud_names = ["tangentFormulaHUD{}".format(i) for i in range(6)]
    # この検証専用GUIの左下領域を確保する（標準HUDとのブロック衝突を防ぐ）。
    for existing in cmds.headsUpDisplay(listHeadsUpDisplays=True) or []:
        if cmds.headsUpDisplay(existing, query=True, section=True) == 5:
            cmds.headsUpDisplay(existing, remove=True)
    for i, hud in enumerate(hud_names):
        if cmds.headsUpDisplay(hud, exists=True):
            cmds.headsUpDisplay(hud, remove=True)
        cmds.headsUpDisplay(hud, section=5, block=5-i, blockSize="large",
                            dataFontSize="large", command=lambda row=i: hud_values[row])
    # 接触前→接線到達→入力だけさらに回転→停止保持→元の方向へ復帰。左右を別々に示す。
    poses = [(0, 90), (0, 90), (0, 175), (0, 175), (0, 90), (0, 0),
             (0, -90), (0, -175), (0, -175), (0, -90), (0, 0), (20, 175), (20, 175), (0, 90)]

    def evaluate(frame):
        """停止角・非接触時の一致・円交差・根元位置を独立に検査する。"""
        phase = min(frame / 36, len(poses) - 1)
        index = min(int(phase), len(poses) - 2)
        weight = phase - index
        weight = weight * weight * (3 - 2 * weight)
        orbit, requested = [a + (b - a) * weight for a, b in zip(poses[index], poses[index + 1])]
        cmds.setAttr(arm + ".ry", orbit)
        cmds.setAttr(source + ".ry", requested)
        actual = cmds.getAttr(output + ".ry")
        alpha = math.degrees(math.asin((radius + clearance) / distance))
        hud_values[:] = [
            "0 deg = OUTWARD | 180 deg = TOWARD CENTER",
            "r={:.2f} cm  gap={:.2f} cm  d={:.2f} cm (fixed)".format(radius, clearance, distance),
            "alpha = asin((r+gap)/d) = {:.2f} deg".format(alpha),
            "limit = 180 - {:.2f} = {:.2f} deg".format(alpha, limit),
            "INPUT (RED) = {:+.2f} deg".format(requested),
            "OUTPUT = clamp(INPUT, -{:.2f}, +{:.2f}) = {:+.2f} deg".format(limit, limit, actual),
        ]
        for hud in hud_names:
            cmds.headsUpDisplay(hud, refresh=True)
        expected = max(-limit, min(limit, requested))
        source_matrix = cmds.xform(source, query=True, worldSpace=True, matrix=True)
        output_matrix = cmds.xform(output, query=True, worldSpace=True, matrix=True)
        root = source_matrix[12:15]
        raw_hit = _circle_hit(root, source_matrix[:3], length, radius)
        safe_hit = _circle_hit(root, output_matrix[:3], length, radius)
        error = math.sqrt(sum((a - b) ** 2 for a, b in zip(root, output_matrix[12:15])))
        return {"frame": frame, "requested_degrees": requested, "output_degrees": actual, "tangent_limit_degrees": limit,
                "clearance_cm": clearance, "stopped": abs(requested) > limit,
                "raw_intersections": ["bodyCircle"] if raw_hit else [],
                "corrected_intersections": ["bodyCircle"] if safe_hit else [],
                "ok": not safe_hit and abs(actual - expected) < 1e-4 and error < 1e-5 and abs(output_matrix[1]) < 1e-5}

    folder = recordVideo("2D上面: 円の接線で尻尾回転を止める", 469, 24, panel, evaluate,
                         ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"), width=900, height=900)
    record = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    if not record["ok"]:
        raise RuntimeError("接線停止の検証に失敗しました: {}".format(folder))
    cmds.file(rename=str(folder / "top-tangent-stop.ma"))
    cmds.file(save=True, type="mayaAscii")
    (Path(__file__).resolve().parents[1] / ".maya-output/verification/latest-top-tangent.json").write_text(
        json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
    logger.info("接線で止まる上面検証を保存しました: {}".format(folder))


if __name__ == "__main__":
    main()
