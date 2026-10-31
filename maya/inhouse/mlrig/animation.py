"""対応済み3関節チェーンからmlrigコントローラーへベイクする。"""
from mlib.maths import MSpace

import json
import math
import mlib

from mlib.common import Time
from mlib.maths import Matrix, Vector
from mlib.decorator import undoTransaction


@undoTransaction("mlrig.bake_source")
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
    sources = [mlib.nodes.Node(node).getFullName() for node in source_joints]
    if len(sources) != 3 or len(set(sources)) != 3:
        raise ValueError("Expected three different source joints")
    root = rig.root.getFullName()
    for source in sources:
        if mlib.nodes.Node(source).getType() != "joint" or source.startswith(root + "|"):
            raise ValueError("Source must be an external joint")
    frames = [start + i * step for i in range(int(math.floor((end - start) / step)) + 1)]
    if frames[-1] < end - 1e-8:
        frames.append(end)
    previous_time = Time.getCurrent()
    controls = rig.controls()
    attributes = ("tx", "ty", "tz", "rx", "ry", "rz")
    keyed = [controls["fk" + str(i)] for i in range(3)]
    if mode == "ik":
        keyed += [controls["target"], controls["pole"]]
    for node in keyed:
        for attr in attributes:
            if mlib.getPlug(node + "." + attr).isLocked():
                raise ValueError("Locked control channel: " + node + "." + attr)
            source = mlib.getPlug(node + "." + attr).getSource()
            if source is not None and not source.getNode().getType().startswith("animCurve"):
                raise ValueError("Control channel is driven by a non-animation node")
    try:
        samples = []
        definition = json.loads(mlib.getPlug(root + ".mlrigDefinition").get())
        from .definition import RigDefinition

        lengths = [
            joint.translation[0] for joint in RigDefinition.from_data(definition).joint_order()[1:]
        ]
        for frame in frames:
            Time.setCurrent(frame)
            matrices = [list(mlib.nodes.Node(node).getMatrix(worldSpace=True)) for node in sources]
            if mode == "ik":
                inverse = Matrix(mlib.nodes.Node(root).getPlug("worldInverseMatrix")[0].get())
                points = [inverse.transformPoint(matrix[12:15]) for matrix in matrices]
                if Vector(points[0]).length() > 1e-4:
                    raise ValueError(
                        "IK source root must coincide with the rig root at each sample"
                    )
                for i, length in enumerate(lengths):
                    if abs((points[i + 1] - points[i]).length() - length) > 1e-4:
                        raise ValueError("IK source bone lengths must match the rig")
            samples.append(matrices)
        for node in keyed:
            mlib.nodes.Node(node).removeKey(list(attributes), time=(start, end))
        rig.set_mode("fk")
        for frame, matrices in zip(frames, samples):
            Time.setCurrent(frame)
            for index, matrix in enumerate(matrices):
                node = controls["fk" + str(index)]
                from .limb import _set_world_matrix

                _set_world_matrix(node, matrix)
                mlib.nodes.Node(node).setKey(list(attributes), time=frame)
            if mode == "ik":
                rig.match_ik()
                for node in (controls["target"], controls["pole"]):
                    mlib.nodes.Node(node).setKey(list(attributes), time=frame)
        rig.set_mode(mode)
    finally:
        Time.setCurrent(previous_time)
    return tuple(frames)
