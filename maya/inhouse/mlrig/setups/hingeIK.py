"""膝(中間のjoint)をヒンジ軸の1軸だけで曲げるRotate Plane IK。"""

from maya import cmds

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector


def worldPosition(node):
    """transformのワールド位置を返す。

    Args:
        node (str | Node): transform。

    Returns:
        Vector: 位置(シーンの長さの単位)。
    """
    translate = mlib.getNode(node).getTranslation(worldSpace=True, at=4)
    return Vector(*(mlib.common.units.distanceToUi(value) for value in translate))


def worldMatrix(node):
    """transformのワールド行列を返す。

    Args:
        node (str | Node): transform。

    Returns:
        Matrix: 行列(移動はシーンの長さの単位)。
    """
    matrix = Matrix(mlib.getNode(node).getMatrix(worldSpace=True))
    for column in range(3):
        matrix.setElement(3, column, mlib.common.units.distanceToUi(matrix.getElement(3, column)))
    return matrix


def planeNormal(root, mid, end):
    """3点の位置が作る平面の法線(root→mid と mid→end の外積)を返す。

    Args:
        root (str | Node): 付け根のtransform。
        mid (str | Node): 膝のtransform。
        end (str | Node): 足首のtransform。

    Returns:
        Vector | None: 単位ベクトル。3点がほぼ一直線ならNone。
    """
    normal = (worldPosition(mid) - worldPosition(root)) ^ (worldPosition(end) - worldPosition(mid))
    if normal.length() < 1e-6:
        return None
    return Vector(normal.normal())


def orientationMatrix(position, aim, hinge, hingeAxis):
    """骨の向き(ローカルX)とヒンジ軸から、ワールドの回転行列を作る。

    Args:
        position (Sequence[float]): 行列の移動。
        aim (Sequence[float]): ローカルXにする向き。
        hinge (Sequence[float]): ヒンジ軸(``hingeAxis`` にする向き)。ローカルXに直交していなくてよい。
        hingeAxis (str): ヒンジ軸にするローカル軸 ``"y"`` または ``"z"``。

    Returns:
        Matrix: 行列。ヒンジ軸は ``hinge`` と完全に一致させ、ローカルXは ``aim`` をヒンジ軸に直交するよう補正する。

    Raises:
        ValueError: ``aim`` と ``hinge`` がほぼ平行な場合。
    """
    hinge = Vector(*hinge).normal()
    aim = Vector(*aim)
    x = aim - hinge * (aim * hinge)
    if x.length() < 1e-6:
        raise ValueError("The bone points along the hinge axis.")
    x.normalize()
    if hingeAxis == "z":
        z, y = hinge, hinge ^ x
    else:
        y, z = hinge, x ^ hinge
    position = Vector(*position)
    return Matrix([x.x, x.y, x.z, 0, y.x, y.y, y.z, 0, z.x, z.y, z.z, 0, position.x, position.y, position.z, 1])


def setJointWorldOrientation(joint, matrix):
    """jointの向きをワールド行列の回転に合わせる。子孫のワールドの位置・向きは保つ。

    rotate・rotateAxisを0にし、親空間での回転をjointOrientへ入れる。位置は変えない。

    Args:
        joint (str | Node): 対象のjoint。
        matrix (Matrix): 目標のワールド行列(回転だけを使う)。
    """
    joint = mlib.getNode(joint)
    children = [mlib.getNode(child) for child in
                cmds.listRelatives(joint.getFullName(), children=True, type="transform", fullPath=True) or []]
    saved = [(child, child.getMatrix(worldSpace=True)) for child in children]
    parent = Matrix(joint.getPlug("parentMatrix")[0].get())
    rotation = Matrix(Matrix(matrix) * parent.inverse()).euler
    joint.getPlug("rotate").set((0, 0, 0))
    joint.getPlug("rotateAxis").set((0, 0, 0))
    joint.getPlug("jointOrient").set((rotation.x, rotation.y, rotation.z), unit="rad")
    for child, child_matrix in saved:
        child.setMatrix(child_matrix, worldSpace=True)


