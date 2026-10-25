"""丸い底(揺り椅子の脚・丸い足の裏)が床の上を滑らずに転がるよう、支点を接地点へ動かす標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution

AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def _cross(a, b):
    """3次元ベクトルの外積。"""
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


class RockerRoll(TwistDistribution):
    """半径 radius の円弧の底を持つ物体を、roll の角度だけ床の上で転がした行列(動く支点、rolling pivot)。

    円弧の中心 c(接地点から上へ radius)の周りに roll だけ回し、同時に中心を ``radius * roll(rad)`` だけ
    転がる向き(軸 × 上)へ送る。転がった弧の長さと床の上の移動量が等しいので底は滑らず、支点(接地点)は
    角度とともに円弧の上を移っていく。フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def localMatrix(cls, roll, radius, axis="x", upAxis="y", contact=(0.0, 0.0, 0.0)):
        """対象のローカルでの転がりの行列を計算する(DGと同じ式のPython版)。

        Args:
            roll (float): 転がす角度(ラジアン)。
            radius (float): 底の円弧の半径。
            axis (str): 回転軸 x/y/z(対象のローカル)。
            upAxis (str): 上の軸 x/y/z(対象のローカル)。
            contact (Sequence[float]): 生成時の接地点(対象のローカル)。

        Returns:
            Matrix: ``T(-c) * R_axis(roll) * T(c + radius * roll * (axis × up))`` (行ベクトル規約)。
        """
        a, u = AXES[axis], AXES[upAxis]
        center = [contact[i] + radius * u[i] for i in range(3)]
        forward = _cross(a, u)
        values = [0.0] * 16
        cosine, sine = math.cos(roll), math.sin(roll)
        index = "xyz".index(axis)
        rows = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        j, k = (index + 1) % 3, (index + 2) % 3
        rows[j][j], rows[j][k], rows[k][j], rows[k][k] = cosine, sine, -sine, cosine
        for r in range(3):
            values[r * 4:r * 4 + 3] = rows[r]
        moved = [center[i] + radius * roll * forward[i] for i in range(3)]
        values[12:15] = [moved[i] - sum(center[r] * rows[r][i] for r in range(3)) for i in range(3)]
        values[15] = 1.0
        return Matrix(values)

    @classmethod
    @undoTransaction("mlrig.RockerRoll.create")
    def create(cls, target, radius, name="rockerRoll", axis="x", upAxis="y", contact=(0.0, 0.0, 0.0)):
        """対象の物体を、丸い底で床の上を転がす行列を生成する。

        Args:
            target (str | Node): 転がす物体のtransform。生成時の姿勢と親の空間を基準にする。
            radius (float): 底の円弧の半径(0より大きい、cm)。
            name (str): 一意なcontainer名。
            axis (str): 転がる回転軸 x/y/z(対象のローカル)。
            upAxis (str): 対象のローカルの上の軸 x/y/z(axisと別の軸)。
            contact (Sequence[float]): 生成時の接地点(対象のローカル、cm)。円弧の中心は ``contact + radius * up`` 。

        Returns:
            RockerRoll: matrix・travel の所有者。containerに roll(角度)・radius(長さ)を持つ。

        Raises:
            ValueError: 対象がtransformでない場合、軸・半径・接地点が不正な場合、またはnameが既に存在する場合。

        Note:
            matrix = T(-c) * R_axis(roll) * T(radius * roll * (axis × up)) * T(c) * L0 * 親の worldMatrix、c = contact + radius * up
            (行ベクトル規約、L0は生成時の対象のローカル行列)。roll = 0 で生成時のワールド行列と一致する(跳ねない)。
            出力はワールド行列なので、ワールド直下のtransformの offsetParentMatrix へ接続する
            (対象自身へ繋ぐ場合は、対象をワールド直下に置き、translate・rotateを0にしてから接続する)。
        """
        if axis not in AXES or upAxis not in AXES or axis == upAxis:
            raise ValueError("axis and upAxis must be different axes of x, y or z")
        radius = float(radius)
        if not math.isfinite(radius) or radius <= 0.0:
            raise ValueError("radius must be a finite value greater than 0")
        contact = [float(value) for value in contact]
        if len(contact) != 3 or not all(math.isfinite(value) for value in contact):
            raise ValueError("contact must be a finite 3D point")
        if mlib.ls(name):
            raise ValueError("RockerRoll container already exists: " + name)
        target = mlib.nodes.Node(target)
        if not isinstance(target, mlib.nodes.Transform):
            raise ValueError("Expected a transform for the target")

        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        owner.addAttr(longName="roll", attributeType="doubleAngle", defaultValue=0.0, keyable=True)
        owner.addAttr(longName="radius", attributeType="doubleLinear", defaultValue=radius, minValue=1e-6,
                      keyable=True)
        owner.addAttr(longName="travel", attributeType="doubleLinear")
        owner.addAttr(longName="matrix", dataType="matrix")

        # travel = radius * roll(rad)。角度・長さは係数1の unitConversion で内部単位(rad・cm)のまま数値にする。
        numbers = []
        for label in ("roll", "radius"):
            plain = graph._node("unitConversion", label + "Number")
            plain.getPlug("conversionFactor").set(1.0)
            owner.getPlug(label).connectTo(plain.getPlug("input"))
            numbers.append(plain.getPlug("output"))
        product = graph._node("multiplyDivide", "travelProduct")
        numbers[0].connectTo(product.getPlug("input1X"))
        numbers[1].connectTo(product.getPlug("input2X"))
        length = graph._node("unitConversion", "travelLength")
        length.getPlug("conversionFactor").set(1.0)
        product.getPlug("outputX").connectTo(length.getPlug("input"))
        length.getPlug("output").connectTo(owner.getPlug("travel"))

        # 中心の送り = travel * (axis × up)。axis × up は ±1 の1軸なので、符号付きの係数で1つの成分へ渡す。
        forward = _cross(AXES[axis], AXES[upAxis])
        slot = max(range(3), key=lambda i: abs(forward[i]))
        roll = graph._node("composeMatrix", "roll")
        owner.getPlug("roll").connectTo(roll.getPlug("inputRotate" + axis.upper()))
        send = graph._node("unitConversion", "travelForward")
        send.getPlug("conversionFactor").set(forward[slot])
        owner.getPlug("travel").connectTo(send.getPlug("input"))
        send.getPlug("output").connectTo(roll.getPlug("inputTranslate" + "XYZ"[slot]))

        # 中心 c = contact + radius * up。radiusを変えても中心が付いてくるよう、radius の分は composeMatrix で作る。
        slot_up = "xyz".index(upAxis)
        offsets = []
        for label, sign in (("centerDown", -1.0), ("centerUp", 1.0)):
            shift = graph._node("unitConversion", label + "Length")
            shift.getPlug("conversionFactor").set(sign)
            owner.getPlug("radius").connectTo(shift.getPlug("input"))
            compose = graph._node("composeMatrix", label)
            shift.getPlug("output").connectTo(compose.getPlug("inputTranslate" + "XYZ"[slot_up]))
            offsets.append(compose.getPlug("outputMatrix"))
        rest = Matrix(target.getPlug("matrix").get()) * Matrix(target.getPlug("offsetParentMatrix").get())
        chain = graph._node("multMatrix", "matrix")
        before = Matrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -contact[0], -contact[1], -contact[2], 1])
        after = Matrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, contact[0], contact[1], contact[2], 1])
        chain.getPlug("matrixIn")[0].set(before)
        offsets[0].connectTo(chain.getPlug("matrixIn")[1])
        roll.getPlug("outputMatrix").connectTo(chain.getPlug("matrixIn")[2])
        offsets[1].connectTo(chain.getPlug("matrixIn")[3])
        chain.getPlug("matrixIn")[4].set(after * rest)
        # jointの parentMatrix は offsetParentMatrix を含むので、親の worldMatrix を直接使う(ワールド直下なら無し)。
        parent = target.getParent()
        if parent is not None:
            parent.getPlug("worldMatrix")[0].connectTo(chain.getPlug("matrixIn")[5])
        chain.getPlug("matrixSum").connectTo(owner.getPlug("matrix"))
        owner.setAttrFlags(["travel", "matrix"], keyable=False)
        return graph
