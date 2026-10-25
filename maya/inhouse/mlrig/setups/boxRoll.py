"""四角い断面の物体(箱・サイコロ)が床の上を縁(エッジ)で順に転がるよう、支点の縁を切り替える標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution

AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
QUARTER = math.pi / 2.0


def _cross(a, b):
    """3次元ベクトルの外積。"""
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _translation(vector):
    """平行移動だけの行列(行ベクトル規約)。"""
    return Matrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, vector[0], vector[1], vector[2], 1])


def _rotation(axis, angle):
    """axis の周りに angle(ラジアン)回す行列(行ベクトル規約、composeMatrix の回転と同じ向き)。"""
    values = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]
    index = "xyz".index(axis)
    j, k = (index + 1) % 3, (index + 2) % 3
    cosine, sine = math.cos(angle), math.sin(angle)
    values[j * 4 + j], values[j * 4 + k], values[k * 4 + j], values[k * 4 + k] = cosine, sine, -sine, cosine
    return Matrix(values)


class BoxRoll(TwistDistribution):
    """一辺 size の正方形の断面を持つ物体を、roll の角度だけ床の上で縁から縁へ転がした行列。

    roll を90度ごとの段 n = floor(roll / 90°) と段の中の角度 φ = roll - n·90° に分け、n 段だけ転がり終えた
    姿勢(n·90° 回り、n·size だけ前へ進む)から、前の下の縁を支点に φ だけ回す。90度ごとに支点の縁が次の縁へ
    移るので、底が床へ潜らず、滑らずに転がる(フレームごとのPython・エクスプレッションは使わない)。
    """

    @classmethod
    def localMatrix(cls, roll, size, axis="x", upAxis="y", contact=(0.0, 0.0, 0.0)):
        """対象のローカルでの転がりの行列を計算する(DGと同じ式のPython版)。

        Args:
            roll (float): 転がす角度(ラジアン)。
            size (float): 断面の正方形の一辺(cm)。
            axis (str): 回転軸 x/y/z(対象のローカル)。
            upAxis (str): 上の軸 x/y/z(対象のローカル)。
            contact (Sequence[float]): 生成時の底の面の中心(対象のローカル)。

        Returns:
            Matrix: ``T(-c)·R(n·90°)·T(c - e)·R(φ)·T(e + n·size·f)`` (行ベクトル規約)。
            c = contact + size/2·up(断面の中心)、f = axis × up(進む向き)、e = contact + size/2·f(前の下の縁)。
        """
        u, f = AXES[upAxis], _cross(AXES[axis], AXES[upAxis])
        step = math.floor(roll / QUARTER)
        partial = roll - step * QUARTER
        half = size / 2.0
        center = [contact[i] + half * u[i] for i in range(3)]
        edge = [contact[i] + half * f[i] for i in range(3)]
        return (_translation([-value for value in center]) * _rotation(axis, step * QUARTER)
                * _translation([center[i] - edge[i] for i in range(3)]) * _rotation(axis, partial)
                * _translation([edge[i] + step * size * f[i] for i in range(3)]))

    @classmethod
    @undoTransaction("mlrig.BoxRoll.create")
    def create(cls, target, size, name="boxRoll", axis="x", upAxis="y", contact=(0.0, 0.0, 0.0)):
        """対象の箱を、縁で順に床の上を転がす行列を生成する。

        Args:
            target (str | Node): 転がす物体のtransform。生成時の姿勢と親の空間を基準にする。
            size (float): 断面の正方形の一辺(0より大きい、cm)。生成時に固定する。
            name (str): 一意なcontainer名。
            axis (str): 転がる回転軸 x/y/z(対象のローカル)。
            upAxis (str): 対象のローカルの上の軸 x/y/z(axisと別の軸)。
            contact (Sequence[float]): 生成時の底の面の中心(対象のローカル、cm)。

        Returns:
            BoxRoll: matrix・step・travel の所有者。containerに roll(角度)を持つ。

        Raises:
            ValueError: 対象がtransformでない場合、軸・一辺・底の中心が不正な場合、またはnameが既に存在する場合。

        Note:
            matrix = localMatrix(roll) · L0 · 親の worldMatrix(L0 は生成時の対象のローカル行列)。
            step = floor(roll / 90°)(段の番号、負の角度では負)、travel = step · size(支点の縁が進んだ距離)。
            roll = 0 で生成時のワールド行列と一致する(跳ねない)。90度の倍数では底の面が床に平らに着き、
            段の切り替わりで値が連続する。出力はワールド行列なので、ワールド直下のtransformの
            offsetParentMatrix へ接続する。
        """
        if axis not in AXES or upAxis not in AXES or axis == upAxis:
            raise ValueError("axis and upAxis must be different axes of x, y or z")
        size = float(size)
        if not math.isfinite(size) or size <= 0.0:
            raise ValueError("size must be a finite value greater than 0")
        contact = [float(value) for value in contact]
        if len(contact) != 3 or not all(math.isfinite(value) for value in contact):
            raise ValueError("contact must be a finite 3D point")
        if mlib.ls(name):
            raise ValueError("BoxRoll container already exists: " + name)
        target = mlib.nodes.Node(target)
        if not isinstance(target, mlib.nodes.Transform):
            raise ValueError("Expected a transform for the target")

        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        owner.addAttr(longName="roll", attributeType="doubleAngle", defaultValue=0.0, keyable=True)
        owner.addAttr(longName="step", attributeType="double")
        owner.addAttr(longName="travel", attributeType="doubleLinear")
        owner.addAttr(longName="matrix", dataType="matrix")

        # 角度は係数1の unitConversion で内部単位(rad)のまま数値にする。
        number = graph._node("unitConversion", "rollNumber")
        number.getPlug("conversionFactor").set(1.0)
        owner.getPlug("roll").connectTo(number.getPlug("input"))
        # n = floor(roll / 90°)
        quarters = graph._node("multiplyDivide", "quarters")
        quarters.getPlug("operation").set(2)
        number.getPlug("output").connectTo(quarters.getPlug("input1X"))
        quarters.getPlug("input2X").set(QUARTER)
        # floor の入出力は版により長さ(doubleLinear)の型なので、係数1の unitConversion で数値のまま渡す
        # (UI単位がmmでも自動の単位変換が入らない)。
        floor = graph._node("floor", "step")
        toFloor = graph._node("unitConversion", "floorInput")
        toFloor.getPlug("conversionFactor").set(1.0)
        quarters.getPlug("outputX").connectTo(toFloor.getPlug("input"))
        toFloor.getPlug("output").connectTo(floor.getPlug("input"))
        stepCount = graph._node("unitConversion", "stepCount")
        stepCount.getPlug("conversionFactor").set(1.0)
        floor.getPlug("output").connectTo(stepCount.getPlug("input"))
        stepCount.getPlug("output").connectTo(owner.getPlug("step"))
        # n·90°(数値) と φ = roll - n·90°
        stepNumber = graph._node("unitConversion", "stepNumber")
        stepNumber.getPlug("conversionFactor").set(QUARTER)
        stepCount.getPlug("output").connectTo(stepNumber.getPlug("input"))
        partial = graph._node("plusMinusAverage", "partial")
        partial.getPlug("operation").set(2)
        number.getPlug("output").connectTo(partial.getPlug("input1D")[0])
        stepNumber.getPlug("output").connectTo(partial.getPlug("input1D")[1])
        # 回転の行列(角度の入力へは係数を明示した unitConversion で渡す)
        rotations = []
        for label, source, factor in (("stepRotate", stepCount.getPlug("output"), QUARTER),
                                      ("partialRotate", partial.getPlug("output1D"), 1.0)):
            angle = graph._node("unitConversion", label + "Angle")
            angle.getPlug("conversionFactor").set(factor)
            source.connectTo(angle.getPlug("input"))
            compose = graph._node("composeMatrix", label)
            angle.getPlug("output").connectTo(compose.getPlug("inputRotate" + axis.upper()))
            rotations.append(compose.getPlug("outputMatrix"))
        # travel = n·size と前への送り T(n·size·f)。f は ±1 の1軸なので符号付きの係数で1つの成分へ渡す。
        forward = _cross(AXES[axis], AXES[upAxis])
        slot = max(range(3), key=lambda i: abs(forward[i]))
        travel = graph._node("unitConversion", "travelLength")
        travel.getPlug("conversionFactor").set(size)
        stepCount.getPlug("output").connectTo(travel.getPlug("input"))
        travel.getPlug("output").connectTo(owner.getPlug("travel"))
        send = graph._node("unitConversion", "travelForward")
        send.getPlug("conversionFactor").set(forward[slot])
        owner.getPlug("travel").connectTo(send.getPlug("input"))
        sendMatrix = graph._node("composeMatrix", "send")
        send.getPlug("output").connectTo(sendMatrix.getPlug("inputTranslate" + "XYZ"[slot]))

        half = size / 2.0
        up = AXES[upAxis]
        center = [contact[i] + half * up[i] for i in range(3)]
        edge = [contact[i] + half * forward[i] for i in range(3)]
        rest = Matrix(target.getPlug("matrix").get()) * Matrix(target.getPlug("offsetParentMatrix").get())
        chain = graph._node("multMatrix", "matrix")
        chain.getPlug("matrixIn")[0].set(_translation([-value for value in center]))
        rotations[0].connectTo(chain.getPlug("matrixIn")[1])
        chain.getPlug("matrixIn")[2].set(_translation([center[i] - edge[i] for i in range(3)]))
        rotations[1].connectTo(chain.getPlug("matrixIn")[3])
        sendMatrix.getPlug("outputMatrix").connectTo(chain.getPlug("matrixIn")[4])
        chain.getPlug("matrixIn")[5].set(_translation(edge) * rest)
        # jointの parentMatrix は offsetParentMatrix を含むので、親の worldMatrix を直接使う(ワールド直下なら無し)。
        parent = target.getParent()
        if parent is not None:
            parent.getPlug("worldMatrix")[0].connectTo(chain.getPlug("matrixIn")[6])
        chain.getPlug("matrixSum").connectTo(owner.getPlug("matrix"))
        owner.setAttrFlags(["step", "travel", "matrix"], keyable=False)
        return graph
