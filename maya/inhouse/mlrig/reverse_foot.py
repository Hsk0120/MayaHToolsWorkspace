"""3関節部位のIKへ後付けする、ローカル行列ベースのリバースフット。"""

import math
import mlib

from mlib.decorator import undoTransaction


@undoTransaction("mlrig.add_reverse_foot")
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
    root = rig.root.getFullName()
    if mlib.getNode(root).hasAttr("footMatrix"):
        raise ValueError("A reverse-foot layer already exists")
    target = rig.controls()["target"]
    for attr in ("heelRoll", "toeRoll", "ballRoll"):
        if mlib.getNode(target).hasAttr(attr):
            raise ValueError("Target attribute already exists: " + attr)
    group = mlib.createNode(
        "transform", name=rig.getNodeName("footGroup"), parent=target, skipSelect=True
    ).getFullName()
    from .limb import _lock_group

    _lock_group(group)
    rig._bind("footGroup", group)
    parent = group
    created = [group]
    result = {}
    for role, pivot in zip(("heel", "toe", "ball"), pivots):
        node = mlib.createNode(
            "transform", name=rig.getNodeName(role), parent=parent, skipSelect=True
        ).getFullName()
        created.append(node)
        result[role] = node
        mlib.getPlug(node + ".rotatePivot").set((*pivot,))
        mlib.getNode(target).addAttr(
            longName=role + "Roll", attributeType="doubleAngle", keyable=True
        )
        mlib.getPlug(target + "." + role + "Roll").connectTo(node + ".rotateZ")
        parent = node
    matrix = mlib.createNode(
        "multMatrix", name=rig.getNodeName("footMatrix"), skipSelect=True
    ).getFullName()
    decompose = mlib.createNode(
        "decomposeMatrix", name=rig.getNodeName("footDecompose"), skipSelect=True
    ).getFullName()
    created.extend((matrix, decompose))
    for index, node in enumerate((result["ball"], result["toe"], result["heel"])):
        mlib.getPlug(node + ".matrix").connectTo(mlib.getNode(matrix).getPlug("matrixIn")[index])
    mlib.getPlug(rig._local_matrix("target")).connectTo(mlib.getNode(matrix).getPlug("matrixIn")[3])
    mlib.getPlug(matrix + ".matrixSum").connectTo(decompose + ".inputMatrix")
    rig._bind("footMatrix", matrix)
    rig._bind("footDecompose", decompose)
    layer = mlib.createSet(created, name=rig.getNodeName("footSet")).getFullName()
    created.append(layer)
    rig._bind("footSet", layer)
    rig._layer_members("moduleSet", [layer])
    mlib.getNode(root).addAttr(longName="mlrigFootSettings", dataType="string")
    mlib.getPlug(root + ".mlrigFootSettings").set(
        mlib.json.JsonText.dumps(dict(zip(("heel", "toe", "ball"), pivots)))
    )
    for node in created:
        mlib.getNode(root).getPlug("mlrigOwned").appendMessage(node)
    rig._update_evaluation()
    return result
