"""対象の位置がカプセル(線分を軸とし両端が半球の形)の中へ入らないよう、軸から外へ柔らかく押し出す標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.planeCollision import PlaneCollision
from mlrig.setups.sphereCollision import SphereCollision

# 線分の長さの2乗がこれ以下なら長さ0とみなし、始点を最近点にする(球と同じ)。
_LENGTH_EPSILON = 1e-12
# 最近点からの距離がこれ以下なら向きが決まらないとみなし、押し出さない(SphereCollisionと同じ)。
_CENTER_EPSILON = 1e-6


class CapsuleCollision(SphereCollision):
    """始点 a・終点 b を結ぶ線分上の最近点 q からの符号付き距離を、SphereCollisionと同じ柔らかい押し出しで 0 へ漸近させる標準DG。

    t = clamp(dot(p - a, b - a) / |b - a|^2, 0, 1)、q = a + t (b - a)、
    半径は両端の値を t で補間した r(t) = startRadius + (endRadius - startRadius) t。
    d = |p - q| - r(t) とし、d >= softness なら入力のまま、d < softness なら
    d' = softness * exp((d - softness) / softness)。出力の行列は入力のワールド行列を、
    q から対象への向き u へ (d' - d) だけ平行移動したもの。回転は変えない。
    押し込まれた深さ penetration = max(-d, 0) と、軸上の位置 parameter = t も出力する。
    """

    @classmethod
    def closestParameter(cls, point, start, end):
        """線分上の最近点の位置 t (0〜1)をPythonで計算する(生成するDGと同じ式)。

        Args:
            point (Sequence[float]): 対象のワールド位置(cm)。
            start (Sequence[float]): 線分の始点のワールド位置(cm)。
            end (Sequence[float]): 線分の終点のワールド位置(cm)。

        Returns:
            float: 0(始点)〜1(終点)。線分の長さが0なら0。
        """
        axis = [float(b) - float(a) for a, b in zip(start, end)]
        relative = [float(p) - float(a) for a, p in zip(start, point)]
        lengthSquared = sum(value * value for value in axis)
        if lengthSquared <= _LENGTH_EPSILON:
            return 0.0
        ratio = sum(a * b for a, b in zip(relative, axis)) / lengthSquared
        return min(max(ratio, 0.0), 1.0)

    @classmethod
    def pushedPosition(cls, point, start, end, startRadius, endRadius, softness):
        """押し出した後の位置をPythonで計算する(生成するDGと同じ式)。

        Args:
            point (Sequence[float]): 対象のワールド位置(cm)。
            start (Sequence[float]): 線分の始点のワールド位置(cm)。
            end (Sequence[float]): 線分の終点のワールド位置(cm)。
            startRadius (float): 始点側の半径(cm)。
            endRadius (float): 終点側の半径(cm)。
            softness (float): 柔らかく押し出し始める距離(cm)。0以下なら硬い押し出し。

        Returns:
            tuple[float, float, float]: 押し出した後の位置(cm)。最近点と一致する場合は入力のまま。
        """
        parameter = cls.closestParameter(point, start, end)
        closest = [float(a) + (float(b) - float(a)) * parameter for a, b in zip(start, end)]
        offset = [float(p) - q for p, q in zip(point, closest)]
        length = math.sqrt(sum(value * value for value in offset))
        if length <= _CENTER_EPSILON:
            return tuple(float(value) for value in point)
        radius = float(startRadius) + (float(endRadius) - float(startRadius)) * parameter
        distance = length - radius
        push = PlaneCollision.response(distance, float(softness)) - distance
        return tuple(float(p) + value / length * push for p, value in zip(point, offset))

    @classmethod
    @undoTransaction("mlrig.CapsuleCollision.create")
    def create(cls, target, start, end, name="capsuleCollision", startRadius=1.0, endRadius=1.0,
               softness=1.0):
        """targetのワールド位置を、startとendを結ぶ線分を軸とするカプセルの中へ入らないよう押し出した行列を生成する。

        Args:
            target (str | Node): 押し出す対象のtransform(コントロールなど)。
            start (str | Node): 軸の始点を表すtransform(上腕・太もものjointなど)。scaleは半径に影響しない。
            end (str | Node): 軸の終点を表すtransform(肘・膝のjointなど)。
            name (str): 一意なcontainer名。
            startRadius (float): 始点側の半径の初期値(cm、0以上)。
            endRadius (float): 終点側の半径の初期値(cm、0以上)。始点側と違えば先細りのカプセルになる。
            softness (float): 柔らかく押し出し始める距離の初期値(cm、0以上)。0なら硬く止める。

        Returns:
            CapsuleCollision: matrix・distance・push・penetration・parameterの所有者。
            containerに startRadius・endRadius・softness を持つ。

        Raises:
            ValueError: 値が不正な場合、target・start・endがtransformでない場合、同じノードを含む場合、
                またはnameが既に存在する場合。

        Note:
            a・b = start・endのワールド位置、p = targetの位置として
            parameter = t = clamp(dot(p - a, b - a) / |b - a|^2, 0, 1)、q = a + t (b - a)、
            r = startRadius + (endRadius - startRadius) t、distance = |p - q| - r、
            push = response(distance, softness) - distance、penetration = max(-distance, 0)、
            matrix = targetのworldMatrix · T(u * push)、u = (p - q) / |p - q|。
            半径が違う場合、r は軸への垂直な射影の位置で補間する近似で、先細りの側面の真の最近点とは
            半径の差が大きいほどずれる(両端の半径が同じなら厳密)。
            |b - a|^2 <= 1e-12 なら t = 0(始点を中心とする球)、|p - q| <= 1e-6cm なら押し出さない。
        """
        startRadius, endRadius, softness = float(startRadius), float(endRadius), float(softness)
        if not all(math.isfinite(value) for value in (startRadius, endRadius, softness)):
            raise ValueError("startRadius, endRadius and softness must be finite")
        if min(startRadius, endRadius, softness) < 0.0:
            raise ValueError("startRadius, endRadius and softness must not be negative")
        if mlib.objExists(name):
            raise ValueError("CapsuleCollision container already exists: " + name)
        nodes = [mlib.nodes.Node(node) for node in (target, start, end)]
        for node in nodes:
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected transforms for the target, the start and the end")
        if len({node.getFullName() for node in nodes}) != 3:
            raise ValueError("target, start and end must be different nodes")
        target, start, end = nodes

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        for longName, value in (("startRadius", startRadius), ("endRadius", endRadius), ("softness", softness)):
            owner.addAttr(longName=longName, attributeType="double", defaultValue=value, keyable=True,
                          minValue=0)
        for longName in ("distance", "push", "penetration", "parameter"):
            owner.addAttr(longName=longName, attributeType="double")
        owner.addAttr(longName="matrix", dataType="matrix")

        # 始点 a・終点 b・対象の位置 p
        points = []
        for node, label in ((start, "start"), (end, "end"), (target, "position")):
            decompose = graph._node("decomposeMatrix", label)
            node.getPlug("worldMatrix")[0].connectTo(decompose.getPlug("inputMatrix"))
            points.append(decompose.getPlug("outputTranslate"))
        a, b, p = points

        # 軸 b - a と p - a
        axis = graph._node("plusMinusAverage", "axis")
        axis.getPlug("operation").set(2)
        b.connectTo(axis.getPlug("input3D")[0])
        a.connectTo(axis.getPlug("input3D")[1])
        relative = graph._node("plusMinusAverage", "relative")
        relative.getPlug("operation").set(2)
        p.connectTo(relative.getPlug("input3D")[0])
        a.connectTo(relative.getPlug("input3D")[1])

        # t = clamp(dot(p - a, b - a) / |b - a|^2, 0, 1)。長さ0の線分は分母を1に置き換える(分子も0なので t = 0)。
        projection = graph._node("vectorProduct", "projection")
        projection.getPlug("operation").set(1)
        projection.getPlug("normalizeOutput").set(False)
        relative.getPlug("output3D").connectTo(projection.getPlug("input1"))
        axis.getPlug("output3D").connectTo(projection.getPlug("input2"))
        lengthSquared = graph._node("vectorProduct", "lengthSquared")
        lengthSquared.getPlug("operation").set(1)
        lengthSquared.getPlug("normalizeOutput").set(False)
        axis.getPlug("output3D").connectTo(lengthSquared.getPlug("input1"))
        axis.getPlug("output3D").connectTo(lengthSquared.getPlug("input2"))
        safeLength = graph._node("condition", "safeLength")
        safeLength.getPlug("operation").set(2)
        lengthSquared.getPlug("outputX").connectTo(safeLength.getPlug("firstTerm"))
        safeLength.getPlug("secondTerm").set(_LENGTH_EPSILON)
        lengthSquared.getPlug("outputX").connectTo(safeLength.getPlug("colorIfTrueR"))
        safeLength.getPlug("colorIfFalseR").set(1.0)
        ratio = graph._node("multiplyDivide", "ratio")
        ratio.getPlug("operation").set(2)
        projection.getPlug("outputX").connectTo(ratio.getPlug("input1X"))
        safeLength.getPlug("outColorR").connectTo(ratio.getPlug("input2X"))
        parameter = graph._node("clamp", "parameter")
        parameter.getPlug("minR").set(0.0)
        parameter.getPlug("maxR").set(1.0)
        ratio.getPlug("outputX").connectTo(parameter.getPlug("inputR"))
        t = parameter.getPlug("outputR")
        t.connectTo(owner.getPlug("parameter"))

        # q = a + t (b - a)
        along = graph._node("multiplyDivide", "along")
        axis.getPlug("output3D").connectTo(along.getPlug("input1"))
        for item in "XYZ":
            t.connectTo(along.getPlug("input2" + item))
        closest = graph._node("plusMinusAverage", "closest")
        a.connectTo(closest.getPlug("input3D")[0])
        along.getPlug("output").connectTo(closest.getPlug("input3D")[1])

        # r = startRadius + (endRadius - startRadius) t
        taper = graph._node("plusMinusAverage", "taper")
        taper.getPlug("operation").set(2)
        owner.getPlug("endRadius").connectTo(taper.getPlug("input1D")[0])
        owner.getPlug("startRadius").connectTo(taper.getPlug("input1D")[1])
        taperAlong = graph._node("multiplyDivide", "taperAlong")
        taper.getPlug("output1D").connectTo(taperAlong.getPlug("input1X"))
        t.connectTo(taperAlong.getPlug("input2X"))
        radius = graph._node("plusMinusAverage", "radius")
        owner.getPlug("startRadius").connectTo(radius.getPlug("input1D")[0])
        taperAlong.getPlug("outputX").connectTo(radius.getPlug("input1D")[1])

        cls._radialGraph(graph, target, p, closest.getPlug("output3D"), radius.getPlug("output1D"))
        return graph
