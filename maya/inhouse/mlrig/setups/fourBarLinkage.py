"""クランク・連結棒(カプラー)・ロッカーの4本の棒からなる四節リンク機構の標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.twistDistribution import TwistDistribution


def _position(matrix):
    """行列の平行移動をVectorで返す。"""
    return Vector(matrix[12], matrix[13], matrix[14])


def _translation(vector):
    """平行移動だけの行列。"""
    return Matrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, vector[0], vector[1], vector[2], 1])


class FourBarLinkage(TwistDistribution):
    """固定の2支点を持つ四節リンク機構(クランク・カプラー・ロッカー)の標準DG。

    クランクのピン B(回るクランクの子のtransform)と、ロッカーの支点 D(ロッカーのtransformの位置)から、
    カプラーとロッカーを繋ぐ関節 C を「B を中心に半径 b の円」と「D を中心に半径 c の円」の交点として求める。
    ロッカーの親の空間で P = B、w = D - P、d = |w|、u = w / d、x = (d^2 + b^2 - c^2) / (2d) を [-b, b] に制限し、
    h = sqrt(max(b^2 - x^2, 0))、C = P + x u + s h normalize(n × u)。s(+1/-1)は生成時の配置から決める枝で、
    途中で反対の枝へ跳ばない。ロッカーは支点に付いたまま C へ、カプラーは B に付いたまま C へ ``aimMatrix`` で向ける。
    フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def jointPosition(cls, pin, pivot, coupler, rocker, normal, branch=1.0):
        """カプラーとロッカーの関節の位置を計算する(DGと同じ式のPython版)。

        Args:
            pin (Sequence[float]): クランクのピン B の位置(ロッカーの親の空間)。
            pivot (Sequence[float]): ロッカーの支点 D の位置(同じ空間)。
            coupler (float): カプラーの長さ b(B から C)。
            rocker (float): ロッカーの長さ c(D から C)。
            normal (Sequence[float]): 機構の面の単位法線 n(同じ空間)。
            branch (float): 枝の向き s。+1 または -1。

        Returns:
            tuple[tuple[float, float, float], float]: 関節 C の位置と、届かない量 excess
            (max(d - (b + c), |b - c| - d, 0))。
        """
        w = [pivot[i] - pin[i] for i in range(3)]
        distance = max(math.sqrt(sum(value * value for value in w)), 1e-6)
        u = [value / distance for value in w]
        x = (distance * distance + coupler * coupler - rocker * rocker) / (2.0 * distance)
        x = min(max(x, -coupler), coupler)
        h = math.sqrt(max(coupler * coupler - x * x, 0.0)) * branch
        side = [normal[1] * u[2] - normal[2] * u[1], normal[2] * u[0] - normal[0] * u[2],
                normal[0] * u[1] - normal[1] * u[0]]
        size = math.sqrt(sum(value * value for value in side)) or 1.0
        point = tuple(pin[i] + x * u[i] + h * side[i] / size for i in range(3))
        excess = max(distance - (coupler + rocker), abs(coupler - rocker) - distance, 0.0)
        return point, excess

    @classmethod
    @undoTransaction("mlrig.FourBarLinkage.create")
    def create(cls, pin, rocker, end, name="fourBarLinkage", coupler=None, normal=None):
        """クランクのピン(pin)・ロッカー(rocker)・関節(end)から、カプラーとロッカーのワールド行列を生成する。

        Args:
            pin (str | Node): クランクのピン B を示すtransform(回るクランクの子に置く)。
            rocker (str | Node): ロッカーのtransform。生成時の位置を支点 D、親の空間を機構の空間にする。
            end (str | Node): カプラーとロッカーを繋ぐ関節 C の生成時の位置を示すtransform。位置だけを読み、接続しない。
            name (str): 一意なcontainer名。
            coupler (str | Node | None): カプラーのtransform。生成時の姿勢を出力の基準にする。None なら B の位置で
                Xを C へ、Zを機構の面の法線へ向けた枠を基準にする。
            normal (Sequence[float] | None): 機構の面の法線(ロッカーの親の空間)。None なら ``(D - B) × (C - B)``。
                B・C・D が一直線に並ぶ配置で作る場合は指定する。

        Returns:
            FourBarLinkage: rockerMatrix・couplerMatrix・jointMatrix・excess・transmissionAngle の所有者。
            containerに couplerLength・rockerLength(長さ、keyable)を持つ。

        Raises:
            ValueError: pin・rocker・end・coupler がtransformでない場合、棒の長さが0の場合、法線が不正な場合、
                またはnameが既に存在する場合。

        Note:
            rockerMatrix = aimMatrix(R_r * S を、生成時の D→C の向きを C へ、法線を n へ揃える)。
            couplerMatrix = aimMatrix(R_c * T(B - B0) * S を、生成時の B→C の向きを C へ、法線を n へ揃える)。
            jointMatrix = T(C) * S。R_r・R_c は生成時のローカル行列、S はロッカーの親の worldMatrix。
            どれもワールド行列なので、ワールド直下のtransformの offsetParentMatrix へ接続する。
            C が作れない(d > b + c または d < |b - c|)場合、C は B から D への線の上の最も近い点に止まり、
            excess にその距離の不足・超過を出す。
        """
        if mlib.objExists(name):
            raise ValueError("FourBarLinkage container already exists: " + name)
        nodes = []
        for label, value in (("pin", pin), ("rocker", rocker), ("end", end), ("coupler", coupler)):
            if value is None:
                nodes.append(None)
                continue
            node = mlib.nodes.Node(value)
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected a transform for the " + label)
            nodes.append(node)
        pin, rocker, end, coupler = nodes

        parent = rocker.getParent()
        space = Matrix(parent.getPlug("worldMatrix")[0].get()) if parent is not None else Matrix()
        inverse = space.inverse()
        rocker_rest = Matrix(rocker.getPlug("matrix").get()) * Matrix(rocker.getPlug("offsetParentMatrix").get())
        pin_rest = _position(Matrix(pin.getPlug("worldMatrix")[0].get()) * inverse)
        joint_rest = _position(Matrix(end.getPlug("worldMatrix")[0].get()) * inverse)
        pivot = _position(rocker_rest)
        coupler_vector = joint_rest - pin_rest
        rocker_vector = joint_rest - pivot
        coupler_length = coupler_vector.length()
        rocker_length = rocker_vector.length()
        if coupler_length < 1e-6 or rocker_length < 1e-6 or (pivot - pin_rest).length() < 1e-6:
            raise ValueError("The pin, the rocker pivot and the end must be at different positions")
        if normal is None:
            plane = (pivot - pin_rest) ^ coupler_vector
            if plane.length() < 1e-6 * coupler_length * (pivot - pin_rest).length():
                raise ValueError("The pin, the rocker pivot and the end are in a line; pass normal")
        else:
            values = [float(value) for value in normal]
            if len(values) != 3 or not all(math.isfinite(value) for value in values):
                raise ValueError("normal must be a finite 3D vector")
            plane = Vector(*values)
            if plane.length() < 1e-9:
                raise ValueError("normal must not be a zero vector")
        plane = plane.normal()
        u = (pivot - pin_rest).normal()
        branch = 1.0 if coupler_vector * (plane ^ u) >= 0.0 else -1.0

        coupler_aim = coupler_vector.normal()
        if coupler is not None:
            coupler_rest = Matrix(coupler.getPlug("worldMatrix")[0].get()) * inverse
        else:
            up = plane ^ coupler_aim
            coupler_rest = Matrix([coupler_aim[0], coupler_aim[1], coupler_aim[2], 0, up[0], up[1], up[2], 0,
                                   plane[0], plane[1], plane[2], 0, pin_rest[0], pin_rest[1], pin_rest[2], 1])
        coupler_inverse = coupler_rest.inverse()
        rocker_inverse = rocker_rest.inverse()

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="couplerLength", attributeType="doubleLinear", defaultValue=coupler_length,
                      minValue=0.0, keyable=True)
        owner.addAttr(longName="rockerLength", attributeType="doubleLinear", defaultValue=rocker_length,
                      minValue=0.0, keyable=True)
        owner.addAttr(longName="excess", attributeType="doubleLinear")
        owner.addAttr(longName="transmissionAngle", attributeType="doubleAngle")
        owner.addAttr(longName="rockerMatrix", dataType="matrix")
        owner.addAttr(longName="couplerMatrix", dataType="matrix")
        owner.addAttr(longName="jointMatrix", dataType="matrix")

        # P: ピンの位置をロッカーの親の空間へ。vectorProduct・plusMinusAverage は単位なしなので cm のまま計算する。
        local = graph._node("multMatrix", "pinLocal")
        pin.getPlug("worldMatrix")[0].connectTo(local.getPlug("matrixIn")[0])
        if parent is not None:
            parent.getPlug("worldInverseMatrix")[0].connectTo(local.getPlug("matrixIn")[1])
        point = graph._node("vectorProduct", "pinPoint")
        point.getPlug("operation").set(4)
        point.getPlug("input1").set((0.0, 0.0, 0.0))
        local.getPlug("matrixSum").connectTo(point.getPlug("matrix"))
        toward = graph._node("plusMinusAverage", "towardPivot")
        toward.getPlug("operation").set(2)
        toward.getPlug("input3D")[0].set(tuple(pivot))
        point.getPlug("output").connectTo(toward.getPlug("input3D")[1])

        # d = sqrt(w・w)(0除算を避けて1e-6以上)、u = w / d。
        square = graph._node("vectorProduct", "distanceSquared")
        square.getPlug("operation").set(1)
        toward.getPlug("output3D").connectTo(square.getPlug("input1"))
        toward.getPlug("output3D").connectTo(square.getPlug("input2"))
        root = graph._node("multiplyDivide", "distanceRoot")
        root.getPlug("operation").set(3)
        square.getPlug("outputX").connectTo(root.getPlug("input1X"))
        root.getPlug("input2X").set(0.5)
        safe = graph._node("clamp", "distance")
        safe.getPlug("minR").set(1e-6)
        safe.getPlug("maxR").set(1e30)
        root.getPlug("outputX").connectTo(safe.getPlug("inputR"))
        distance = safe.getPlug("outputR")
        unit = graph._node("multiplyDivide", "direction")
        unit.getPlug("operation").set(2)
        toward.getPlug("output3D").connectTo(unit.getPlug("input1"))
        for letter in "XYZ":
            distance.connectTo(unit.getPlug("input2" + letter))

        # 棒の長さ b・c は係数1の unitConversion で数値にし、b^2・c^2・(b - c)^2 を作る。
        lengths = []
        for attribute in ("couplerLength", "rockerLength"):
            plain = graph._node("unitConversion", attribute + "Number")
            plain.getPlug("conversionFactor").set(1.0)
            owner.getPlug(attribute).connectTo(plain.getPlug("input"))
            lengths.append(plain.getPlug("output"))
        b, c = lengths
        difference = graph._node("plusMinusAverage", "lengthDifference")
        difference.getPlug("operation").set(2)
        b.connectTo(difference.getPlug("input1D")[0])
        c.connectTo(difference.getPlug("input1D")[1])
        squares = graph._node("multiplyDivide", "lengthSquares")
        for letter, value in (("X", b), ("Y", c), ("Z", difference.getPlug("output1D"))):
            value.connectTo(squares.getPlug("input1" + letter))
            value.connectTo(squares.getPlug("input2" + letter))

        # x = (d^2 + b^2 - c^2) / (2d) を [-b, b] に制限する。
        numerator = graph._node("plusMinusAverage", "alongNumerator")
        numerator.getPlug("operation").set(2)
        square.getPlug("outputX").connectTo(numerator.getPlug("input1D")[0])
        squares.getPlug("outputY").connectTo(numerator.getPlug("input1D")[1])
        negative = graph._node("multiplyDivide", "negatives")
        squares.getPlug("outputX").connectTo(negative.getPlug("input1X"))
        negative.getPlug("input2X").set(-1.0)
        b.connectTo(negative.getPlug("input1Y"))
        negative.getPlug("input2Y").set(-1.0)
        negative.getPlug("outputX").connectTo(numerator.getPlug("input1D")[2])
        along = graph._node("multiplyDivide", "along")
        along.getPlug("operation").set(2)
        numerator.getPlug("output1D").connectTo(along.getPlug("input1X"))
        twice = graph._node("multiplyDivide", "twiceDistance")
        distance.connectTo(twice.getPlug("input1X"))
        twice.getPlug("input2X").set(2.0)
        twice.getPlug("outputX").connectTo(along.getPlug("input2X"))
        limit = graph._node("clamp", "alongLimit")
        along.getPlug("outputX").connectTo(limit.getPlug("inputR"))
        negative.getPlug("outputY").connectTo(limit.getPlug("minR"))
        b.connectTo(limit.getPlug("maxR"))
        x = limit.getPlug("outputR")

        # h = s * sqrt(max(b^2 - x^2, 0))。
        alongSquared = graph._node("multiplyDivide", "alongSquared")
        x.connectTo(alongSquared.getPlug("input1X"))
        x.connectTo(alongSquared.getPlug("input2X"))
        heightSquared = graph._node("plusMinusAverage", "heightSquared")
        heightSquared.getPlug("operation").set(2)
        squares.getPlug("outputX").connectTo(heightSquared.getPlug("input1D")[0])
        alongSquared.getPlug("outputX").connectTo(heightSquared.getPlug("input1D")[1])
        floor = graph._node("clamp", "heightFloor")
        floor.getPlug("maxR").set(1e30)
        heightSquared.getPlug("output1D").connectTo(floor.getPlug("inputR"))
        height = graph._node("multiplyDivide", "height")
        height.getPlug("operation").set(3)
        floor.getPlug("outputR").connectTo(height.getPlug("input1X"))
        height.getPlug("input2X").set(0.5)
        signed = graph._node("multiplyDivide", "branchHeight")
        height.getPlug("outputX").connectTo(signed.getPlug("input1X"))
        signed.getPlug("input2X").set(branch)

        # C = P + x u + h normalize(n × u)。
        side = graph._node("vectorProduct", "side")
        side.getPlug("operation").set(2)
        side.getPlug("normalizeOutput").set(True)
        side.getPlug("input1").set(tuple(plane))
        unit.getPlug("output").connectTo(side.getPlug("input2"))
        offsets = []
        for suffix, vector, scale in (("alongOffset", unit.getPlug("output"), x),
                                      ("sideOffset", side.getPlug("output"), signed.getPlug("outputX"))):
            offset = graph._node("multiplyDivide", suffix)
            vector.connectTo(offset.getPlug("input1"))
            for letter in "XYZ":
                scale.connectTo(offset.getPlug("input2" + letter))
            offsets.append(offset.getPlug("output"))
        joint = graph._node("plusMinusAverage", "joint")
        point.getPlug("output").connectTo(joint.getPlug("input3D")[0])
        offsets[0].connectTo(joint.getPlug("input3D")[1])
        offsets[1].connectTo(joint.getPlug("input3D")[2])

        # jointMatrix = T(C) * S。fourByFourMatrix は単位なしの数値なので単位変換が入らない。
        carryJoint = graph._node("fourByFourMatrix", "jointTranslate")
        for index, letter in enumerate("xyz"):
            joint.getPlug("output3D" + letter).connectTo(carryJoint.getPlug("in3{}".format(index)))
        jointChain = graph._node("multMatrix", "jointMatrix")
        carryJoint.getPlug("output").connectTo(jointChain.getPlug("matrixIn")[0])
        if parent is not None:
            parent.getPlug("worldMatrix")[0].connectTo(jointChain.getPlug("matrixIn")[1])
        jointChain.getPlug("matrixSum").connectTo(owner.getPlug("jointMatrix"))

        # excess = max(d - (b + c), |b - c| - d, 0)。
        overReach = graph._node("plusMinusAverage", "overReach")
        overReach.getPlug("operation").set(2)
        distance.connectTo(overReach.getPlug("input1D")[0])
        b.connectTo(overReach.getPlug("input1D")[1])
        c.connectTo(overReach.getPlug("input1D")[2])
        gap = graph._node("multiplyDivide", "lengthGap")
        gap.getPlug("operation").set(3)
        squares.getPlug("outputZ").connectTo(gap.getPlug("input1X"))
        gap.getPlug("input2X").set(0.5)
        underReach = graph._node("plusMinusAverage", "underReach")
        underReach.getPlug("operation").set(2)
        gap.getPlug("outputX").connectTo(underReach.getPlug("input1D")[0])
        distance.connectTo(underReach.getPlug("input1D")[1])
        larger = graph._node("condition", "largerExcess")
        larger.getPlug("operation").set(2)
        overReach.getPlug("output1D").connectTo(larger.getPlug("firstTerm"))
        underReach.getPlug("output1D").connectTo(larger.getPlug("secondTerm"))
        overReach.getPlug("output1D").connectTo(larger.getPlug("colorIfTrueR"))
        underReach.getPlug("output1D").connectTo(larger.getPlug("colorIfFalseR"))
        positive = graph._node("clamp", "excessFloor")
        positive.getPlug("maxR").set(1e30)
        larger.getPlug("outColorR").connectTo(positive.getPlug("inputR"))
        excess = graph._node("unitConversion", "excessLength")
        excess.getPlug("conversionFactor").set(1.0)
        positive.getPlug("outputR").connectTo(excess.getPlug("input"))
        excess.getPlug("output").connectTo(owner.getPlug("excess"))

        # 伝達角 μ = angle(B - C, D - C)。
        toPin = graph._node("plusMinusAverage", "jointToPin")
        toPin.getPlug("operation").set(2)
        point.getPlug("output").connectTo(toPin.getPlug("input3D")[0])
        joint.getPlug("output3D").connectTo(toPin.getPlug("input3D")[1])
        toPivot = graph._node("plusMinusAverage", "jointToPivot")
        toPivot.getPlug("operation").set(2)
        toPivot.getPlug("input3D")[0].set(tuple(pivot))
        joint.getPlug("output3D").connectTo(toPivot.getPlug("input3D")[1])
        angle = graph._node("angleBetween", "transmission")
        toPin.getPlug("output3D").connectTo(angle.getPlug("vector1"))
        toPivot.getPlug("output3D").connectTo(angle.getPlug("vector2"))
        angle.getPlug("angle").connectTo(owner.getPlug("transmissionAngle"))

        # ロッカー: 生成時の姿勢のまま、D→C の向きを C へ、法線を n へ揃える。
        rockerChain = graph._node("multMatrix", "rockerInput")
        rockerChain.getPlug("matrixIn")[0].set(rocker_rest)
        if parent is not None:
            parent.getPlug("worldMatrix")[0].connectTo(rockerChain.getPlug("matrixIn")[1])
        # カプラー: 生成時の姿勢をピンの位置へ運び(pickMatrixで平行移動だけ)、B→C の向きを C へ揃える。
        carry = graph._node("pickMatrix", "pinTranslate")
        for flag in ("useScale", "useShear", "useRotate"):
            carry.getPlug(flag).set(False)
        local.getPlug("matrixSum").connectTo(carry.getPlug("inputMatrix"))
        couplerChain = graph._node("multMatrix", "couplerInput")
        couplerChain.getPlug("matrixIn")[0].set(coupler_rest * _translation(-pin_rest))
        carry.getPlug("outputMatrix").connectTo(couplerChain.getPlug("matrixIn")[1])
        if parent is not None:
            parent.getPlug("worldMatrix")[0].connectTo(couplerChain.getPlug("matrixIn")[2])
        for suffix, chain, aim, rest_inverse, output in (
                ("rockerAim", rockerChain, rocker_vector.normal(), rocker_inverse, "rockerMatrix"),
                ("couplerAim", couplerChain, coupler_aim, coupler_inverse, "couplerMatrix")):
            aimer = graph._node("aimMatrix", suffix)
            chain.getPlug("matrixSum").connectTo(aimer.getPlug("inputMatrix"))
            aimer.getPlug("primaryMode").set(1)
            aimer.getPlug("primaryInputAxis").set(tuple((aim * rest_inverse).normal()))
            aimer.getPlug("primaryTargetVector").set((0.0, 0.0, 0.0))
            jointChain.getPlug("matrixSum").connectTo(aimer.getPlug("primaryTargetMatrix"))
            aimer.getPlug("secondaryMode").set(2)
            aimer.getPlug("secondaryInputAxis").set(tuple((plane * rest_inverse).normal()))
            aimer.getPlug("secondaryTargetVector").set(tuple(plane))
            if parent is not None:
                parent.getPlug("worldMatrix")[0].connectTo(aimer.getPlug("secondaryTargetMatrix"))
            aimer.getPlug("outputMatrix").connectTo(owner.getPlug(output))
        owner.setAttrFlags(["excess", "transmissionAngle", "rockerMatrix", "couplerMatrix", "jointMatrix"],
                           keyable=False)
        return graph
