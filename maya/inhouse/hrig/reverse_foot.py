"""3関節部位のIKへ後付けする、ローカル行列ベースのリバースフット。"""

import math
import json
from maya import cmds

import hlib
from hlib.decorators.undo import undo_transaction


@undo_transaction("hrig.add_reverse_foot")
def add_reverse_foot(rig, heel=(-1, 0, 0), toe=(2, 0, 0), ball=(1, 0, 0)):
    """IK目標の下へheel→toe→ballの回転ピボットを重ねる。

    Args:
        rig (LimbRig): 構築済みの部位。
        heel (tuple): 足首原点・目標コントローラー空間の踵位置。
        toe (tuple): 同じ空間の爪先位置。
        ball (tuple): 同じ空間の母指球位置。

    Returns:
        dict[str, str]: ピボット名と生成したtransformの対応。

    Note:
        正Xを足先、Yを上とし、ロール軸はZ。LOD 1だけで有効。
        足ロールが非ゼロの姿勢からのIKマッチは未対応。
    """
    pivots = [tuple(float(v) for v in point) for point in (heel, toe, ball)]
    if any(len(point) != 3 or not all(math.isfinite(v) for v in point) for point in pivots):
        raise ValueError("Expected finite three-component pivots")
    root = rig.root.full_name()
    if hlib.node(root).has_attr("footMatrix"):
        raise ValueError("A reverse-foot layer already exists")
    target = rig.controls()["target"]
    for attr in ("heelRoll", "toeRoll", "ballRoll"):
        if hlib.node(target).has_attr(attr):
            raise ValueError("Target attribute already exists: " + attr)
    group = hlib.createNode(
        "transform", name=rig.node_name("footGroup"), parent=target, skipSelect=True
    ).full_name()
    from .limb import _lock_group

    _lock_group(group)
    rig._bind("footGroup", group)
    parent = group
    created = [group]
    result = {}
    for role, pivot in zip(("heel", "toe", "ball"), pivots):
        node = hlib.createNode(
            "transform", name=rig.node_name(role), parent=parent, skipSelect=True
        ).full_name()
        created.append(node)
        result[role] = node
        hlib.plug(node + ".rotatePivot").set((*pivot,))
        hlib.node(target).add_attr(
            long_name=role + "Roll", attribute_type="doubleAngle", keyable=True
        )
        hlib.plug(target + "." + role + "Roll").connect(node + ".rotateZ")
        parent = node
    matrix = hlib.createNode(
        "multMatrix", name=rig.node_name("footMatrix"), skipSelect=True
    ).full_name()
    decompose = hlib.createNode(
        "decomposeMatrix", name=rig.node_name("footDecompose"), skipSelect=True
    ).full_name()
    created.extend((matrix, decompose))
    for index, node in enumerate((result["ball"], result["toe"], result["heel"])):
        hlib.plug(node + ".matrix").connect(matrix + ".matrixIn[{}]".format(index))
    hlib.plug(rig._local_matrix("target")).connect(matrix + ".matrixIn[3]")
    hlib.plug(matrix + ".matrixSum").connect(decompose + ".inputMatrix")
    rig._bind("footMatrix", matrix)
    rig._bind("footDecompose", decompose)
    layer = cmds.sets(created, name=rig.node_name("footSet"))
    created.append(layer)
    rig._bind("footSet", layer)
    rig._layer_members("moduleSet", [layer])
    hlib.node(root).add_attr(long_name="hrigFootSettings", data_type="string")
    hlib.plug(root + ".hrigFootSettings").set(
        json.dumps(dict(zip(("heel", "toe", "ball"), pivots)))
    )
    indices = cmds.getAttr(root + ".hrigOwned", multiIndices=True) or []
    first = max(indices, default=-1) + 1
    for index, node in enumerate(created, first):
        hlib.plug(node + ".message").connect(root + ".hrigOwned[{}]".format(index))
    rig._update_evaluation()
    return result
