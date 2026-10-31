"""向きの整ったIK用の平面チェーンで解き、元のjointへ回転だけを渡すIK。"""


import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.hingeIK import (createRotatePlaneHandle, groupUnderWorld, orientationMatrix, planeNormal,
                                  setJointWorldOrientation, storePreferredAngles, worldPosition)


class PlanarIK:
    """付け根・膝・足首の回転中心へIK用のjointを3本作ってIKで解き、元のjointへ回転を渡す。

    IK用のjointは一平面上に並び、膝は平面の法線(ローカルZ)の1軸だけで曲がる。元のjointは、
    途中にずれた骨(オフセットの骨)が挟まっていても、向き(jointOrient)がばらばらでもよい。
    元の付け根と膝は、IK用のjointの回転をオフセット付きの ``orientConstraint`` で受け取る。
    回転の中心が同じなので、途中の骨を含めて元のjointの位置はIK用のjointと一致する。

    Attributes:
        container (str): 生成物を所有するcontainer。
        handle (str): ikHandle。足首の目標(フットコントロールなど)に親子付けして使う。
        pole (str): ポールベクターのlocator。
        drivers (tuple[str, str, str]): IK用のjoint(付け根, 膝, 足首)。
        joints (tuple[str, str, str]): 元のjoint(付け根, 膝, 足首)。
        normal (Vector): IK用チェーンの平面の法線(膝の曲がる軸。ワールド)。
    """

    def __init__(self, container, handle, pole, drivers, joints, normal):
        """生成結果をまとめる。

        Args:
            container (str): container。
            handle (str): ikHandle。
            pole (str): ポールベクターのlocator。
            drivers (tuple[str, str, str]): IK用のjoint。
            joints (tuple[str, str, str]): 元のjoint。
            normal (Vector): 平面の法線。
        """
        self.container = container
        self.handle = handle
        self.pole = pole
        self.drivers = drivers
        self.joints = joints
        self.normal = normal

    @classmethod
    @undoTransaction("mlrig.PlanarIK.create")
    def create(cls, root, mid, end, name="planarIK", poleDistance=None, showDrivers=False):
        """IK用の平面チェーン・Rotate Plane IK・ポールベクターを作り、元のjointへ回転を渡す。

        Args:
            root (str): 元の付け根のjoint(股関節の回転中心)。
            mid (str): 元の膝のjoint(膝の回転中心)。``root`` の子孫。間に別のjointがあってよい。
            end (str): 元の足首のjoint(足首の回転中心)。``mid`` の子孫。間に別のjointがあってよい。
            name (str): 生成物の名前の先頭(containerの名前)。
            poleDistance (float | None): 付け根からポールベクターのlocatorまでの距離。Noneならチェーンの全長。
            showDrivers (bool): IK用のjointを表示するか。

        Returns:
            PlanarIK: 生成結果。

        Raises:
            ValueError: jointの親子関係が正しくない、3点が一直線で平面を決められない場合。

        Note:
            生成時の姿勢を基準にする(bindポーズで実行する)。元のjointの値は書き換えず、
            付け根と膝のrotateへorientConstraintを接続する。足首の向きは膝からの親子関係のまま
            (フットコントロールに合わせる場合は、足首へ別にorientConstraintを付ける)。
            IK用のjointは元の付け根の親の子として作るので、骨盤などの親の動きに付いていく。
        """
        for joint in (root, mid, end):
            if not mlib.objExists(joint) or mlib.nodes.Node(joint).getType() != "joint":
                raise ValueError("Joint not found: {}".format(joint))
        if not _isAncestor(root, mid) or not _isAncestor(mid, end):
            raise ValueError("Expected root -> ... -> mid -> ... -> end in one hierarchy.")
        normal = planeNormal(root, mid, end)
        if normal is None:
            raise ValueError("The chain is straight. Bend the knee slightly before creating the IK.")
        owner = mlib.createContainer(name).getFullName()
        positions = [worldPosition(node) for node in (root, mid, end)]
        parent = mlib.nodes.Node(root).getParent()
        drivers = []
        for label, position in zip(("root", "mid", "end"), positions):
            # ワールド直下に作って位置を入れ、ワールドの位置を保って親子付けする(cmds.joint と同じ結果)。
            joint = mlib.createNode("joint", name="{}_{}Driver".format(name, label), skipSelect=True)
            joint.getPlug("translate").set(tuple(mlib.common.units.distanceFromUi(value) for value in position))
            target = drivers[-1] if drivers else parent
            if target is not None:
                joint.setParent(target)
            drivers.append(joint.getFullName())
        # 骨の向きをローカルX、平面の法線をローカルZにする(足首は膝と同じ向き)。
        for index, joint in enumerate(drivers):
            aim = positions[min(index + 1, 2)] - positions[min(index, 1)]
            setJointWorldOrientation(joint, orientationMatrix(positions[index], aim, normal, "z"))
        mid_driver = mlib.nodes.Node(drivers[1])
        for letter in "XYZ":
            mid_driver.getPlug("jointType" + letter).set(letter == "Z")
        storePreferredAngles(drivers)
        handle, effector, pole = createRotatePlaneHandle(drivers[0], drivers[2], name, poleDistance)
        group, (handle, pole) = groupUnderWorld(name + "_GRP", handle, pole)
        constraints = [mlib.nodes.Node(joint).addConstraint(driver, type="orient", maintainOffset=True,
                                                         name="{}_{}OrientConstraint".format(name, label)).getFullName()
                       for driver, joint, label in zip(drivers[:2], (root, mid), ("root", "mid"))]
        mlib.nodes.Node(drivers[0]).getPlug("visibility").set(showDrivers)
        mlib.nodes.Container(owner).addMembers(group, handle, pole, *(drivers + constraints))
        return cls(owner, handle, pole, tuple(drivers), (root, mid, end), normal)


def _isAncestor(ancestor, node):
    """``ancestor`` が ``node`` の祖先か(同じノードは含まない)。"""
    return mlib.nodes.Node(node).getFullName().startswith(mlib.nodes.Node(ancestor).getFullName() + "|")
