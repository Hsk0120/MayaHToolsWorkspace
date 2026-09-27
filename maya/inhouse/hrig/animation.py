"""対応済み3関節チェーンからhrigコントローラーへベイクする。"""

import math
import json
from maya import cmds

import hlib
from maya.api import OpenMaya as om
from hlib.decorators.undo import undo_transaction


@undo_transaction("hrig.bake_source")
def bake_source(rig, source_joints, start, end, step=1.0, mode="fk"):
    """外部の受け側骨をサンプリングし、FKまたはIKのキーへ変換する。

    Args:
        rig (LimbRig): ベイク先。
        source_joints (iterable): 根元・中間・終端の順の外部joint。
        start (float): 開始フレーム。
        end (float): 終了フレーム。
        step (float): 正のサンプル間隔。
        mode (str): fkまたはik。ikでもFKキーを中間結果として残す。

    Returns:
        tuple[float]: ベイクしたフレーム。

    Note:
        同じ骨長・基準軸へリターゲット済みのチェーン専用。HumanIK等で
        比率や基準姿勢を合わせてから使用する。指定範囲の既存キーを置換する。
        FK/IK切替のアニメーションは作らず、最後に指定モードへ切り替える。
    """
    if mode not in ("fk", "ik"):
        raise ValueError("mode must be fk or ik")
    if not all(math.isfinite(v) for v in (start, end, step)) or step <= 0 or end < start:
        raise ValueError("Invalid frame range")
    sources = [hlib.node(node).full_name() for node in source_joints]
    if len(sources) != 3 or len(set(sources)) != 3:
        raise ValueError("Expected three different source joints")
    root = rig.root.full_name()
    for source in sources:
        if hlib.node(source).type() != "joint" or source.startswith(root + "|"):
            raise ValueError("Source must be an external joint")
    frames = [start + i * step for i in range(int(math.floor((end - start) / step)) + 1)]
    if frames[-1] < end - 1e-8:
        frames.append(end)
    previous_time = cmds.currentTime(query=True)
    controls = rig.controls()
    attributes = ("tx", "ty", "tz", "rx", "ry", "rz")
    keyed = [controls["fk" + str(i)] for i in range(3)]
    if mode == "ik":
        keyed += [controls["target"], controls["pole"]]
    for node in keyed:
        for attr in attributes:
            if hlib.plug(node + "." + attr).is_locked():
                raise ValueError("Locked control channel: " + node + "." + attr)
            sources_in = (
                cmds.listConnections(node + "." + attr, source=True, destination=False) or []
            )
            if any(not hlib.node(item).type().startswith("animCurve") for item in sources_in):
                raise ValueError("Control channel is driven by a non-animation node")
    try:
        samples = []
        definition = json.loads(hlib.plug(root + ".hrigDefinition").get())
        from .definition import RigDefinition

        lengths = [
            joint.translation[0] for joint in RigDefinition.from_data(definition).joint_order()[1:]
        ]
        for frame in frames:
            cmds.currentTime(frame)
            matrices = [list(hlib.node(node).get_matrix(ws=True)) for node in sources]
            if mode == "ik":
                inverse = om.MMatrix(hlib.plug(root + ".worldInverseMatrix[0]").get())
                points = [om.MPoint(matrix[12:15]) * inverse for matrix in matrices]
                if om.MVector(points[0]).length() > 1e-4:
                    raise ValueError(
                        "IK source root must coincide with the rig root at each sample"
                    )
                for i, length in enumerate(lengths):
                    if abs((points[i + 1] - points[i]).length() - length) > 1e-4:
                        raise ValueError("IK source bone lengths must match the rig")
            samples.append(matrices)
        for node in keyed:
            cmds.cutKey(node, attribute=list(attributes), time=(start, end), clear=True)
        rig.set_mode("fk")
        for frame, matrices in zip(frames, samples):
            cmds.currentTime(frame)
            for index, matrix in enumerate(matrices):
                node = controls["fk" + str(index)]
                from .limb import _set_world_matrix

                _set_world_matrix(node, matrix)
                cmds.setKeyframe(node, attribute=list(attributes), time=frame)
            if mode == "ik":
                rig.match_ik()
                for node in (controls["target"], controls["pole"]):
                    cmds.setKeyframe(node, attribute=list(attributes), time=frame)
        rig.set_mode(mode)
    finally:
        cmds.currentTime(previous_time)
    return tuple(frames)
