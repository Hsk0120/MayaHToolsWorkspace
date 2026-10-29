"""対象の位置が楕円体の中へ入らないよう、楕円体の中心からの向きへ柔らかく押し出す標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.planeCollision import PlaneCollision
from mlrig.setups.sphereCollision import SphereCollision

# 中心からの距離がこれ以下なら向きが決まらないとみなし、押し出さない(SphereCollisionと同じ)。
_CENTER_EPSILON = 1e-6
# 軸ごとの半径の下限(cm)。0で割らないよう、作成時の引数とアトリビュートの最小値にする。
_MIN_RADIUS = 1e-4


class EllipsoidCollision(SphereCollision):
    """中心 c から対象への向き u での楕円体の半径 R(u) を求め、SphereCollisionと同じ柔らかい押し出しを当てる標準DG。

    楕円体の軸は ellipsoid の transform の回転(scaleは除く)で、軸ごとの半径を radiusX・radiusY・radiusZ とする。
    u をその局所の向き (ux, uy, uz) にすると R(u) = 1 / sqrt((ux/rx)^2 + (uy/ry)^2 + (uz/rz)^2) で、
    これは中心から u の向きへ伸ばした半直線が楕円体の表面と交わるまでの距離。
    d = |p - c| - R(u) とし、d >= softness なら入力のまま、d < softness なら
    d' = softness * exp((d - softness) / softness)。出力の行列は入力のワールド行列を u へ (d' - d) だけ
    平行移動したもの。回転は変えない。3つの半径が同じなら SphereCollision と一致する。
    """

    @classmethod
    def directionRadius(cls, direction, radii):
        """楕円体の局所の向きでの、中心から表面までの距離 R(u) をPythonで計算する(生成するDGと同じ式)。

        Args:
            direction (Sequence[float]): 楕円体の局所空間での向き。長さは問わない(内部で正規化する)。
            radii (Sequence[float]): X・Y・Z軸の半径(cm、正)。

        Returns:
            float: 中心から表面までの距離(cm)。向きの長さが0ならX軸の半径。
        """
        length = math.sqrt(sum(float(value) * float(value) for value in direction))
        if length <= _CENTER_EPSILON:
            return float(radii[0])
        scaled = [float(value) / length / float(radius) for value, radius in zip(direction, radii)]
        return 1.0 / math.sqrt(sum(value * value for value in scaled))

    @classmethod
    def pushedPosition(cls, point, center, radii, softness, axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))):
        """押し出した後の位置をPythonで計算する(生成するDGと同じ式)。

        Args:
            point (Sequence[float]): 対象のワールド位置(cm)。
            center (Sequence[float]): 楕円体の中心のワールド位置(cm)。
            radii (Sequence[float]): X・Y・Z軸の半径(cm、正)。
            softness (float): 柔らかく押し出し始める距離(cm)。0以下なら硬い押し出し。
            axes (Sequence[Sequence[float]]): 楕円体の局所X・Y・Z軸のワールドでの向き(互いに直交する単位ベクトル)。

        Returns:
            tuple[float, float, float]: 押し出した後の位置(cm)。中心と一致する場合は入力のまま。
        """
        offset = [float(a) - float(b) for a, b in zip(point, center)]
        length = math.sqrt(sum(value * value for value in offset))
        if length <= _CENTER_EPSILON:
            return tuple(float(value) for value in point)
        local = [sum(value * float(component) for value, component in zip(offset, axis)) for axis in axes]
        distance = length - cls.directionRadius(local, radii)
        push = PlaneCollision.response(distance, float(softness)) - distance
        return tuple(float(p) + value / length * push for p, value in zip(point, offset))

    @classmethod
    @undoTransaction("mlrig.EllipsoidCollision.create")
    def create(cls, target, ellipsoid, name="ellipsoidCollision", radiusX=1.0, radiusY=1.0, radiusZ=1.0,
               softness=1.0):
        """targetのワールド位置を、ellipsoidを中心とする楕円体の中へ入らないよう押し出した行列を生成する。

        Args:
            target (str | Node): 押し出す対象のtransform(コントロールなど)。
            ellipsoid (str | Node): 楕円体の中心と軸の向きを表すtransform(胸・頭・太もものjointなど)。
                scaleは半径に影響しない。
            name (str): 一意なcontainer名。
            radiusX (float): 局所X軸の半径の初期値(cm、正)。
            radiusY (float): 局所Y軸の半径の初期値(cm、正)。
            radiusZ (float): 局所Z軸の半径の初期値(cm、正)。
            softness (float): 柔らかく押し出し始める距離の初期値(cm、0以上)。0なら硬く止める。

        Returns:
            EllipsoidCollision: matrix・distance・push・penetration・directionRadiusの所有者。
            containerに radiusX・radiusY・radiusZ・softness を持つ。

        Raises:
            ValueError: 値が不正な場合、target・ellipsoidがtransformでない場合、同じノードの場合、
                またはnameが既に存在する場合。

        Note:
            c = ellipsoidのワールド位置、p = targetの位置、u = (p - c) / |p - c| とし、
            l = u を ellipsoid のワールド回転の逆で回した局所の向きとして
            directionRadius = R = 1 / |(lx / radiusX, ly / radiusY, lz / radiusZ)|、
            distance = |p - c| - R、push = response(distance, softness) - distance、
            penetration = max(-distance, 0)、matrix = targetのworldMatrix · T(u * push)。
            押し出す向きは中心からの放射方向で、表面の法線ではない。distance は表面の最近点までの距離ではなく
            放射方向に測った距離なので、軸の半径の比が大きいほど、細い向きの近くで真の距離より大きくなる。
            |p - c| <= 1e-6cm では向きが決まらないため push = 0 とし、押し出さない。
        """
        radiusX, radiusY, radiusZ, softness = float(radiusX), float(radiusY), float(radiusZ), float(softness)
        if not all(math.isfinite(value) for value in (radiusX, radiusY, radiusZ, softness)):
            raise ValueError("radiusX, radiusY, radiusZ and softness must be finite")
        if min(radiusX, radiusY, radiusZ) < _MIN_RADIUS:
            raise ValueError("radiusX, radiusY and radiusZ must be at least {}".format(_MIN_RADIUS))
        if softness < 0.0:
            raise ValueError("softness must not be negative")
        if mlib.ls(name):
            raise ValueError("EllipsoidCollision container already exists: " + name)
        target = mlib.nodes.Node(target)
        ellipsoid = mlib.nodes.Node(ellipsoid)
        for node in (target, ellipsoid):
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected transforms for the target and the ellipsoid")
        if target.getFullName() == ellipsoid.getFullName():
            raise ValueError("target and ellipsoid must be different nodes")

        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        for longName, value in (("radiusX", radiusX), ("radiusY", radiusY), ("radiusZ", radiusZ)):
            owner.addAttr(longName=longName, attributeType="double", defaultValue=value, keyable=True,
                          minValue=_MIN_RADIUS)
        owner.addAttr(longName="softness", attributeType="double", defaultValue=softness, keyable=True,
                      minValue=0)
        for longName in ("distance", "push", "penetration", "directionRadius"):
            owner.addAttr(longName=longName, attributeType="double")
        owner.addAttr(longName="matrix", dataType="matrix")

        # 中心 c(と軸の回転)、対象の位置 p
        center = graph._node("decomposeMatrix", "center")
        ellipsoid.getPlug("worldMatrix")[0].connectTo(center.getPlug("inputMatrix"))
        position = graph._node("decomposeMatrix", "position")
        target.getPlug("worldMatrix")[0].connectTo(position.getPlug("inputMatrix"))
        p = position.getPlug("outputTranslate")
        c = center.getPlug("outputTranslate")

        # ワールドの向きを局所の向きへ戻す行列(scaleを除いた回転の逆)。単位クォータニオンの逆は共役 (-x, -y, -z, w)。
        conjugate = graph._node("multiplyDivide", "conjugate")
        for item in "XYZ":
            center.getPlug("outputQuat" + item).connectTo(conjugate.getPlug("input1" + item))
            conjugate.getPlug("input2" + item).set(-1.0)
        toLocal = graph._node("composeMatrix", "toLocal")
        toLocal.getPlug("useEulerRotation").set(False)
        for item in "XYZ":
            conjugate.getPlug("output" + item).connectTo(toLocal.getPlug("inputQuat" + item))
        center.getPlug("outputQuatW").connectTo(toLocal.getPlug("inputQuatW"))

        # 局所の向き l。中心と一致する場合は長さ0のベクトルを正規化しないよう、仮の向き(+X)へ置き換える。
        offset = graph._node("plusMinusAverage", "worldOffset")
        offset.getPlug("operation").set(2)
        p.connectTo(offset.getPlug("input3D")[0])
        c.connectTo(offset.getPlug("input3D")[1])
        length = graph._node("distanceBetween", "worldLength")
        p.connectTo(length.getPlug("point1"))
        c.connectTo(length.getPlug("point2"))
        safeOffset = graph._node("condition", "localSafeOffset")
        safeOffset.getPlug("operation").set(2)
        length.getPlug("distance").connectTo(safeOffset.getPlug("firstTerm"))
        safeOffset.getPlug("secondTerm").set(_CENTER_EPSILON)
        offset.getPlug("output3D").connectTo(safeOffset.getPlug("colorIfTrue"))
        safeOffset.getPlug("colorIfFalse").set((1.0, 0.0, 0.0))
        local = graph._node("vectorProduct", "localDirection")
        local.getPlug("operation").set(3)
        local.getPlug("normalizeOutput").set(True)
        safeOffset.getPlug("outColor").connectTo(local.getPlug("input1"))
        toLocal.getPlug("outputMatrix").connectTo(local.getPlug("matrix"))

        # R = 1 / |(lx / rx, ly / ry, lz / rz)|
        scaled = graph._node("multiplyDivide", "scaledDirection")
        scaled.getPlug("operation").set(2)
        local.getPlug("output").connectTo(scaled.getPlug("input1"))
        for item in "XYZ":
            owner.getPlug("radius" + item).connectTo(scaled.getPlug("input2" + item))
        scaledLength = graph._node("distanceBetween", "scaledLength")
        scaled.getPlug("output").connectTo(scaledLength.getPlug("point1"))
        radius = graph._node("multiplyDivide", "directionRadius")
        radius.getPlug("operation").set(2)
        radius.getPlug("input1X").set(1.0)
        scaledLength.getPlug("distance").connectTo(radius.getPlug("input2X"))
        radius.getPlug("outputX").connectTo(owner.getPlug("directionRadius"))

        cls._radialGraph(graph, target, p, c, radius.getPlug("outputX"))
        return graph
