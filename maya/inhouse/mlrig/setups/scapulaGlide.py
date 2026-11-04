"""肩甲骨などの対象を、胸郭を表す楕円体の表面へ放射方向に投影し、表面の法線へ向けて滑らせる標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.ellipsoidCollision import EllipsoidCollision
from mlrig.setups.twistDistribution import TwistDistribution

# 中心からの距離がこれ以下なら向きが決まらないとみなし、仮の向き(局所+X)を使う(EllipsoidCollisionと同じ)。
_CENTER_EPSILON = 1e-6
# 軸ごとの半径の下限(cm)。0で割らないよう、作成時の引数とアトリビュートの最小値にする。
_MIN_RADIUS = 1e-4
_AXES = ("x", "y", "z")


class ScapulaGlide(TwistDistribution):
    """対象の位置を楕円体の表面へ放射方向に投影し、外向きの法線へ normalAxis を向けた行列を出力する標準DG。

    楕円体の軸は ribcage の transform の回転(scaleは除く)で、軸ごとの半径を radiusX・radiusY・radiusZ とする。
    中心 c から対象への向きを局所の向き l にすると、表面までの距離は R = 1 / |(lx/rx, ly/ry, lz/rz)|
    (EllipsoidCollision.directionRadius と同じ)、表面の点は s = l * R。表面の外向きの法線は
    陰関数 (x/rx)^2 + (y/ry)^2 + (z/rz)^2 = 1 の勾配 n = normalize(sx/rx^2, sy/ry^2, sz/rz^2)。
    出力の位置は表面の点から法線の向きへ offset だけ浮かせたもの。押し出しと違い、対象が表面から離れても
    常に表面へ吸い付く(肩甲骨が胸郭の上を滑る動き)。
    """

    @classmethod
    def glidePosition(cls, point, center, radii, offset=0.0,
                      axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))):
        """投影した位置と外向きの法線をPythonで計算する(生成するDGと同じ式)。

        Args:
            point (Sequence[float]): 対象のワールド位置(cm)。
            center (Sequence[float]): 楕円体の中心のワールド位置(cm)。
            radii (Sequence[float]): X・Y・Z軸の半径(cm、正)。
            offset (float): 表面から法線の向きへ浮かせる距離(cm、負なら内側)。
            axes (Sequence[Sequence[float]]): 楕円体の局所X・Y・Z軸のワールドでの向き(互いに直交する単位ベクトル)。

        Returns:
            tuple[tuple[float, float, float], tuple[float, float, float]]: 出力の位置(cm)と、
            ワールドでの外向きの単位法線。中心と一致する場合は局所+X の向きの表面を使う。
        """
        world = [float(a) - float(b) for a, b in zip(point, center)]
        length = math.sqrt(sum(value * value for value in world))
        if length <= _CENTER_EPSILON:
            local = [1.0, 0.0, 0.0]
        else:
            local = [sum(value * float(component) for value, component in zip(world, axis)) / length
                     for axis in axes]
        radius = EllipsoidCollision.directionRadius(local, radii)
        surface = [value * radius for value in local]
        gradient = [value / (float(r) * float(r)) for value, r in zip(surface, radii)]
        size = math.sqrt(sum(value * value for value in gradient))
        normal = [value / size for value in gradient]

        def toWorld(vector):
            return [sum(vector[index] * float(axes[index][item]) for index in range(3)) for item in range(3)]

        surfaceWorld = toWorld(surface)
        normalWorld = toWorld(normal)
        position = tuple(float(c) + s + n * float(offset) for c, s, n in zip(center, surfaceWorld, normalWorld))
        return position, tuple(normalWorld)

    @classmethod
    @undoTransaction("mlrig.ScapulaGlide.create")
    def create(cls, target, ribcage, name="scapulaGlide", radiusX=1.0, radiusY=1.0, radiusZ=1.0, offset=0.0,
               normalAxis="z", upAxis="y"):
        """targetの位置をribcageを中心とする楕円体の表面へ投影し、法線へ向けた行列を生成する。

        Args:
            target (str | Node): 投影する対象のtransform(肩甲骨のコントロール・鎖骨の先のlocatorなど)。
            ribcage (str | Node): 楕円体の中心と軸の向きを表すtransform(胸のjointなど)。scaleは半径に影響しない。
            name (str): 一意なcontainer名。
            radiusX (float): 局所X軸の半径の初期値(cm、正)。
            radiusY (float): 局所Y軸の半径の初期値(cm、正)。
            radiusZ (float): 局所Z軸の半径の初期値(cm、正)。
            offset (float): 表面から法線の向きへ浮かせる距離の初期値(cm)。肩甲骨の厚みなど。
            normalAxis (str): 出力の行列で外向きの法線へ向ける軸 x/y/z。
            upAxis (str): 出力の行列で target の同じ軸の向きへ揃える軸 x/y/z。normalAxisと異なる。

        Returns:
            ScapulaGlide: matrix・normal・distance・directionRadiusの所有者。
            containerに radiusX・radiusY・radiusZ・offset を持つ。

        Raises:
            ValueError: 値・軸が不正な場合、target・ribcageがtransformでない場合、同じノードの場合、
                またはnameが既に存在する場合。

        Note:
            c = ribcageのワールド位置、p = targetの位置、l = (p - c) を ribcage のワールド回転の逆で回して
            正規化した局所の向きとして directionRadius = R = 1 / |(lx / radiusX, ly / radiusY, lz / radiusZ)|、
            distance = |p - c| - R(放射方向に測った表面からの距離。外が正)、s = l * R、
            局所の法線 n = normalize(sx / radiusX^2, sy / radiusY^2, sz / radiusZ^2)、
            normal = n を ribcage のワールド回転で回したもの、位置 = c + rotate(s) + normal * offset。
            matrix は標準の ``aimMatrix`` で、その位置から normalAxis を normal へ向け、upAxis を
            targetのワールドの upAxis へ揃えた行列(scaleは1)。投影は中心からの放射方向で、表面の最近点ではない。
            |p - c| <= 1e-6cm では向きが決まらないため局所+X の表面を使う。target の upAxis が法線と平行になると
            ねじれの向きが不定になる。
        """
        radiusX, radiusY, radiusZ, offset = float(radiusX), float(radiusY), float(radiusZ), float(offset)
        if not all(math.isfinite(value) for value in (radiusX, radiusY, radiusZ, offset)):
            raise ValueError("radiusX, radiusY, radiusZ and offset must be finite")
        if min(radiusX, radiusY, radiusZ) < _MIN_RADIUS:
            raise ValueError("radiusX, radiusY and radiusZ must be at least {}".format(_MIN_RADIUS))
        if normalAxis not in _AXES or upAxis not in _AXES or normalAxis == upAxis:
            raise ValueError("normalAxis and upAxis must be two different axes of x, y and z")
        if mlib.objExists(name):
            raise ValueError("ScapulaGlide container already exists: " + name)
        target = mlib.nodes.Node(target)
        ribcage = mlib.nodes.Node(ribcage)
        for node in (target, ribcage):
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected transforms for the target and the ribcage")
        if target.getFullName() == ribcage.getFullName():
            raise ValueError("target and ribcage must be different nodes")
        normal_axis = [float(axis == normalAxis) for axis in _AXES]
        up_axis = [float(axis == upAxis) for axis in _AXES]

        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        for longName, value in (("radiusX", radiusX), ("radiusY", radiusY), ("radiusZ", radiusZ)):
            owner.addAttr(longName=longName, attributeType="double", defaultValue=value, keyable=True,
                          minValue=_MIN_RADIUS)
        owner.addAttr(longName="offset", attributeType="double", defaultValue=offset, keyable=True)
        for longName in ("distance", "directionRadius"):
            owner.addAttr(longName=longName, attributeType="double")
        owner.addAttr(longName="normal", attributeType="double3")
        owner.addAttr(longName="matrix", dataType="matrix")

        # 中心 c(と軸の回転)、対象の位置 p
        center = graph._node("decomposeMatrix", "center")
        ribcage.getPlug("worldMatrix")[0].connectTo(center.getPlug("inputMatrix"))
        position = graph._node("decomposeMatrix", "position")
        target.getPlug("worldMatrix")[0].connectTo(position.getPlug("inputMatrix"))
        p = position.getPlug("outputTranslate")
        c = center.getPlug("outputTranslate")

        # 局所→ワールドの回転(scaleを除く)と、その逆(単位クォータニオンの共役 (-x, -y, -z, w))。
        toWorld = graph._node("composeMatrix", "toWorld")
        toWorld.getPlug("useEulerRotation").set(False)
        conjugate = graph._node("multiplyDivide", "conjugate")
        for item in "XYZ":
            center.getPlug("outputQuat" + item).connectTo(toWorld.getPlug("inputQuat" + item))
            center.getPlug("outputQuat" + item).connectTo(conjugate.getPlug("input1" + item))
            conjugate.getPlug("input2" + item).set(-1.0)
        center.getPlug("outputQuatW").connectTo(toWorld.getPlug("inputQuatW"))
        toLocal = graph._node("composeMatrix", "toLocal")
        toLocal.getPlug("useEulerRotation").set(False)
        for item in "XYZ":
            conjugate.getPlug("output" + item).connectTo(toLocal.getPlug("inputQuat" + item))
        center.getPlug("outputQuatW").connectTo(toLocal.getPlug("inputQuatW"))

        # 局所の向き l。中心と一致する場合は長さ0のベクトルを正規化しないよう、ワールドで局所+Xの向きへ置き換える。
        worldOffset = graph._node("plusMinusAverage", "worldOffset")
        worldOffset.getPlug("operation").set(2)
        p.connectTo(worldOffset.getPlug("input3D")[0])
        c.connectTo(worldOffset.getPlug("input3D")[1])
        length = graph._node("distanceBetween", "worldLength")
        p.connectTo(length.getPlug("point1"))
        c.connectTo(length.getPlug("point2"))
        fallback = graph._node("vectorProduct", "fallbackDirection")
        fallback.getPlug("operation").set(3)
        fallback.getPlug("input1").set((1.0, 0.0, 0.0))
        toWorld.getPlug("outputMatrix").connectTo(fallback.getPlug("matrix"))
        safeOffset = graph._node("condition", "safeOffset")
        safeOffset.getPlug("operation").set(2)
        length.getPlug("distance").connectTo(safeOffset.getPlug("firstTerm"))
        safeOffset.getPlug("secondTerm").set(_CENTER_EPSILON)
        worldOffset.getPlug("output3D").connectTo(safeOffset.getPlug("colorIfTrue"))
        fallback.getPlug("output").connectTo(safeOffset.getPlug("colorIfFalse"))
        local = graph._node("vectorProduct", "localDirection")
        local.getPlug("operation").set(3)
        local.getPlug("normalizeOutput").set(True)
        safeOffset.getPlug("outColor").connectTo(local.getPlug("input1"))
        toLocal.getPlug("outputMatrix").connectTo(local.getPlug("matrix"))

        # R = 1 / |(lx / rx, ly / ry, lz / rz)|、distance = |p - c| - R
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
        distance = graph._node("plusMinusAverage", "distance")
        distance.getPlug("operation").set(2)
        length.getPlug("distance").connectTo(distance.getPlug("input1D")[0])
        radius.getPlug("outputX").connectTo(distance.getPlug("input1D")[1])
        distance.getPlug("output1D").connectTo(owner.getPlug("distance"))

        # 表面の点 s = l * R と、局所の法線 n = normalize(s / r^2)
        surface = graph._node("multiplyDivide", "surfaceLocal")
        local.getPlug("output").connectTo(surface.getPlug("input1"))
        for item in "XYZ":
            radius.getPlug("outputX").connectTo(surface.getPlug("input2" + item))
        squared = graph._node("multiplyDivide", "radiusSquared")
        for item in "XYZ":
            owner.getPlug("radius" + item).connectTo(squared.getPlug("input1" + item))
            owner.getPlug("radius" + item).connectTo(squared.getPlug("input2" + item))
        gradient = graph._node("multiplyDivide", "gradient")
        gradient.getPlug("operation").set(2)
        surface.getPlug("output").connectTo(gradient.getPlug("input1"))
        squared.getPlug("output").connectTo(gradient.getPlug("input2"))

        # ワールドへ回す: rotate(s) と normal = rotate(n) の正規化
        surfaceWorld = graph._node("vectorProduct", "surfaceWorld")
        surfaceWorld.getPlug("operation").set(3)
        surface.getPlug("output").connectTo(surfaceWorld.getPlug("input1"))
        toWorld.getPlug("outputMatrix").connectTo(surfaceWorld.getPlug("matrix"))
        normal = graph._node("vectorProduct", "normalWorld")
        normal.getPlug("operation").set(3)
        normal.getPlug("normalizeOutput").set(True)
        gradient.getPlug("output").connectTo(normal.getPlug("input1"))
        toWorld.getPlug("outputMatrix").connectTo(normal.getPlug("matrix"))
        normal.getPlug("output").connectTo(owner.getPlug("normal"))

        # 位置 = c + rotate(s) + normal * offset と、法線の先の点
        lift = graph._node("multiplyDivide", "lift")
        normal.getPlug("output").connectTo(lift.getPlug("input1"))
        for item in "XYZ":
            owner.getPlug("offset").connectTo(lift.getPlug("input2" + item))
        glide = graph._node("plusMinusAverage", "glidePosition")
        c.connectTo(glide.getPlug("input3D")[0])
        surfaceWorld.getPlug("output").connectTo(glide.getPlug("input3D")[1])
        lift.getPlug("output").connectTo(glide.getPlug("input3D")[2])
        ahead = graph._node("plusMinusAverage", "normalTip")
        glide.getPlug("output3D").connectTo(ahead.getPlug("input3D")[0])
        normal.getPlug("output").connectTo(ahead.getPlug("input3D")[1])
        origin = graph._node("composeMatrix", "origin")
        glide.getPlug("output3D").connectTo(origin.getPlug("inputTranslate"))
        tip = graph._node("composeMatrix", "normalTipMatrix")
        ahead.getPlug("output3D").connectTo(tip.getPlug("inputTranslate"))

        # 向き: 位置から normalAxis を法線の先へ向け、upAxis を target の upAxis へ揃える。
        frame = graph._node("aimMatrix", "frame")
        origin.getPlug("outputMatrix").connectTo(frame.getPlug("inputMatrix"))
        tip.getPlug("outputMatrix").connectTo(frame.getPlug("primaryTargetMatrix"))
        frame.getPlug("primaryMode").set(1)
        frame.getPlug("primaryInputAxis").set(normal_axis)
        frame.getPlug("primaryTargetVector").set((0, 0, 0))
        frame.getPlug("secondaryMode").set(2)
        frame.getPlug("secondaryInputAxis").set(up_axis)
        frame.getPlug("secondaryTargetVector").set(up_axis)
        target.getPlug("worldMatrix")[0].connectTo(frame.getPlug("secondaryTargetMatrix"))
        frame.getPlug("outputMatrix").connectTo(owner.getPlug("matrix"))

        owner.setAttrFlags(["distance", "directionRadius"], keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph
