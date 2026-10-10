"""尻尾根元補正の連続動作を、表示中の専用検証シーンで録画する。"""

import math
import os
import json
from pathlib import Path

from maya import cmds
from hlib import logger
import demo_root_direction_limit as demo
from verification_video import recordVideo


def main(*, armMotion=False, elbowBend=0.0, tailLength=6.0):
    """既存デモを使い、姿勢を補間して数値検証と映像を保存する。

    Args:
        armMotion (bool): 胴体を固定し、腕の持上げ・前後スイング・捻りを記録する。
        elbowBend (float): 肘を曲げる角度。度単位。録画後に元の姿勢へ戻す。
        tailLength (float): 尻尾方向の表示長。cm。6より大きい場合は貫通比較向けの動きを使う。
    """
    if not demo.STATE or not cmds.objExists(demo.STATE["arm"]):
        raise RuntimeError("専用Mayaで先にdemo_root_direction_limit.pyを実行してください。")
    state = demo.STATE
    if not math.isfinite(elbowBend) or not 0 <= elbowBend <= 150:
        raise ValueError("elbowBendは0から150度までで指定してください。")
    if not math.isfinite(tailLength) or tailLength <= 0:
        raise ValueError("tailLengthは正の有限値で指定してください。")
    nodes = [state["guides"][1], state["guides"][2], state["arm_pose"], state["arm"], state["elbow"]]
    original = [cmds.getAttr(node + ".rotate")[0] for node in nodes]
    original_legend = cmds.headsUpDisplay("rootLimitLegendHUD", query=True, label=True)
    visual_original = [(node, cmds.getAttr(node + ".tx"), cmds.getAttr(node + ".sx"))
                       for node in ("uncorrectedTail", "correctedTail")]
    camera_shape = cmds.listRelatives(state["camera"], shapes=True, fullPath=True)[0]
    original_width = cmds.getAttr(camera_shape + ".orthographicWidth")
    waypoints = [(0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 165, 0), (45, 30, 0, 0, 165, 0),
                 (0, 0, 35, 20, 165, 15), (0, 0, 0, 0, 0, 0)]
    if armMotion:
        waypoints = [(0, 0, 0), (0, 0, 85), (-55, 0, 65), (55, 0, 65),
                     (0, 150, 50), (-45, 150, 50), (45, 150, 50), (0, 0, 0)]
        if tailLength > 6:
            # 腕を体内へ押し込まず、未補正方向が体を横断する姿勢で停止する。
            waypoints = [(0, 0, 0), (0, 0, 0), (0, 165, 0), (0, 165, 0),
                         (0, 165, 15), (0, 165, 15), (0, 0, 0), (0, 0, 0)]

    def evaluate(frame):
        """ポーズ間を補間し、cone・位置・末端維持を確認する。"""
        phase = min(frame / 48.0, len(waypoints) - 1)
        segment = min(int(phase), len(waypoints) - 2)
        weight = phase - segment
        weight = weight * weight * (3 - 2 * weight)
        values = [a + (b - a) * weight for a, b in zip(waypoints[segment], waypoints[segment + 1])]
        if armMotion:
            rotations = [(0, 0, 0), (0, 0, 0), (0, 0, 0), tuple(values)]
        else:
            bend, chest, side, chest_side, twist, sweep = values
            rotations = [(bend, 0, side), (chest, 0, chest_side), (-chest, 0, -chest_side), (0, twist, sweep)]
        rotations.append((-elbowBend, 0, 0))
        for node, rotation in zip(nodes, rotations):
            cmds.setAttr(node + ".rotate", *rotation)
        graph = state["graph"]
        before = math.degrees(math.acos(max(-1, min(1, graph.container.getPlug("inputDot").get()))))
        after = math.degrees(math.acos(max(-1, min(1, graph.container.getPlug("resultDot").get()))))
        raw = cmds.xform(state["elbow"], query=True, worldSpace=True, translation=True)
        safe = cmds.xform(state["root"], query=True, worldSpace=True, translation=True)
        error = math.sqrt(sum((a - b) ** 2 for a, b in zip(raw, safe)))
        tip_position = cmds.getAttr(state["tip"] + ".translate")[0]
        tip_rotation = cmds.getAttr(state["tip"] + ".rotate")[0]
        raw_matrix = demo.om.MMatrix(cmds.getAttr(state["elbow"] + ".worldMatrix[0]"))
        safe_matrix = demo.om.MMatrix(cmds.getAttr(state["root"] + ".worldMatrix[0]"))
        raw_hits = demo.intersections(demo.om.MVector(*tuple(raw_matrix)[:3]).normal(), tailLength)
        safe_hits = demo.intersections(demo.om.MVector(*tuple(safe_matrix)[:3]).normal(), tailLength)
        cmds.headsUpDisplay("rootLimitPoseHUD", edit=True, label="Frame {} | RED: {} | GREEN: {} | {:.1f} -> {:.1f} deg".format(
            frame, "BODY HIT" if raw_hits else "CLEAR", "BODY HIT" if safe_hits else "CLEAR", before, after))
        return {"frame": frame, "input_angle": before, "output_angle": after, "root_position_error_cm": error,
                "elbow_bend_degrees": elbowBend,
                "tail_display_length_cm": tailLength, "raw_intersections": raw_hits, "corrected_intersections": safe_hits,
                "ok": after <= 45.002 and error < 1e-4 and not safe_hits and tip_position == (6, 0, 0) and tip_rotation == (0, 0, 0)}

    try:
        if tailLength > 6:
            cmds.setAttr(camera_shape + ".orthographicWidth", max(original_width, tailLength * 2 + 14))
        for node, _, _ in visual_original:
            cmds.setAttr(node + ".tx", tailLength / 2)
            cmds.setAttr(node + ".sx", tailLength / 6)
        cmds.headsUpDisplay("rootLimitLegendHUD", edit=True,
                            label="RED = ORIGINAL (NO CORRECTION) | GREEN = CORRECTED | BLUE = ARM")
        title = "RootDirectionLimit: 腕の持上げ・前後スイング・捻り" if armMotion else "RootDirectionLimit: 腕捻り・前屈・側屈"
        if elbowBend:
            title += "（肘{}度）".format(elbowBend)
        if tailLength > 6:
            title += "・長い方向表示{}cm・体交差比較".format(tailLength)
        folder = recordVideo(title, (len(waypoints) - 1) * 48 + 1, 24, state["panel"], evaluate,
                             ffmpeg=os.environ.get("MAYA_VERIFICATION_FFMPEG"))
        (Path(__file__).resolve().parents[1] / ".maya-output/verification/latest-root-limit.json").write_text(
            json.dumps({"folder": str(folder)}, ensure_ascii=False), encoding="utf-8")
        logger.info("検証動画を保存しました: {}".format(folder))
    finally:
        cmds.setAttr(camera_shape + ".orthographicWidth", original_width)
        for node, position, scale in visual_original:
            cmds.setAttr(node + ".tx", position)
            cmds.setAttr(node + ".sx", scale)
        for node, rotation in zip(nodes, original):
            cmds.setAttr(node + ".rotate", *rotation)
        cmds.headsUpDisplay("rootLimitLegendHUD", edit=True, label=original_legend)
        cmds.headsUpDisplay("rootLimitPoseHUD", edit=True, label="Recording complete")
        cmds.refresh(force=True)


if __name__ == "__main__":
    main()
