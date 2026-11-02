"""対象の位置がトーラス(輪)の管の中へ入らないよう、輪の芯の円から外へ柔らかく押し出す標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.planeCollision import PlaneCollision
from mlrig.setups.sphereCollision import SphereCollision

# 輪の軸からの距離がこれ以下なら芯の円上の最近点が決まらないとみなし、輪の局所Xの向きの点を使う。
_AXIS_EPSILON = 1e-6
# 芯の円上の最近点からの距離がこれ以下なら向きが決まらないとみなし、押し出さない(SphereCollisionと同じ)。
_CENTER_EPSILON = 1e-6


def _normalized(vector):
    """vectorを長さ1にする。長さ0ならNone。"""
    length = math.sqrt(sum(value * value for value in vector))
    if length <= 1e-12:
        return None
    return [value / length for value in vector]


class TorusCollision(SphereCollision):
    """輪の中心 c・軸 n・芯の円の半径 R の円上の最近点 q からの符号付き距離を、SphereCollisionと同じ柔らかい押し出しで 0 へ漸近させる標準DG。

    v = p - c、height = dot(v, n)、w = v - height n(輪の平面への射影)、
    q = c + R w / |w|、d = |p - q| - minorRadius とし、d >= softness なら入力のまま、
    d < softness なら d' = softness * exp((d - softness) / softness)。出力の行列は入力のワールド行列を、
    q から対象への向き u へ (d' - d) だけ平行移動したもの。回転は変えない。
    押し込まれた深さ penetration = max(-d, 0)、輪の平面からの高さ height、軸からの距離 axisDistance = |w| も出力する。
    """

    @classmethod
    def closestRingPoint(cls, point, center, axis, majorRadius, fallback=None):
        """輪の芯の円上の最近点をPythonで計算する(生成するDGと同じ式)。

        Args:
            point (Sequence[float]): 対象のワールド位置(cm)。
            center (Sequence[float]): 輪の中心のワールド位置(cm)。
            axis (Sequence[float]): 輪の軸(輪の平面の法線)のワールドの向き。長さは問わない。
            majorRadius (float): 芯の円の半径(cm)。
            fallback (Sequence[float] | None): 対象が軸上にある場合に使う、輪の平面内の向き。
                生成するDGでは輪のtransformの局所X。Noneならワールドの+X(軸と平行なら+Z)を輪の平面へ射影した向き。

        Returns:
            tuple[float, float, float]: 芯の円上の最近点(cm)。

        Raises:
            ValueError: axisの長さが0の場合。
        """
        normal = _normalized([float(value) for value in axis])
        if normal is None:
            raise ValueError("axis must not be a zero vector")
        offset = [float(p) - float(c) for p, c in zip(point, center)]
        height = sum(a * b for a, b in zip(offset, normal))
        planar = [value - height * n for value, n in zip(offset, normal)]
        if math.sqrt(sum(value * value for value in planar)) <= _AXIS_EPSILON:
            candidates = [fallback] if fallback is not None else [(1.0, 0.0, 0.0), (0.0, 0.0, 1.0)]
            planar = None
            for candidate in candidates:
                vector = [float(value) for value in candidate]
                dot = sum(a * b for a, b in zip(vector, normal))
                planar = _normalized([value - dot * n for value, n in zip(vector, normal)])
                if planar is not None:
                    break
            if planar is None:
                raise ValueError("fallback must not be parallel to the axis")
        direction = _normalized(planar)
        return tuple(float(c) + float(majorRadius) * value for c, value in zip(center, direction))

    @classmethod
    def pushedPosition(cls, point, center, axis, majorRadius, minorRadius, softness, fallback=None):
        """押し出した後の位置をPythonで計算する(生成するDGと同じ式)。

        Args:
            point (Sequence[float]): 対象のワールド位置(cm)。
            center (Sequence[float]): 輪の中心のワールド位置(cm)。
            axis (Sequence[float]): 輪の軸のワールドの向き。長さは問わない。
            majorRadius (float): 芯の円の半径(cm)。
            minorRadius (float): 管の半径(cm)。
            softness (float): 柔らかく押し出し始める距離(cm)。0以下なら硬い押し出し。
            fallback (Sequence[float] | None): 対象が軸上にある場合に使う、輪の平面内の向き(closestRingPointと同じ)。

        Returns:
            tuple[float, float, float]: 押し出した後の位置(cm)。芯の円上の最近点と一致する場合は入力のまま。

        Raises:
            ValueError: axisの長さが0の場合。
        """
        closest = cls.closestRingPoint(point, center, axis, majorRadius, fallback)
        offset = [float(p) - q for p, q in zip(point, closest)]
        length = math.sqrt(sum(value * value for value in offset))
        if length <= _CENTER_EPSILON:
            return tuple(float(value) for value in point)
        distance = length - float(minorRadius)
        push = PlaneCollision.response(distance, float(softness)) - distance
        return tuple(float(p) + value / length * push for p, value in zip(point, offset))

    @classmethod
    @undoTransaction("mlrig.TorusCollision.create")
    def create(cls, target, torus, name="torusCollision", majorRadius=4.0, minorRadius=1.0, softness=1.0):
        """targetのワールド位置を、torusを中心とし局所Yを軸とするトーラスの管の中へ入らないよう押し出した行列を生成する。

        Args:
            target (str | Node): 押し出す対象のtransform(コントロールなど)。
            torus (str | Node): 輪の中心と向きを表すtransform(局所Yが輪の軸)。scaleは半径に影響しない。
            name (str): 一意なcontainer名。
            majorRadius (float): 輪の芯の円の半径の初期値(cm、0以上)。0なら球と同じ。
            minorRadius (float): 管の半径の初期値(cm、0以上)。対象の太さを含めてもよい。
            softness (float): 柔らかく押し出し始める距離の初期値(cm、0以上)。0なら硬く止める。

        Returns:
            TorusCollision: matrix・distance・push・penetration・height・axisDistanceの所有者。
            containerに majorRadius・minorRadius・softness を持つ。

        Raises:
            ValueError: 値が不正な場合、target・torusがtransformでない場合、同じノードの場合、
                またはnameが既に存在する場合。

        Note:
            c = torusのワールド位置、n・x = torusの局所Y・局所Xのワールドの向き(scaleを除いた回転)、
            p = targetの位置として v = p - c、height = dot(v, n)、w = v - height n、axisDistance = |w|、
            q = c + majorRadius w / |w|(|w| <= 1e-6cm なら w の代わりに x)、distance = |p - q| - minorRadius、
            push = response(distance, softness) - distance、penetration = max(-distance, 0)、
            matrix = targetのworldMatrix · T(u * push)、u = (p - q) / |p - q|。
            トーラスの符号付き距離は厳密で、軸上では芯の円上の全ての点が等距離なので distance は連続する
            (押し出す向きだけを x で決める)。|p - q| <= 1e-6cm では向きが決まらないため押し出さない。
        """
        majorRadius, minorRadius, softness = float(majorRadius), float(minorRadius), float(softness)
        if not all(math.isfinite(value) for value in (majorRadius, minorRadius, softness)):
            raise ValueError("majorRadius, minorRadius and softness must be finite")
        if min(majorRadius, minorRadius, softness) < 0.0:
            raise ValueError("majorRadius, minorRadius and softness must not be negative")
        if mlib.objExists(name):
            raise ValueError("TorusCollision container already exists: " + name)
        target = mlib.nodes.Node(target)
        torus = mlib.nodes.Node(torus)
        for node in (target, torus):
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected transforms for the target and the torus")
        if target.getFullName() == torus.getFullName():
            raise ValueError("target and torus must be different nodes")

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        for longName, value in (("majorRadius", majorRadius), ("minorRadius", minorRadius), ("softness", softness)):
            owner.addAttr(longName=longName, attributeType="double", defaultValue=value, keyable=True,
                          minValue=0)
        for longName in ("distance", "push", "penetration", "height", "axisDistance"):
            owner.addAttr(longName=longName, attributeType="double")
        owner.addAttr(longName="matrix", dataType="matrix")

        # 中心 c(と輪の回転)、対象の位置 p
        center = graph._node("decomposeMatrix", "center")
        torus.getPlug("worldMatrix")[0].connectTo(center.getPlug("inputMatrix"))
        position = graph._node("decomposeMatrix", "position")
        target.getPlug("worldMatrix")[0].connectTo(position.getPlug("inputMatrix"))
        p = position.getPlug("outputTranslate")
        c = center.getPlug("outputTranslate")

        # scaleを除いた回転だけの行列で、局所Y(軸 n)と局所X(軸上での仮の向き x)をワールドへ向ける。
        rotation = graph._node("composeMatrix", "rotation")
        rotation.getPlug("useEulerRotation").set(False)
        for item in "XYZW":
            center.getPlug("outputQuat" + item).connectTo(rotation.getPlug("inputQuat" + item))
        axes = []
        for label, local in (("axis", (0.0, 1.0, 0.0)), ("fallback", (1.0, 0.0, 0.0))):
            product = graph._node("vectorProduct", label)
            product.getPlug("operation").set(3)
            product.getPlug("normalizeOutput").set(True)
            product.getPlug("input1").set(local)
            rotation.getPlug("outputMatrix").connectTo(product.getPlug("matrix"))
            axes.append(product.getPlug("output"))
        n, x = axes

        # v = p - c、height = dot(v, n)、w = v - height n
        offset = graph._node("plusMinusAverage", "ringOffset")
        offset.getPlug("operation").set(2)
        p.connectTo(offset.getPlug("input3D")[0])
        c.connectTo(offset.getPlug("input3D")[1])
        height = graph._node("vectorProduct", "height")
        height.getPlug("operation").set(1)
        height.getPlug("normalizeOutput").set(False)
        offset.getPlug("output3D").connectTo(height.getPlug("input1"))
        n.connectTo(height.getPlug("input2"))
        height.getPlug("outputX").connectTo(owner.getPlug("height"))
        lift = graph._node("multiplyDivide", "lift")
        n.connectTo(lift.getPlug("input1"))
        for item in "XYZ":
            height.getPlug("outputX").connectTo(lift.getPlug("input2" + item))
        planar = graph._node("plusMinusAverage", "planar")
        planar.getPlug("operation").set(2)
        offset.getPlug("output3D").connectTo(planar.getPlug("input3D")[0])
        lift.getPlug("output").connectTo(planar.getPlug("input3D")[1])
        axisDistance = graph._node("distanceBetween", "axisDistance")
        planar.getPlug("output3D").connectTo(axisDistance.getPlug("point1"))
        axisDistance.getPlug("distance").connectTo(owner.getPlug("axisDistance"))

        # 軸上では長さ0のベクトルを正規化しないよう、局所Xの向きへ置き換える。
        safePlanar = graph._node("condition", "safePlanar")
        safePlanar.getPlug("operation").set(2)
        axisDistance.getPlug("distance").connectTo(safePlanar.getPlug("firstTerm"))
        safePlanar.getPlug("secondTerm").set(_AXIS_EPSILON)
        planar.getPlug("output3D").connectTo(safePlanar.getPlug("colorIfTrue"))
        x.connectTo(safePlanar.getPlug("colorIfFalse"))
        ringDirection = graph._node("vectorProduct", "ringDirection")
        ringDirection.getPlug("operation").set(0)
        ringDirection.getPlug("normalizeOutput").set(True)
        safePlanar.getPlug("outColor").connectTo(ringDirection.getPlug("input1"))

        # q = c + majorRadius w / |w|
        ringRadius = graph._node("multiplyDivide", "ringRadius")
        ringDirection.getPlug("output").connectTo(ringRadius.getPlug("input1"))
        for item in "XYZ":
            owner.getPlug("majorRadius").connectTo(ringRadius.getPlug("input2" + item))
        closest = graph._node("plusMinusAverage", "ringPoint")
        c.connectTo(closest.getPlug("input3D")[0])
        ringRadius.getPlug("output").connectTo(closest.getPlug("input3D")[1])

        cls._radialGraph(graph, target, p, closest.getPlug("output3D"), owner.getPlug("minorRadius"))
        return graph
