"""3関節部位のIKへ後付けする、ローカル行列ベースのリバースフット。"""

import math
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
    if hlib.getNode(root).has_attribute("footMatrix"):
        raise ValueError("A reverse-foot layer already exists")
    target = rig.controls()["target"]
    for attr in ("heelRoll", "toeRoll", "ballRoll"):
        if hlib.getNode(target).has_attribute(attr):
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
        hlib.getPlug(node + ".rotatePivot").set((*pivot,))
        hlib.getNode(target).add_attribute(
            long_name=role + "Roll", attribute_type="doubleAngle", keyable=True
        )
        hlib.getPlug(target + "." + role + "Roll").connect(node + ".rotateZ")
        parent = node
    matrix = hlib.createNode(
        "multMatrix", name=rig.node_name("footMatrix"), skipSelect=True
    ).full_name()
    decompose = hlib.createNode(
        "decomposeMatrix", name=rig.node_name("footDecompose"), skipSelect=True
    ).full_name()
    created.extend((matrix, decompose))
    for index, node in enumerate((result["ball"], result["toe"], result["heel"])):
        hlib.getPlug(node + ".matrix").connect(matrix + ".matrixIn[{}]".format(index))
    hlib.getPlug(rig._local_matrix("target")).connect(matrix + ".matrixIn[3]")
    hlib.getPlug(matrix + ".matrixSum").connect(decompose + ".inputMatrix")
    rig._bind("footMatrix", matrix)
    rig._bind("footDecompose", decompose)
    layer = hlib.createSet(created, name=rig.node_name("footSet")).full_name()
    created.append(layer)
    rig._bind("footSet", layer)
    rig._layer_members("moduleSet", [layer])
    hlib.getNode(root).add_attribute(long_name="hrigFootSettings", data_type="string")
    hlib.getPlug(root + ".hrigFootSettings").set(
        hlib.json.JsonText.dumps(dict(zip(("heel", "toe", "ball"), pivots)))
    )
    for node in created:
        hlib.getNode(root).plug("hrigOwned").append_message(node)
    rig._update_evaluation()
    return result
