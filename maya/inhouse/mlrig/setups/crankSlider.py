"""回るクランクのピンにコネクティングロッドで繋いだピストンを、シリンダーの軸に沿って滑らせる標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.twistDistribution import TwistDistribution

AXES = {
    "x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0),
    "-x": (-1.0, 0.0, 0.0), "-y": (0.0, -1.0, 0.0), "-z": (0.0, 0.0, -1.0),
}


def _position(matrix):
    """行列の平行移動をVectorで返す。"""
    return Vector(matrix[12], matrix[13], matrix[14])


def _translation(vector):
    """平行移動だけの行列。"""
    return Matrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, vector[0], vector[1], vector[2], 1])


class CrankSlider(TwistDistribution):
    """エンジンのクランク・コネクティングロッド・ピストン(往復スライダー・クランク機構)の標準DG。

    クランクのピンの位置 P(回るクランクの子のtransform)から、長さ L のロッドで繋がったピストンのピンが、
    シリンダーの軸 d(ピストンの親の空間の固定の向き)の上のどこに来るかを、円と直線の交点として求める。
    ピストンの生成時の位置を X0 とすると、v = P - X0、a = dot(v, d) として、
    移動量 t = a + sqrt(max(L^2 - (dot(v, v) - a^2), 0))。生成時は a < 0 で sqrt = |a| なので t = 0(跳ねない)。
    ロッドはピンの位置に付いたまま ``aimMatrix`` でピストンのピンへ向ける。フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def pistonOffset(cls, pin, rest, axis, length):
        """ピストンの軸に沿った移動量を計算する(DGと同じ式のPython版)。

        Args:
            pin (Sequence[float]): クランクのピンの位置(ピストンの親の空間)。
            rest (Sequence[float]): ピストンのピンの生成時の位置(同じ空間)。
            axis (Sequence[float]): シリンダーの軸の単位ベクトル(同じ空間、ピストンがピンから離れる向き)。
            length (float): ロッドの長さ。

        Returns:
            float: 生成時の位置からの軸に沿った移動量。ロッドが届かない場合は軸の上の最も近い点まで。
        """
        v = [pin[i] - rest[i] for i in range(3)]
        a = sum(v[i] * axis[i] for i in range(3))
        perpendicular = sum(value * value for value in v) - a * a
        return a + math.sqrt(max(length * length - perpendicular, 0.0))

    @classmethod
    @undoTransaction("mlrig.CrankSlider.create")
    def create(cls, pin, piston, name="crankSlider", axis="y", rod=None, normal=None):
        """クランクのピン(pin)とピストン(piston)から、ピストンとロッドのワールド行列を生成する。

        Args:
            pin (str | Node): クランクのピンの位置を示すtransform(回るクランクの子に置く)。
            piston (str | Node): ピストンのtransform。生成時の位置をピストンのピン、親の空間をシリンダーの空間にする。
            name (str): 一意なcontainer名。
            axis (str | Sequence[float]): シリンダーの軸(ピストンの親の空間)。x/y/z/-x/-y/-z または3次元の向き。
                ピストンがクランクから離れる向きにする。
            rod (str | Node | None): ロッドのtransform。生成時の姿勢を出力の基準にする。None ならピンの位置で
                Xをピストンへ、Zを機構の面の法線へ向けた枠を基準にする。
            normal (Sequence[float] | None): 機構の面の法線(ピストンの親の空間)。None なら ``axis × (ピン - ピストン)``。
                ピンがシリンダーの軸の上にある(上死点・下死点で作る)場合は指定する。

        Returns:
            CrankSlider: pistonMatrix・rodMatrix・stroke の所有者。containerに rodLength(長さ、keyable)を持つ。

        Raises:
            ValueError: pin・piston・rod がtransformでない場合、軸・法線が不正な場合、ピストンがピンより軸の先に
                無い場合、またはnameが既に存在する場合。

        Note:
            pistonMatrix = R_p * T(d * t) * S(R_p は生成時のピストンのローカル行列、S は親の worldMatrix)。
            rodMatrix = aimMatrix(R0 * T(P - P0) * S を、primaryをピストンのピンへ、secondaryを法線へ揃える)。
            どちらもワールド行列なので、ワールド直下のtransformの offsetParentMatrix へ接続する。
            ロッドが軸に届かない(L が軸からピンまでの距離より短い)場合、ピストンは軸の上の最も近い点に止まる。
        """
        if mlib.objExists(name):
            raise ValueError("CrankSlider container already exists: " + name)
        nodes = []
        for label, value in (("pin", pin), ("piston", piston), ("rod", rod)):
            if value is None:
                nodes.append(None)
                continue
            node = mlib.nodes.Node(value)
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected a transform for the " + label)
            nodes.append(node)
        pin, piston, rod = nodes
        direction = AXES.get(axis) if isinstance(axis, str) else tuple(float(value) for value in axis)
        if direction is None or len(direction) != 3 or not all(math.isfinite(value) for value in direction):
            raise ValueError("axis must be x, y, z, -x, -y, -z or a finite 3D vector")
        direction = Vector(*direction)
        if direction.length() < 1e-9:
            raise ValueError("axis must not be a zero vector")
        direction = direction.normal()

        parent = piston.getParent()
        space = Matrix(parent.getPlug("worldMatrix")[0].get()) if parent is not None else Matrix()
        inverse = space.inverse()
        rest_piston = Matrix(piston.getPlug("matrix").get()) * Matrix(piston.getPlug("offsetParentMatrix").get())
        pin_rest = _position(Matrix(pin.getPlug("worldMatrix")[0].get()) * inverse)
        piston_rest = _position(rest_piston)
        reach = piston_rest - pin_rest
        length = reach.length()
        if length < 1e-6:
            raise ValueError("The pin and the piston must not be at the same position")
        if reach * direction < 1e-6:
            raise ValueError("The piston must be ahead of the pin along the axis")
        if normal is None:
            plane = direction ^ (pin_rest - piston_rest)
            if plane.length() < 1e-6 * length:
                raise ValueError("The pin is on the cylinder axis; pass normal")
        else:
            plane = Vector(*[float(value) for value in normal])
            plane = plane - direction * (plane * direction)
            if plane.length() < 1e-9:
                raise ValueError("normal must not be parallel to the axis")
        plane = plane.normal()
        aim = reach.normal()
        if rod is not None:
            rod_rest = Matrix(rod.getPlug("worldMatrix")[0].get()) * inverse
        else:
            up = plane ^ aim
            rod_rest = Matrix([aim[0], aim[1], aim[2], 0, up[0], up[1], up[2], 0,
                               plane[0], plane[1], plane[2], 0, pin_rest[0], pin_rest[1], pin_rest[2], 1])
        rod_inverse = rod_rest.inverse()
        aim_local = (aim * rod_inverse).normal()
        plane_local = (plane * rod_inverse).normal()

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="rodLength", attributeType="doubleLinear", defaultValue=length, minValue=0.0,
                      keyable=True)
        owner.addAttr(longName="stroke", attributeType="doubleLinear")
        owner.addAttr(longName="pistonMatrix", dataType="matrix")
        owner.addAttr(longName="rodMatrix", dataType="matrix")

        # P: ピンの位置をピストンの親の空間へ。vectorProduct・plusMinusAverage は単位なしなので cm のまま計算する。
        local = graph._node("multMatrix", "pinLocal")
        pin.getPlug("worldMatrix")[0].connectTo(local.getPlug("matrixIn")[0])
        if parent is not None:
            parent.getPlug("worldInverseMatrix")[0].connectTo(local.getPlug("matrixIn")[1])
        point = graph._node("vectorProduct", "pinPoint")
        point.getPlug("operation").set(4)
        point.getPlug("input1").set((0.0, 0.0, 0.0))
        local.getPlug("matrixSum").connectTo(point.getPlug("matrix"))
        offset = graph._node("plusMinusAverage", "pinOffset")
        offset.getPlug("operation").set(2)
        point.getPlug("output").connectTo(offset.getPlug("input3D")[0])
        offset.getPlug("input3D")[1].set(tuple(piston_rest))

        # a = dot(v, d)、vv = dot(v, v)。
        along = graph._node("vectorProduct", "along")
        along.getPlug("operation").set(1)
        offset.getPlug("output3D").connectTo(along.getPlug("input1"))
        along.getPlug("input2").set(tuple(direction))
        square = graph._node("vectorProduct", "squared")
        square.getPlug("operation").set(1)
        offset.getPlug("output3D").connectTo(square.getPlug("input1"))
        offset.getPlug("output3D").connectTo(square.getPlug("input2"))

        # q = L^2 - vv + a^2 を0以上にして平方根、t = a + sqrt(q)。長さは係数1の unitConversion で数値にする。
        plain = graph._node("unitConversion", "rodLengthNumber")
        plain.getPlug("conversionFactor").set(1.0)
        owner.getPlug("rodLength").connectTo(plain.getPlug("input"))
        squares = graph._node("multiplyDivide", "squares")
        plain.getPlug("output").connectTo(squares.getPlug("input1X"))
        plain.getPlug("output").connectTo(squares.getPlug("input2X"))
        along.getPlug("outputX").connectTo(squares.getPlug("input1Y"))
        along.getPlug("outputX").connectTo(squares.getPlug("input2Y"))
        reachSquared = graph._node("plusMinusAverage", "reachSquared")
        squares.getPlug("outputX").connectTo(reachSquared.getPlug("input1D")[0])
        squares.getPlug("outputY").connectTo(reachSquared.getPlug("input1D")[1])
        negate = graph._node("multiplyDivide", "negateSquared")
        square.getPlug("outputX").connectTo(negate.getPlug("input1X"))
        negate.getPlug("input2X").set(-1.0)
        negate.getPlug("outputX").connectTo(reachSquared.getPlug("input1D")[2])
        floor = graph._node("clamp", "reachFloor")
        floor.getPlug("maxR").set(1e30)
        reachSquared.getPlug("output1D").connectTo(floor.getPlug("inputR"))
        root = graph._node("multiplyDivide", "reachRoot")
        root.getPlug("operation").set(3)
        floor.getPlug("outputR").connectTo(root.getPlug("input1X"))
        root.getPlug("input2X").set(0.5)
        travel = graph._node("plusMinusAverage", "travel")
        along.getPlug("outputX").connectTo(travel.getPlug("input1D")[0])
        root.getPlug("outputX").connectTo(travel.getPlug("input1D")[1])
        stroke = graph._node("unitConversion", "strokeLength")
        stroke.getPlug("conversionFactor").set(1.0)
        travel.getPlug("output1D").connectTo(stroke.getPlug("input"))
        stroke.getPlug("output").connectTo(owner.getPlug("stroke"))

        # pistonMatrix = R_p * T(d * t) * S。d の成分を係数にした unitConversion で t を各軸の移動へ渡す。
        slide = graph._node("composeMatrix", "slide")
        for index, letter in enumerate("XYZ"):
            if abs(direction[index]) < 1e-12:
                continue
            component = graph._node("unitConversion", "slide" + letter)
            component.getPlug("conversionFactor").set(direction[index])
            travel.getPlug("output1D").connectTo(component.getPlug("input"))
            component.getPlug("output").connectTo(slide.getPlug("inputTranslate" + letter))
        chain = graph._node("multMatrix", "pistonMatrix")
        chain.getPlug("matrixIn")[0].set(rest_piston)
        slide.getPlug("outputMatrix").connectTo(chain.getPlug("matrixIn")[1])
        if parent is not None:
            parent.getPlug("worldMatrix")[0].connectTo(chain.getPlug("matrixIn")[2])
        chain.getPlug("matrixSum").connectTo(owner.getPlug("pistonMatrix"))

        # ロッド: 生成時の姿勢をピンの位置へ運び(pickMatrixで平行移動だけ)、aimMatrixでピストンのピンへ向ける。
        carry = graph._node("pickMatrix", "pinTranslate")
        for flag in ("useScale", "useShear", "useRotate"):
            carry.getPlug(flag).set(False)
        local.getPlug("matrixSum").connectTo(carry.getPlug("inputMatrix"))
        rest_chain = graph._node("multMatrix", "rodInput")
        rest_chain.getPlug("matrixIn")[0].set(rod_rest * _translation(-pin_rest))
        carry.getPlug("outputMatrix").connectTo(rest_chain.getPlug("matrixIn")[1])
        if parent is not None:
            parent.getPlug("worldMatrix")[0].connectTo(rest_chain.getPlug("matrixIn")[2])
        aimer = graph._node("aimMatrix", "rodAim")
        rest_chain.getPlug("matrixSum").connectTo(aimer.getPlug("inputMatrix"))
        aimer.getPlug("primaryMode").set(1)
        aimer.getPlug("primaryInputAxis").set(tuple(aim_local))
        aimer.getPlug("primaryTargetVector").set((0.0, 0.0, 0.0))
        chain.getPlug("matrixSum").connectTo(aimer.getPlug("primaryTargetMatrix"))
        aimer.getPlug("secondaryMode").set(2)
        aimer.getPlug("secondaryInputAxis").set(tuple(plane_local))
        aimer.getPlug("secondaryTargetVector").set(tuple(plane))
        if parent is not None:
            parent.getPlug("worldMatrix")[0].connectTo(aimer.getPlug("secondaryTargetMatrix"))
        aimer.getPlug("outputMatrix").connectTo(owner.getPlug("rodMatrix"))
        owner.setAttrFlags(["stroke", "pistonMatrix", "rodMatrix"], keyable=False)
        return graph
