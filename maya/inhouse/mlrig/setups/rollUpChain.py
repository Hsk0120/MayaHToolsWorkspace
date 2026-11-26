"""joint列を端から1関節ずつ順に曲げ、舌・尻尾・巻物・触手を巻き取る回転を標準DGで構築する。"""

import math

import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution


class RollUpChain(TwistDistribution):
    """rollを増やすと、端の関節から順に軸まわりへ曲がって渦巻きに巻き取られる標準DG。

    rollは「巻き終えた関節の数」で、届く範囲(0〜N-1+width)の外は端で止めて超えた量をexcessへ出す。
    フレームごとのPythonやエクスプレッションは使わず、rollへキーを打てばそのまま動く。
    """

    @classmethod
    def rollAngles(cls, count, roll, angle, decay=1.0, width=1.0, fromRoot=False):
        """各関節の回転角と、止めたroll・超えた量を計算する(DGと同じ式のPython版)。

        Args:
            count (int): 関節の数。
            roll (float): 巻き取りの量(巻き終えた関節の数)。
            angle (float): 最初に巻く関節が巻き終えたときの角度(度)。
            decay (float): 巻く順が1つ後になるごとに角度へ掛ける倍率。
            width (float): 同時に曲がっていく関節の数(1関節が曲がり終えるまでのrollの幅)。
            fromRoot (bool): Trueなら根元から、Falseなら先端から巻く。

        Returns:
            tuple[list[float], float, float]: 各関節の回転角(度)、止めたroll、超えた量(roll - 止めたroll)。
        """
        limit = count - 1 + width
        rolled = min(max(roll, 0.0), limit)
        angles = []
        for index in range(count):
            order = index if fromRoot else count - 1 - index
            weight = min(max((rolled - order) / width, 0.0), 1.0)
            angles.append(angle * decay ** order * weight)
        return angles, rolled, roll - rolled

    @classmethod
    @undoTransaction("mlrig.RollUpChain.create")
    def create(cls, joints, name="rollUpChain", axis="z", angle=60.0, decay=1.0, width=1.0, fromRoot=False):
        """各関節の親空間行列を生成する。

        Args:
            joints (list[str | Node]): 根元から先端へ、親子に並んだ2つ以上のtransform。
            name (str): 一意なcontainer名。
            axis (str): 各関節のローカルで曲げる回転軸x/y/z。
            angle (float): 最初に巻く関節が巻き終えたときの角度。度、-180〜180。
            decay (float): 巻く順が1つ後になるごとに角度へ掛ける倍率。0.1〜1。1で円、1未満で外へ広がる渦巻き。
            width (float): 同時に曲がっていく関節の数。0.01以上。1で1関節ずつ、大きいほどなだらかに巻く。
            fromRoot (bool): Trueなら根元から、Falseなら先端から巻く。

        Returns:
            RollUpChain: matrix0〜matrixN-1・angle0〜angleN-1・rolled・excess・totalAngleの所有者。
            containerのrollで巻き取る。

        Raises:
            ValueError: 関節の並び・軸・値が不正な場合、またはnameが既に存在する場合。

        Note:
            巻く順 j は、先端から巻くとき j = N-1-i、根元から巻くとき j = i。
            rolled = clamp(roll, 0, N-1+width)、excess = roll - rolled、
            重み w_i = clamp((rolled - j)/width, 0, 1)、角度 θ_i = angle * decay^j * w_i(度)、
            totalAngle = Σθ_i。
            出力 matrix_i は、関節iの現在のローカル行列(matrix * offsetParentMatrix)の前に、
            ローカルのaxisまわりのθ_iの回転を掛けた行列(行ベクトル規約)。位置は入力のまま。
            rollの既定は0なので、生成時に姿勢は変わらない。
            出力の関節も入力と同じ親子に並べ、各出力をoffsetParentMatrixへ接続する。
            負・非一様scaleは対象外。
        """
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be x, y or z")
        for value in (angle, decay, width):
            if not math.isfinite(value):
                raise ValueError("angle, decay and width must be finite")
        if not -180 <= angle <= 180:
            raise ValueError("angle must be between -180 and 180 degrees")
        if not 0.1 <= decay <= 1:
            raise ValueError("decay must be between 0.1 and 1")
        if width < 0.01:
            raise ValueError("width must be at least 0.01 joints")
        if mlib.objExists(name):
            raise ValueError("RollUpChain container already exists: " + name)
        joints = [mlib.Node(joint) for joint in joints]
        if len(joints) < 2 or any(not isinstance(joint, mlib.Transform) for joint in joints):
            raise ValueError("Expected two or more transforms")
        for parent, child in zip(joints, joints[1:]):
            actual = child.getParent()
            if actual is None or actual != parent:
                raise ValueError("Each joint must be the direct child of the previous one")
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        scalar = ScalarGraph(owner)
        count = len(joints)
        owner.addAttr(longName="roll", attributeType="double", defaultValue=0.0, keyable=True)
        owner.addAttr(longName="angle", attributeType="double", defaultValue=angle,
                      minValue=-180, maxValue=180, keyable=True)
        owner.addAttr(longName="decay", attributeType="double", defaultValue=decay,
                      minValue=0.1, maxValue=1, keyable=True)
        owner.addAttr(longName="width", attributeType="double", defaultValue=width, minValue=0.01, keyable=True)
        outputs = ["rolled", "excess", "totalAngle"] + ["angle" + str(index) for index in range(count)]
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        for index in range(count):
            owner.addAttr(longName="matrix" + str(index), dataType="matrix")
        # rollを届く範囲 0〜N-1+width で止め、超えた量を出す。
        limit = scalar.sum("limit", owner.getPlug("width"), count - 1.0)
        stop = graph._node("clamp", "rollClamp")
        owner.getPlug("roll").connectTo(stop.getPlug("inputR"))
        limit.connectTo(stop.getPlug("maxR"))
        stop.getPlug("outputR").connectTo(owner.getPlug("rolled"))
        scalar.sum("excessRaw", owner.getPlug("roll"), owner.getPlug("rolled"), subtract=True).connectTo(
            owner.getPlug("excess")
        )
        # 巻く順 j の角度の倍率 decay^j を、掛け算の連鎖で作る(j = 0 は1)。
        strengths = [owner.getPlug("angle")]
        for order in range(1, count):
            strengths.append(scalar.multiply("strength" + str(order), strengths[-1], owner.getPlug("decay")))
        rotate = "inputRotate" + axis.upper()
        total = None
        for index, joint in enumerate(joints):
            role = "joint" + str(index)
            order = index if fromRoot else count - 1 - index
            # 重み w = clamp((rolled - j) / width, 0, 1)。
            progress = scalar.sum(role + "Progress", owner.getPlug("rolled"), float(order), subtract=True)
            ratio = scalar.multiply(role + "Ratio", progress, owner.getPlug("width"), operation=2)
            weight = graph._node("clamp", role + "Weight")
            ratio.connectTo(weight.getPlug("inputR"))
            weight.getPlug("maxR").set(1.0)
            scalar.multiply(role + "AngleRaw", strengths[order], weight.getPlug("outputR")).connectTo(
                owner.getPlug("angle" + str(index))
            )
            current = owner.getPlug("angle" + str(index))
            total = current if total is None else scalar.sum(role + "Total", total, current)
            # 関節のローカル行列の前に、ローカルのaxisまわりの回転を掛ける。
            curl = graph._node("composeMatrix", role + "Curl")
            angle_radians = graph._node("unitConversion", role + "AngleRadians")
            current.connectTo(angle_radians.getPlug("input"))
            angle_radians.getPlug("conversionFactor").set(math.pi / 180)
            angle_radians.getPlug("output").connectTo(curl.getPlug(rotate))
            local = graph._node("multMatrix", role + "Local")
            curl.getPlug("outputMatrix").connectTo(local.getPlug("matrixIn")[0])
            joint.getPlug("matrix").connectTo(local.getPlug("matrixIn")[1])
            joint.getPlug("offsetParentMatrix").connectTo(local.getPlug("matrixIn")[2])
            local.getPlug("matrixSum").connectTo(owner.getPlug("matrix" + str(index)))
        total.connectTo(owner.getPlug("totalAngle"))
        owner.setAttrFlags(outputs, keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph
