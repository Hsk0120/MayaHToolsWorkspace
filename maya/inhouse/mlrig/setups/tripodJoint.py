"""シャフトの長さを保ったまま軸方向へ滑る(プランジする)トリポード形の継手の標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.twistDistribution import TwistDistribution

_AXES = ("x", "y", "z")


class TripodJoint(TwistDistribution):
    """ハウジングの軸に沿ってスパイダーを滑らせ、外側の継手までのシャフトの長さを一定に保つ標準DG。

    ドライブシャフトの内側(デフ側)に使われるトリポード形の継手は、ハウジングの3本の溝に沿って
    スパイダー(3本のトラニオンとローラー)が軸方向へ滑る。サスペンションで両端の距離が変わっても、
    シャフトの長さは変わらず継手が伸び縮み(プランジ)する。スパイダーの中心はハウジングの軸上の、
    外側の継手の位置からシャフトの長さだけ離れた点(直線と球の交点)で、滑れる範囲で止める。
    向きはConstantVelocityJointと同じく、入力の回転に最短の回転を掛けた等速の近似。
    """

    @classmethod
    def plungeOf(cls, axialDistance, radialDistance, length):
        """スパイダーの中心がハウジングの軸上で進む量(制限前)を計算する。

        Args:
            axialDistance (float): 外側の継手の位置のハウジングの軸方向の成分 a(cm)。
            radialDistance (float): 外側の継手の位置のハウジングの軸からの距離 b(cm)。
            length (float): シャフトの長さ L(cm)。

        Returns:
            float: p = a - √max(L² - b², 0)(cm)。L < b で届かない場合は軸に最も近い点の a。
        """
        return axialDistance - math.sqrt(max(length * length - radialDistance * radialDistance, 0.0))

    @classmethod
    @undoTransaction("mlrig.TripodJoint.create")
    def create(cls, housing, outerJoint, name="tripodJoint", axis="x", length=None, minPlunge=None, maxPlunge=None):
        """housingの軸に沿って滑るスパイダーと、outerJointへ向くシャフトの行列を生成する。

        Args:
            housing (str | Node): ハウジング(入力軸)のtransform。プランジ0の位置に置き、axis を軸にする。
            outerJoint (str | Node): シャフトの反対側(外側の継手)の位置を表すtransform(位置だけを使う)。
            name (str): 一意なcontainer名。
            axis (str): ハウジング・シャフトの軸の向き x/y/z。
            length (float | None): シャフトの長さ(cm)。Noneなら生成時のhousingとouterJointの距離(プランジ0)。
            minPlunge (float | None): 最も押し込んだときのプランジ(cm、負はハウジングの奥)。Noneなら -0.1 × length。
            maxPlunge (float | None): 最も引き出したときのプランジ(cm)。Noneなら 0.1 × length。

        Returns:
            TripodJoint: matrix・tipMatrix・plunge・overPlunge・shaftLength・stretch・bendAngleの所有者。

        Raises:
            ValueError: 軸・長さ・範囲が不正な場合、housing・outerJointがtransformでない場合、同じノードの場合、
                またはnameが既に存在する場合。

        Note:
            H = housingのワールド位置、R = housingのワールド行列の回転(scale・shear・平行移動を除く)、
            u = R で回した axis、W = outerJointのワールド位置、d = W - H、a = d·u、b² = |d|² - a²。
            スパイダーの中心は c = H + u × plunge、plunge = clamp(a - √max(L² - b², 0), minPlunge, maxPlunge)、
            overPlunge = 制限前 - plunge(引き出しすぎは正、押し込みすぎは負)。
            v = normalize(W - c)、matrix = R × Q(u→v) に位置 c、tipMatrix は同じ向きで位置 W。scaleは1。
            shaftLength = |W - c|、stretch = shaftLength - L(範囲内なら0、範囲を超えるとシャフトが伸び縮みした量)。
            bendAngle = u と v のなす角。長さはcm(UIの長さ単位によらない)。
            スパイダーの中心の3倍周期の公転(orbit)、ローラーの傾き、W がハウジングの後ろ側(a < 0)は対象外。
        """
        if axis not in _AXES:
            raise ValueError("axis must be one of x, y and z")
        if mlib.objExists(name):
            raise ValueError("TripodJoint container already exists: " + name)
        housing = mlib.Node(housing)
        outerJoint = mlib.Node(outerJoint)
        for node in (housing, outerJoint):
            if not isinstance(node, mlib.Transform):
                raise ValueError("Expected transforms for the housing and the outer joint")
        if housing.getFullName() == outerJoint.getFullName():
            raise ValueError("housing and outerJoint must be different nodes")
        if length is None:
            start = Vector(Matrix(housing.getPlug("worldMatrix")[0].get()).translate)
            end = Vector(Matrix(outerJoint.getPlug("worldMatrix")[0].get()).translate)
            length = (end - start).length()
        length = float(length)
        if not math.isfinite(length) or length < 1e-6:
            raise ValueError("length must be a finite positive distance")
        minPlunge = -0.1 * length if minPlunge is None else float(minPlunge)
        maxPlunge = 0.1 * length if maxPlunge is None else float(maxPlunge)
        if not (math.isfinite(minPlunge) and math.isfinite(maxPlunge)) or minPlunge > maxPlunge:
            raise ValueError("minPlunge and maxPlunge must be finite and minPlunge <= maxPlunge")
        shaft_axis = [float(item == axis) for item in _AXES]
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="length", attributeType="double", defaultValue=length, minValue=0, keyable=True)
        owner.addAttr(longName="minPlunge", attributeType="double", defaultValue=minPlunge, keyable=True)
        owner.addAttr(longName="maxPlunge", attributeType="double", defaultValue=maxPlunge, keyable=True)
        outputs = ("plunge", "overPlunge", "shaftLength", "stretch")
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        owner.addAttr(longName="bendAngle", attributeType="doubleAngle")
        for attr in ("matrix", "tipMatrix"):
            owner.addAttr(longName=attr, dataType="matrix")

        # ハウジングの位置 H・回転 R・軸 u と、外側の継手の位置 W
        housingMatrix = housing.getPlug("worldMatrix")[0]
        origin = graph._node("decomposeMatrix", "housingPosition")
        housingMatrix.connectTo(origin.getPlug("inputMatrix"))
        outer = graph._node("decomposeMatrix", "outerPosition")
        outerJoint.getPlug("worldMatrix")[0].connectTo(outer.getPlug("inputMatrix"))
        h = origin.getPlug("outputTranslate")
        w = outer.getPlug("outputTranslate")
        rotation = graph._node("pickMatrix", "housingRotation")
        for flag in ("useTranslate", "useScale", "useShear"):
            rotation.getPlug(flag).set(False)
        housingMatrix.connectTo(rotation.getPlug("inputMatrix"))
        u = graph._node("vectorProduct", "housingAxis")
        u.getPlug("operation").set(3)
        u.getPlug("normalizeOutput").set(True)
        u.getPlug("input1").set(shaft_axis)
        housingMatrix.connectTo(u.getPlug("matrix"))

        # d = W - H、a = d·u、|d|²
        offset = graph._node("plusMinusAverage", "outerOffset")
        offset.getPlug("operation").set(2)
        w.connectTo(offset.getPlug("input3D")[0])
        h.connectTo(offset.getPlug("input3D")[1])
        axial = graph._node("vectorProduct", "axialDistance")
        axial.getPlug("operation").set(1)
        offset.getPlug("output3D").connectTo(axial.getPlug("input1"))
        u.getPlug("output").connectTo(axial.getPlug("input2"))
        squared = graph._node("vectorProduct", "offsetSquared")
        squared.getPlug("operation").set(1)
        offset.getPlug("output3D").connectTo(squared.getPlug("input1"))
        offset.getPlug("output3D").connectTo(squared.getPlug("input2"))
        a = axial.getPlug("outputX")

        # 制限前のプランジ p = a - √max(L² + a² - |d|², 0)
        powers = graph._node("multiplyDivide", "squares")
        owner.getPlug("length").connectTo(powers.getPlug("input1X"))
        owner.getPlug("length").connectTo(powers.getPlug("input2X"))
        a.connectTo(powers.getPlug("input1Y"))
        a.connectTo(powers.getPlug("input2Y"))
        total = graph._node("plusMinusAverage", "discriminantSum")
        powers.getPlug("outputX").connectTo(total.getPlug("input1D")[0])
        powers.getPlug("outputY").connectTo(total.getPlug("input1D")[1])
        discriminant = graph._node("plusMinusAverage", "discriminant")
        discriminant.getPlug("operation").set(2)
        total.getPlug("output1D").connectTo(discriminant.getPlug("input1D")[0])
        squared.getPlug("outputX").connectTo(discriminant.getPlug("input1D")[1])
        positive = graph._node("clamp", "discriminantPositive")
        positive.getPlug("maxR").set(1e12)
        discriminant.getPlug("output1D").connectTo(positive.getPlug("inputR"))
        root = graph._node("multiplyDivide", "discriminantRoot")
        root.getPlug("operation").set(3)
        root.getPlug("input2X").set(0.5)
        positive.getPlug("outputR").connectTo(root.getPlug("input1X"))
        raw = graph._node("plusMinusAverage", "rawPlunge")
        raw.getPlug("operation").set(2)
        a.connectTo(raw.getPlug("input1D")[0])
        root.getPlug("outputX").connectTo(raw.getPlug("input1D")[1])

        # plunge = clamp(p, minPlunge, maxPlunge)、overPlunge = p - plunge
        limit = graph._node("clamp", "plungeLimit")
        owner.getPlug("minPlunge").connectTo(limit.getPlug("minR"))
        owner.getPlug("maxPlunge").connectTo(limit.getPlug("maxR"))
        raw.getPlug("output1D").connectTo(limit.getPlug("inputR"))
        limit.getPlug("outputR").connectTo(owner.getPlug("plunge"))
        over = graph._node("plusMinusAverage", "overPlungeRaw")
        over.getPlug("operation").set(2)
        raw.getPlug("output1D").connectTo(over.getPlug("input1D")[0])
        limit.getPlug("outputR").connectTo(over.getPlug("input1D")[1])
        over.getPlug("output1D").connectTo(owner.getPlug("overPlunge"))

        # スパイダーの中心 c = H + u × plunge
        slide = graph._node("multiplyDivide", "slide")
        u.getPlug("output").connectTo(slide.getPlug("input1"))
        for component in "XYZ":
            limit.getPlug("outputR").connectTo(slide.getPlug("input2" + component))
        spider = graph._node("plusMinusAverage", "spiderCenter")
        h.connectTo(spider.getPlug("input3D")[0])
        slide.getPlug("output").connectTo(spider.getPlug("input3D")[1])
        c = spider.getPlug("output3D")

        # シャフト W - c の長さと向き v
        shaftOffset = graph._node("plusMinusAverage", "shaftOffset")
        shaftOffset.getPlug("operation").set(2)
        w.connectTo(shaftOffset.getPlug("input3D")[0])
        c.connectTo(shaftOffset.getPlug("input3D")[1])
        shaftSquared = graph._node("vectorProduct", "shaftSquared")
        shaftSquared.getPlug("operation").set(1)
        shaftOffset.getPlug("output3D").connectTo(shaftSquared.getPlug("input1"))
        shaftOffset.getPlug("output3D").connectTo(shaftSquared.getPlug("input2"))
        shaftRoot = graph._node("multiplyDivide", "shaftRoot")
        shaftRoot.getPlug("operation").set(3)
        shaftRoot.getPlug("input2X").set(0.5)
        shaftSquared.getPlug("outputX").connectTo(shaftRoot.getPlug("input1X"))
        shaftRoot.getPlug("outputX").connectTo(owner.getPlug("shaftLength"))
        stretch = graph._node("plusMinusAverage", "stretchRaw")
        stretch.getPlug("operation").set(2)
        owner.getPlug("shaftLength").connectTo(stretch.getPlug("input1D")[0])
        owner.getPlug("length").connectTo(stretch.getPlug("input1D")[1])
        stretch.getPlug("output1D").connectTo(owner.getPlug("stretch"))
        v = graph._node("vectorProduct", "shaftAxis")
        v.getPlug("operation").set(0)
        v.getPlug("normalizeOutput").set(True)
        shaftOffset.getPlug("output3D").connectTo(v.getPlug("input1"))

        # 向き R × Q(u→v)。位置はスパイダーの中心 c と外側の継手 W。
        arc = graph._node("angleBetween", "shaftArc")
        u.getPlug("output").connectTo(arc.getPlug("vector1"))
        v.getPlug("output").connectTo(arc.getPlug("vector2"))
        arc.getPlug("angle").connectTo(owner.getPlug("bendAngle"))
        for position, label, output in ((c, "spider", "matrix"), (w, "tip", "tipMatrix")):
            turn = graph._node("composeMatrix", label + "Turn")
            arc.getPlug("euler").connectTo(turn.getPlug("inputRotate"))
            position.connectTo(turn.getPlug("inputTranslate"))
            frame = graph._node("multMatrix", label + "Frame")
            rotation.getPlug("outputMatrix").connectTo(frame.getPlug("matrixIn")[0])
            turn.getPlug("outputMatrix").connectTo(frame.getPlug("matrixIn")[1])
            frame.getPlug("matrixSum").connectTo(owner.getPlug(output))

        owner.setAttrFlags(list(outputs) + ["bendAngle"], keyable=False, channelBox=True)
        # 位置の値はすべて内部単位(cm)のまま計算するので、UIの長さ単位で挿入された変換は係数1にする。
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        for node in added:
            node.getPlug("conversionFactor").set(1.0)
        if added:
            owner.addMembers(*added)
        return graph
