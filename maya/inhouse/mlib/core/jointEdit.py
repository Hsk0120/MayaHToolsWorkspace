"""Jointの再親付けを、回転チャンネルとSSCを保って直接実行する。"""

import maya.api.OpenMaya as om2

from .fastWrite import require_writable
from .nodeEdit import require_editable


def reparent_plan(joint, parent):
    """cmds.parentで中間Transformを必要としないJointの更新計画を作る。

    Args:
        joint (Joint): 移動するJoint。
        parent (Transform | None): 移動先。

    Returns:
        tuple: 対象、親、移動・jointOrient、新しいinverseScale入力。
    """
    from ..maths import Matrix
    from ..nodes.transform import Transform

    require_editable(joint.mnode())
    if om2.MFnDagNode(joint.mnode()).isInstanced():
        raise NotImplementedError("fast joint parenting does not support instances")
    if parent is not None:
        require_editable(parent.mnode())
        parent_matrix = parent.getMatrix(worldSpace=True)
        if abs(parent_matrix.det4x4()) < 1e-12:
            raise ValueError("Cannot parent under a singular transform")
    else:
        parent_matrix = Matrix()
    for name in ("translate", "jointOrient"):
        plug = joint.getPlug(name).mplug()
        require_writable(plug)
        for i in range(plug.numChildren()):
            require_writable(plug.child(i))
    inverse = joint.getPlug("inverseScale").mplug()
    old_source = inverse.connectedTo(True, False)
    old_parent = joint.getParent()
    if old_source and (old_parent is None or old_source[0] != old_parent.getPlug("scale").mplug()):
        raise NotImplementedError("fast joint parenting cannot replace a custom inverseScale input")
    if inverse.isLocked or any(inverse.child(i).isLocked or inverse.child(i).isDestination
                              for i in range(inverse.numChildren())):
        raise RuntimeError("inverseScale is locked or has per-axis inputs")
    new_source = parent.getPlug("scale") if parent is not None and parent.isType("joint") else None
    inverse_value = tuple(new_source.get()) if new_source is not None else (1.0, 1.0, 1.0)
    if joint.getSegmentScaleCompensate() and any(abs(v) < 1e-12 for v in inverse_value):
        raise ValueError("Cannot compensate a zero parent scale")
    local = joint.getMatrix(worldSpace=True) * parent_matrix.inverse()
    corrected = local * Matrix(scale=inverse_value) if joint.getSegmentScaleCompensate() else Matrix(local)
    corrected.translate = local.translate
    _, quaternion, scale, shear, _ = Transform._decompose_like_channels(joint, corrected)
    if any(abs(a - b) > 1e-7 for a, b in zip(scale, joint.getScale())) or any(abs(v) > 1e-7 for v in shear):
        raise NotImplementedError("fast joint parenting cannot insert the compensating Transform required by Maya")
    orientation = (joint._component_quaternion("rotate").inverse()
                   * joint._component_quaternion("rotateAxis").inverse() * quaternion)
    return joint, parent, tuple(local.translate), orientation.asEulerRotation(), new_source


def reparent(plan):
    """検証済みJointを移動し、inverseScale接続と姿勢を復元する。

    Args:
        plan (tuple): reparent_planが返した計画。

    Returns:
        None: 値を返さない。
    """
    joint, parent, translate, orientation, new_source = plan
    inverse = joint.getPlug("inverseScale").mplug()
    modifier = om2.MDGModifier()
    for origin in inverse.connectedTo(True, False):
        modifier.disconnect(origin, inverse)
    modifier.doIt()
    modifier = om2.MDagModifier()
    modifier.reparentNode(joint.mnode(), parent.mnode() if parent is not None else om2.MObject.kNullObj)
    modifier.doIt()
    # 旧パスを別インスタンスへ暗黙変更せず、この操作で移動したノードの新パスを束縛する。
    joint._resolve(om2.MDagPath.getAPathTo(joint.mnode()))
    inverse = joint.getPlug("inverseScale")
    if new_source is not None:
        new_source.connectTo(inverse, fast=True)
    else:
        inverse.set((1.0, 1.0, 1.0), fast=True)
    joint.getPlug("jointOrient").set(orientation, fast=True)
    joint.getPlug("translate").set(translate, fast=True)