def storePreferredAngles(joints):
    """各jointのpreferredAngleを今のrotateにする(Skeleton > Set Preferred Angle と同じ)。

    Rotate Plane IKはpreferredAngleの姿勢から曲げる平面を決めるため、今の姿勢と違う値が入っていると
    IKを作った瞬間に姿勢が跳ねる。生成時の姿勢(少し曲げたbindポーズ)をそのまま使う。

    Args:
        joints (Iterable[str | Node]): 対象のjoint。
    """
    for joint in joints:
        cmds.joint(str(joint), edit=True, setPreferredAngles=True)


def createRotatePlaneHandle(root, end, name, poleDistance=None):
    """Rotate Plane IKとポールベクターのlocatorを作る。作った瞬間に姿勢が跳ねないようにする。

    locatorは、IKが作成時に決めたポールベクター(``ikHandle.poleVector``)の向きの延長上に置く。

    Args:
        root (str | Node): 付け根のjoint。
        end (str | Node): 足首のjoint。
        name (str): 名前の先頭。
        poleDistance (float | None): 付け根からlocatorまでの距離。Noneならチェーンの全長。

    Returns:
        tuple[str, str, str]: (ikHandle, effector, ポールベクターのlocator)。
    """
    handle, effector = cmds.ikHandle(startJoint=str(root), endEffector=str(end), solver="ikRPsolver",
                                     name=name + "_ikHandle")
    effector = mlib.getNode(effector)
    effector.rename(name + "_effector")
    effector = effector.getFullName()
    handleNode = mlib.getNode(handle)
    # poleVector はikHandleの親の空間の向き(作った直後のikHandleはワールド直下なので、ワールドの向き)。
    parent = Matrix(handleNode.getPlug("parentMatrix")[0].get())
    direction = (Vector(*handleNode.getPlug("poleVector").get()) * parent).normal()
    if poleDistance is None:
        joints = cmds.ikHandle(handle, query=True, jointList=True) + [str(end)]
        poleDistance = sum((worldPosition(b) - worldPosition(a)).length() for a, b in zip(joints, joints[1:]))
    position = worldPosition(root) + direction * poleDistance
    pole = mlib.getNode(cmds.spaceLocator(name=name + "_pole")[0])
    # locatorはワールド直下なので、translateがそのままワールド位置になる。
    pole.getPlug("translate").set(tuple(mlib.common.units.distanceFromUi(value) for value in position))
    cmds.poleVectorConstraint(pole.getFullName(), handleNode.getFullName(), name=name + "_poleVectorConstraint")
    return handleNode.getFullName(), effector, pole.getFullName()


def groupUnderWorld(name, *nodes):
    """ワールド直下に原点のtransformを作り、``nodes`` をワールドの位置を保って子にする(``cmds.group`` と同じ)。

    Args:
        name (str): transformの名前。
        *nodes (str): 子にするノード。

    Returns:
        tuple[str, list[str]]: (transformのフルパス, 子にしたノードのフルパス)。
    """
    group = mlib.createNode("transform", name=name, skipSelect=True).getFullName()
    children = [mlib.getNode(cmds.parent(node, group)[0]).getFullName() for node in nodes]
    return group, children


