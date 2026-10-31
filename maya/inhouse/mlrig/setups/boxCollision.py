"""対象の位置が箱(角を丸められる直方体)の中へ入らないよう、表面の法線の向きへ柔らかく押し出す標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.planeCollision import PlaneCollision
from mlrig.setups.twistDistribution import TwistDistribution

# 箱の外へ出た長さがこれより大きければ「外」とみなし、最近点からの向きを法線にする。
_OUTSIDE_EPSILON = 1e-6
# 辺の長さの下限(cm)。作成時の引数とアトリビュートの最小値にする。
_MIN_SIZE = 1e-4


class BoxCollision(TwistDistribution):
    """箱の符号付き距離 d と表面の法線 n を求め、PlaneCollisionと同じ柔らかい押し出しで n の向きへ押し出す標準DG。

    箱の中心と軸は box の transform の位置と回転(scaleは除く)で、辺の長さを sizeX・sizeY・sizeZ、
    角と辺の丸めの半径を rounding とする。局所の位置 l、内側の箱の半分の長さ e = max(size / 2 - rounding, 0) として、
    外なら最近点 k = clamp(l, -e, e) から d = |l - k| - rounding、n = (l - k) / |l - k|。
    中なら q = |l| - e の最大の成分の軸 i で d = q_i - rounding、n = sign(l_i) * 軸i。
    d >= softness なら入力のまま、d < softness なら d' = softness * exp((d - softness) / softness)。
    出力の行列は入力のワールド行列をワールドの n へ (d' - d) だけ平行移動したもの。回転は変えない。
    """

    @classmethod
    def signedDistance(cls, local, size, rounding=0.0):
        """箱の局所の位置での符号付き距離と法線をPythonで計算する(生成するDGと同じ式)。

        Args:
            local (Sequence[float]): 箱の中心から見た局所の位置(cm)。
            size (Sequence[float]): X・Y・Z軸の辺の長さ(cm、正)。
            rounding (float): 角と辺の丸めの半径(cm、0以上)。

        Returns:
            tuple[float, tuple[float, float, float]]: 表面からの符号付き距離(cm、中は負)と、局所の法線(単位ベクトル)。
        """
        half = [max(float(value) * 0.5 - float(rounding), 0.0) for value in size]
        local = [float(value) for value in local]
        outside = [value - min(max(value, -limit), limit) for value, limit in zip(local, half)]
        length = math.sqrt(sum(value * value for value in outside))
        if length > _OUTSIDE_EPSILON:
            return length - float(rounding), tuple(value / length for value in outside)
        depth = [abs(value) - limit for value, limit in zip(local, half)]
        # 同じ値なら X、Y、Z の順に優先する(DGの condition の >= と同じ)。
        axis = 0
        if depth[1] > depth[0]:
            axis = 1
        if depth[2] > depth[axis]:
            axis = 2
        normal = [0.0, 0.0, 0.0]
        normal[axis] = 1.0 if local[axis] >= 0.0 else -1.0
        return depth[axis] - float(rounding), tuple(normal)

    @classmethod
    def pushedPosition(cls, point, center, size, softness, rounding=0.0,
                       axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))):
        """押し出した後の位置をPythonで計算する(生成するDGと同じ式)。

        Args:
            point (Sequence[float]): 対象のワールド位置(cm)。
            center (Sequence[float]): 箱の中心のワールド位置(cm)。
            size (Sequence[float]): X・Y・Z軸の辺の長さ(cm、正)。
            softness (float): 柔らかく押し出し始める距離(cm)。0以下なら硬い押し出し。
            rounding (float): 角と辺の丸めの半径(cm、0以上)。
            axes (Sequence[Sequence[float]]): 箱の局所X・Y・Z軸のワールドでの向き(互いに直交する単位ベクトル)。

        Returns:
            tuple[float, float, float]: 押し出した後の位置(cm)。
        """
        offset = [float(a) - float(b) for a, b in zip(point, center)]
        local = [sum(value * float(component) for value, component in zip(offset, axis)) for axis in axes]
        distance, normal = cls.signedDistance(local, size, rounding)
        push = PlaneCollision.response(distance, float(softness)) - distance
        world = [sum(n * float(axis[index]) for n, axis in zip(normal, axes)) for index in range(3)]
        return tuple(float(p) + value * push for p, value in zip(point, world))

    @classmethod
    @undoTransaction("mlrig.BoxCollision.create")
    def create(cls, target, box, name="boxCollision", sizeX=2.0, sizeY=2.0, sizeZ=2.0, rounding=0.0,
               softness=1.0):
        """targetのワールド位置を、boxを中心とする箱の中へ入らないよう押し出した行列を生成する。

        Args:
            target (str | Node): 押し出す対象のtransform(コントロールなど)。
            box (str | Node): 箱の中心と軸の向きを表すtransform(腰・胸・机の天板など)。scaleは大きさに影響しない。
            name (str): 一意なcontainer名。
            sizeX (float): 局所X軸の辺の長さの初期値(cm、正)。
            sizeY (float): 局所Y軸の辺の長さの初期値(cm、正)。
            sizeZ (float): 局所Z軸の辺の長さの初期値(cm、正)。
            rounding (float): 角と辺の丸めの半径の初期値(cm、0以上)。辺の長さの半分を超えた軸は丸めだけになる。
            softness (float): 柔らかく押し出し始める距離の初期値(cm、0以上)。0なら硬く止める。

        Returns:
            BoxCollision: matrix・distance・push・penetration・normalの所有者。
            containerに sizeX・sizeY・sizeZ・rounding・softness を持つ。

        Raises:
            ValueError: 値が不正な場合、target・boxがtransformでない場合、同じノードの場合、
                またはnameが既に存在する場合。

        Note:
            c = boxのワールド位置、p = targetの位置、l = p - c を box のワールド回転の逆で回した局所の位置、
            e = max(size / 2 - rounding, 0) として、
            |l - clamp(l, -e, e)| > 1e-6cm(外)なら distance = |l - k| - rounding、法線は (l - k) の向き、
            そうでなければ(中)distance = max_i(|l_i| - e_i) - rounding、法線は最も浅い面の向き。
            push = response(distance, softness) - distance、penetration = max(-distance, 0)、
            normal = ワールドの法線、matrix = targetのworldMatrix · T(normal * push)。
            中の法線は最も浅い面で決まるので、箱の中心を通る面の境目(中心と辺を結ぶ面)をまたぐと、
            深く押し込んだ場合は押し出す面が切り替わって出力が跳ぶ。中心では X、Y、Z の順に優先した +側の面へ押し出す。
        """
        sizeX, sizeY, sizeZ = float(sizeX), float(sizeY), float(sizeZ)
        rounding, softness = float(rounding), float(softness)
        if not all(math.isfinite(value) for value in (sizeX, sizeY, sizeZ, rounding, softness)):
            raise ValueError("sizeX, sizeY, sizeZ, rounding and softness must be finite")
        if min(sizeX, sizeY, sizeZ) < _MIN_SIZE:
            raise ValueError("sizeX, sizeY and sizeZ must be at least {}".format(_MIN_SIZE))
        if rounding < 0.0 or softness < 0.0:
            raise ValueError("rounding and softness must not be negative")
        if mlib.objExists(name):
            raise ValueError("BoxCollision container already exists: " + name)
        target = mlib.nodes.Node(target)
        box = mlib.nodes.Node(box)
        for node in (target, box):
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected transforms for the target and the box")
        if target.getFullName() == box.getFullName():
            raise ValueError("target and box must be different nodes")

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        for longName, value in (("sizeX", sizeX), ("sizeY", sizeY), ("sizeZ", sizeZ)):
            owner.addAttr(longName=longName, attributeType="double", defaultValue=value, keyable=True,
                          minValue=_MIN_SIZE)
        owner.addAttr(longName="rounding", attributeType="double", defaultValue=rounding, keyable=True,
                      minValue=0)
        owner.addAttr(longName="softness", attributeType="double", defaultValue=softness, keyable=True,
                      minValue=0)
        for longName in ("distance", "push", "penetration"):
            owner.addAttr(longName=longName, attributeType="double")
        owner.addAttr(longName="normal", attributeType="double3")
        owner.addAttr(longName="matrix", dataType="matrix")

        # 中心 c(と軸の回転)、対象の位置 p
        center = graph._node("decomposeMatrix", "center")
        box.getPlug("worldMatrix")[0].connectTo(center.getPlug("inputMatrix"))
        position = graph._node("decomposeMatrix", "position")
        target.getPlug("worldMatrix")[0].connectTo(position.getPlug("inputMatrix"))

        # 局所とワールドの回転の行列(scaleを除く)。単位クォータニオンの逆は共役 (-x, -y, -z, w)。
        conjugate = graph._node("multiplyDivide", "conjugate")
        toLocal = graph._node("composeMatrix", "toLocal")
        toWorld = graph._node("composeMatrix", "toWorld")
        for node in (toLocal, toWorld):
            node.getPlug("useEulerRotation").set(False)
            center.getPlug("outputQuatW").connectTo(node.getPlug("inputQuatW"))
        for item in "XYZ":
            center.getPlug("outputQuat" + item).connectTo(conjugate.getPlug("input1" + item))
            conjugate.getPlug("input2" + item).set(-1.0)
            conjugate.getPlug("output" + item).connectTo(toLocal.getPlug("inputQuat" + item))
            center.getPlug("outputQuat" + item).connectTo(toWorld.getPlug("inputQuat" + item))

        # l = (p - c) を局所へ
        offset = graph._node("plusMinusAverage", "worldOffset")
        offset.getPlug("operation").set(2)
        position.getPlug("outputTranslate").connectTo(offset.getPlug("input3D")[0])
        center.getPlug("outputTranslate").connectTo(offset.getPlug("input3D")[1])
        local = graph._node("vectorProduct", "local")
        local.getPlug("operation").set(3)
        offset.getPlug("output3D").connectTo(local.getPlug("input1"))
        toLocal.getPlug("outputMatrix").connectTo(local.getPlug("matrix"))
        l = local.getPlug("output")

        # e = clamp(size / 2 - rounding, 0, size / 2)
        half = graph._node("multiplyDivide", "half")
        for item in "XYZ":
            owner.getPlug("size" + item).connectTo(half.getPlug("input1" + item))
            half.getPlug("input2" + item).set(0.5)
        shrunk = graph._node("plusMinusAverage", "shrunk")
        shrunk.getPlug("operation").set(2)
        half.getPlug("output").connectTo(shrunk.getPlug("input3D")[0])
        for item in "xyz":
            owner.getPlug("rounding").connectTo(shrunk.getPlug("input3D[1].input3D" + item))
        inner = graph._node("clamp", "inner")
        shrunk.getPlug("output3D").connectTo(inner.getPlug("input"))
        inner.getPlug("min").set((0.0, 0.0, 0.0))
        half.getPlug("output").connectTo(inner.getPlug("max"))
        e = inner.getPlug("output")

        # 外: 最近点 k = clamp(l, -e, e)、外へ出た分 o = l - k とその長さ
        negative = graph._node("multiplyDivide", "negativeInner")
        e.connectTo(negative.getPlug("input1"))
        negative.getPlug("input2").set((-1.0, -1.0, -1.0))
        closest = graph._node("clamp", "closest")
        l.connectTo(closest.getPlug("input"))
        negative.getPlug("output").connectTo(closest.getPlug("min"))
        e.connectTo(closest.getPlug("max"))
        outside = graph._node("plusMinusAverage", "outside")
        outside.getPlug("operation").set(2)
        l.connectTo(outside.getPlug("input3D")[0])
        closest.getPlug("output").connectTo(outside.getPlug("input3D")[1])
        outsideLength = graph._node("distanceBetween", "outsideLength")
        outside.getPlug("output3D").connectTo(outsideLength.getPlug("point1"))

        # 中: q = |l| - e(|l| = sqrt(l * l))
        square = graph._node("multiplyDivide", "square")
        l.connectTo(square.getPlug("input1"))
        l.connectTo(square.getPlug("input2"))
        absolute = graph._node("multiplyDivide", "absolute")
        absolute.getPlug("operation").set(3)
        square.getPlug("output").connectTo(absolute.getPlug("input1"))
        absolute.getPlug("input2").set((0.5, 0.5, 0.5))
        depth = graph._node("plusMinusAverage", "depth")
        depth.getPlug("operation").set(2)
        absolute.getPlug("output").connectTo(depth.getPlug("input3D")[0])
        e.connectTo(depth.getPlug("input3D")[1])
        q = [depth.getPlug("output3D" + item) for item in "xyz"]

        # 各軸の符号付きの面の向き sign(l_i) * 軸i(l_i >= 0 なら +)
        faces = []
        for index, item in enumerate("XYZ"):
            face = graph._node("condition", "face" + item)
            face.getPlug("operation").set(3)
            local.getPlug("output" + item).connectTo(face.getPlug("firstTerm"))
            face.getPlug("secondTerm").set(0.0)
            face.getPlug("colorIfTrue").set(tuple(1.0 if axis == index else 0.0 for axis in range(3)))
            face.getPlug("colorIfFalse").set(tuple(-1.0 if axis == index else 0.0 for axis in range(3)))
            faces.append(face.getPlug("outColor"))

        # 最も浅い面: q の最大(同じ値なら X、Y、Z の順)とその面の向き
        depthXY = graph._node("condition", "depthXY")
        faceXY = graph._node("condition", "faceXY")
        for node in (depthXY, faceXY):
            node.getPlug("operation").set(3)
            q[0].connectTo(node.getPlug("firstTerm"))
            q[1].connectTo(node.getPlug("secondTerm"))
        q[0].connectTo(depthXY.getPlug("colorIfTrueR"))
        q[1].connectTo(depthXY.getPlug("colorIfFalseR"))
        faces[0].connectTo(faceXY.getPlug("colorIfTrue"))
        faces[1].connectTo(faceXY.getPlug("colorIfFalse"))
        depthMax = graph._node("condition", "depthMax")
        faceMax = graph._node("condition", "faceMax")
        for node in (depthMax, faceMax):
            node.getPlug("operation").set(3)
            depthXY.getPlug("outColorR").connectTo(node.getPlug("firstTerm"))
            q[2].connectTo(node.getPlug("secondTerm"))
        depthXY.getPlug("outColorR").connectTo(depthMax.getPlug("colorIfTrueR"))
        q[2].connectTo(depthMax.getPlug("colorIfFalseR"))
        faceXY.getPlug("outColor").connectTo(faceMax.getPlug("colorIfTrue"))
        faces[2].connectTo(faceMax.getPlug("colorIfFalse"))

        # 外か中かで距離と局所の法線を選ぶ
        boxDistance = graph._node("condition", "boxDistance")
        localNormal = graph._node("condition", "localNormal")
        for node in (boxDistance, localNormal):
            node.getPlug("operation").set(2)
            outsideLength.getPlug("distance").connectTo(node.getPlug("firstTerm"))
            node.getPlug("secondTerm").set(_OUTSIDE_EPSILON)
        outsideLength.getPlug("distance").connectTo(boxDistance.getPlug("colorIfTrueR"))
        depthMax.getPlug("outColorR").connectTo(boxDistance.getPlug("colorIfFalseR"))
        outside.getPlug("output3D").connectTo(localNormal.getPlug("colorIfTrue"))
        faceMax.getPlug("outColor").connectTo(localNormal.getPlug("colorIfFalse"))

        # d = 箱からの距離 - rounding、n = ワールドの法線
        distance = graph._node("plusMinusAverage", "distance")
        distance.getPlug("operation").set(2)
        boxDistance.getPlug("outColorR").connectTo(distance.getPlug("input1D")[0])
        owner.getPlug("rounding").connectTo(distance.getPlug("input1D")[1])
        d = distance.getPlug("output1D")
        d.connectTo(owner.getPlug("distance"))
        normal = graph._node("vectorProduct", "normal")
        normal.getPlug("operation").set(3)
        normal.getPlug("normalizeOutput").set(True)
        localNormal.getPlug("outColor").connectTo(normal.getPlug("input1"))
        toWorld.getPlug("outputMatrix").connectTo(normal.getPlug("matrix"))
        normal.getPlug("output").connectTo(owner.getPlug("normal"))

        push = PlaneCollision._pushGraph(graph, d, owner.getPlug("softness"))
        push.getPlug("output1D").connectTo(owner.getPlug("push"))

        # penetration = max(-d, 0)
        penetration = graph._node("condition", "penetration")
        penetration.getPlug("operation").set(4)
        d.connectTo(penetration.getPlug("firstTerm"))
        penetration.getPlug("secondTerm").set(0.0)
        negate = graph._node("plusMinusAverage", "negate")
        negate.getPlug("operation").set(2)
        negate.getPlug("input1D")[0].set(0.0)
        d.connectTo(negate.getPlug("input1D")[1])
        negate.getPlug("output1D").connectTo(penetration.getPlug("colorIfTrueR"))
        penetration.getPlug("colorIfFalseR").set(0.0)
        penetration.getPlug("outColorR").connectTo(owner.getPlug("penetration"))

        # matrix = targetのworldMatrix · T(n * push)
        move = graph._node("multiplyDivide", "move")
        normal.getPlug("output").connectTo(move.getPlug("input1"))
        for item in "XYZ":
            push.getPlug("output1D").connectTo(move.getPlug("input2" + item))
        translate = graph._node("composeMatrix", "translate")
        move.getPlug("output").connectTo(translate.getPlug("inputTranslate"))
        world = graph._node("multMatrix", "world")
        target.getPlug("worldMatrix")[0].connectTo(world.getPlug("matrixIn")[0])
        translate.getPlug("outputMatrix").connectTo(world.getPlug("matrixIn")[1])
        world.getPlug("matrixSum").connectTo(owner.getPlug("matrix"))
        return graph