class HingeIK:
    """膝のjointの向きをヒンジ軸へ合わせ、自由度(Degrees of Freedom)を1軸にしたRotate Plane IK。

    付け根・膝・足首が一平面に並ばない脚(膝が横にずれた機械の脚など)でも、膝はヒンジ軸だけで曲がる。
    Rotate Plane IK(``ikRPsolver``)はjointの自由度(``dofMask``)を守って解くため、足首は目標に届き、
    足りない分は付け根が3軸で回って補う。

    Attributes:
        container (str): 生成物を所有するcontainer。
        handle (str): ikHandle。足首の目標(フットコントロールなど)に親子付けして使う。
        pole (str): ポールベクターのlocator。脚の向き(膝の向き)を決める。
        joints (tuple[str, str, str]): (付け根, 膝, 足首)。
        hinge (Vector): ワールドのヒンジ軸。
        axis (str): 膝のヒンジ軸にしたローカル軸。
    """

    def __init__(self, container, handle, pole, joints, hinge, axis):
        """生成結果をまとめる。

        Args:
            container (str): container。
            handle (str): ikHandle。
            pole (str): ポールベクターのlocator。
            joints (tuple[str, str, str]): (付け根, 膝, 足首)。
            hinge (Vector): ワールドのヒンジ軸。
            axis (str): 膝のヒンジ軸にしたローカル軸。
        """
        self.container = container
        self.handle = handle
        self.pole = pole
        self.joints = joints
        self.hinge = hinge
        self.axis = axis

    @classmethod
    @undoTransaction("mlrig.HingeIK.create")
    def create(cls, root, mid, end, name="hingeIK", hinge=None, axis="z", poleDistance=None):
        """膝の向きと自由度を設定し、Rotate Plane IKとポールベクターを作る。

        Args:
            root (str): 付け根のjoint(股関節)。
            mid (str): 膝のjoint。``root`` の直接の子。
            end (str): 足首のjoint。``mid`` の直接の子。
            name (str): 生成物の名前の先頭(containerの名前)。
            hinge (Sequence[float] | None): ワールドのヒンジ軸(模型の膝の回転軸)。Noneなら3点の平面の法線。
            axis (str): 膝のヒンジ軸にするローカル軸 ``"y"`` または ``"z"``。骨の向きはローカルX。
            poleDistance (float | None): 付け根からポールベクターのlocatorまでの距離。Noneならチェーンの全長。

        Returns:
            HingeIK: 生成結果。

        Raises:
            ValueError: jointの親子関係・軸が正しくない、3点が一直線でヒンジ軸を決められない場合。

        Note:
            生成時の姿勢を基準にする(bindポーズで実行する)。膝のrotate・rotateAxisは0にし、向きはjointOrientへ入れる。
            足首など膝の子のワールドの位置・向きは変えない。
            ヒンジ軸は骨(膝→足首)に直交していなくてよい。ローカルXは骨の向きをヒンジ軸に直交するよう補正したもので、
            足首の位置はローカルXから外れることがある。
        """
        if axis not in ("y", "z"):
            raise ValueError("axis must be y or z (the bone points along local X)")
        for joint in (root, mid, end):
            if not cmds.objExists(joint) or mlib.getNode(joint).getType() != "joint":
                raise ValueError("Joint not found: {}".format(joint))
        if _parent(mid) != _longName(root) or _parent(end) != _longName(mid):
            raise ValueError("Expected a chain root -> mid -> end of direct children.")
        if hinge is None:
            hinge = planeNormal(root, mid, end)
            if hinge is None:
                raise ValueError("The chain is straight. Bend the knee slightly or pass the hinge axis.")
        hinge = Vector(*hinge).normal()
        owner = mlib.nodes.Container.create(name).getFullName()
        setJointWorldOrientation(mid, orientationMatrix(worldPosition(mid), worldPosition(end) - worldPosition(mid),
                                                        hinge, axis))
        cmds.joint(mid, edit=True, degreeOfFreedom=axis)
        storePreferredAngles((root, mid, end))
        handle, effector, pole = createRotatePlaneHandle(root, end, name, poleDistance)
        group, (handle, pole) = groupUnderWorld(name + "_GRP", handle, pole)
        mlib.nodes.Container(owner).addMembers(group, handle, pole)
        return cls(owner, handle, pole, (root, mid, end), hinge, axis)


def _longName(node):
    """フルパス名を返す。"""
    return mlib.getNode(node).getFullName()


def _parent(node):
    """親のフルパス名を返す(無ければNone)。"""
    parents = cmds.listRelatives(node, parent=True, fullPath=True)
    return parents[0] if parents else None
