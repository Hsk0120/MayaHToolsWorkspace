"""対象の位置が球の中へ入らないよう、球の中心からの向きへ柔らかく押し出す標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.planeCollision import PlaneCollision
from mlrig.setups.twistDistribution import TwistDistribution

# 中心からの距離がこれ以下なら向きが決まらないとみなし、押し出さない。
_CENTER_EPSILON = 1e-6


class SphereCollision(TwistDistribution):
    """球の表面からの符号付き距離 d を、PlaneCollisionと同じ柔らかい押し出しで 0 へ漸近させる標準DG。

    d = |p - c| - radius とし、d >= softness なら入力のまま、d < softness なら
    d' = softness * exp((d - softness) / softness)。出力の行列は入力のワールド行列を、
    中心から対象への向き u へ (d' - d) だけ平行移動したもの。回転は変えない。
    押し込まれた深さ penetration = max(-d, 0) も出力し、補正シェイプのドライバーへ使える。
    """

    @classmethod
    def pushedPosition(cls, point, center, radius, softness):
        """押し出した後の位置をPythonで計算する(生成するDGと同じ式)。

        Args:
            point (Sequence[float]): 対象のワールド位置(cm)。
            center (Sequence[float]): 球の中心のワールド位置(cm)。
            radius (float): 球の半径(cm)。
            softness (float): 柔らかく押し出し始める距離(cm)。0以下なら硬い押し出し。

        Returns:
            tuple[float, float, float]: 押し出した後の位置(cm)。中心と一致する場合は入力のまま。
        """
        offset = [float(a) - float(b) for a, b in zip(point, center)]
        length = math.sqrt(sum(value * value for value in offset))
        if length <= _CENTER_EPSILON:
            return tuple(float(value) for value in point)
        distance = length - float(radius)
        push = PlaneCollision.response(distance, float(softness)) - distance
        return tuple(float(p) + value / length * push for p, value in zip(point, offset))

    @classmethod
    @undoTransaction("mlrig.SphereCollision.create")
    def create(cls, target, sphere, name="sphereCollision", radius=1.0, softness=1.0):
        """targetのワールド位置を、sphereを中心とする球の中へ入らないよう押し出した行列を生成する。

        Args:
            target (str | Node): 押し出す対象のtransform(コントロールなど)。
            sphere (str | Node): 球の中心を表すtransform。scaleは半径に影響しない。
            name (str): 一意なcontainer名。
            radius (float): 球の半径の初期値(cm、0以上)。対象の太さを含めてもよい。
            softness (float): 柔らかく押し出し始める距離の初期値(cm、0以上)。0なら硬く止める。

        Returns:
            SphereCollision: matrix・distance・push・penetrationの所有者。containerに radius・softness を持つ。

        Raises:
            ValueError: 値が不正な場合、target・sphereがtransformでない場合、同じノードの場合、
                またはnameが既に存在する場合。

        Note:
            c = sphereのワールド位置、p = targetの位置、u = (p - c) / |p - c| として
            distance = |p - c| - radius、push = response(distance, softness) - distance、
            penetration = max(-distance, 0)、matrix = targetのworldMatrix · T(u * push)。
            生成時に対象が表面から softness 以上離れていれば push = 0 で入力と一致する(跳ねない)。
            |p - c| <= 1e-6cm では向きが決まらないため push = 0 とし、押し出さない。
        """
        radius, softness = float(radius), float(softness)
        if not (math.isfinite(softness) and math.isfinite(radius)):
            raise ValueError("radius and softness must be finite")
        if softness < 0.0 or radius < 0.0:
            raise ValueError("radius and softness must not be negative")
        if mlib.objExists(name):
            raise ValueError("SphereCollision container already exists: " + name)
        target = mlib.nodes.Node(target)
        sphere = mlib.nodes.Node(sphere)
        for node in (target, sphere):
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected transforms for the target and the sphere")
        if target.getFullName() == sphere.getFullName():
            raise ValueError("target and sphere must be different nodes")

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="radius", attributeType="double", defaultValue=radius, keyable=True,
                      minValue=0)
        owner.addAttr(longName="softness", attributeType="double", defaultValue=softness, keyable=True,
                      minValue=0)
        owner.addAttr(longName="distance", attributeType="double")
        owner.addAttr(longName="push", attributeType="double")
        owner.addAttr(longName="penetration", attributeType="double")
        owner.addAttr(longName="matrix", dataType="matrix")

        # 中心 c と対象の位置 p
        center = graph._node("decomposeMatrix", "center")
        sphere.getPlug("worldMatrix")[0].connectTo(center.getPlug("inputMatrix"))
        position = graph._node("decomposeMatrix", "position")
        target.getPlug("worldMatrix")[0].connectTo(position.getPlug("inputMatrix"))
        cls._radialGraph(graph, target, position.getPlug("outputTranslate"), center.getPlug("outputTranslate"),
                         owner.getPlug("radius"))
        return graph

    @classmethod
    def _radialGraph(cls, graph, target, point, center, radius):
        """中心から対象への向きへ柔らかく押し出すDGを作り、containerの出力へつなぐ。

        Args:
            graph (SphereCollision): 所有者。containerに softness・distance・push・penetration・matrix を持つ。
            target (Node): 押し出す対象のtransform。出力の行列はこのworldMatrixを基にする。
            point (Plug): 対象のワールド位置 p(double3)。
            center (Plug): 押し出しの中心 c(double3)。
            radius (Plug): 中心からの半径(double)。
        """
        owner = graph.container
        # v = p - c とその向き u
        offset = graph._node("plusMinusAverage", "offset")
        offset.getPlug("operation").set(2)
        point.connectTo(offset.getPlug("input3D")[0])
        center.connectTo(offset.getPlug("input3D")[1])
        length = graph._node("distanceBetween", "length")
        point.connectTo(length.getPlug("point1"))
        center.connectTo(length.getPlug("point2"))
        # 中心と一致する場合は長さ0のベクトルを正規化しないよう、仮の向き(+X)へ置き換える(押し出し量は0にする)。
        safeOffset = graph._node("condition", "safeOffset")
        safeOffset.getPlug("operation").set(2)
        length.getPlug("distance").connectTo(safeOffset.getPlug("firstTerm"))
        safeOffset.getPlug("secondTerm").set(_CENTER_EPSILON)
        offset.getPlug("output3D").connectTo(safeOffset.getPlug("colorIfTrue"))
        safeOffset.getPlug("colorIfFalse").set((1.0, 0.0, 0.0))
        direction = graph._node("vectorProduct", "direction")
        direction.getPlug("operation").set(0)
        direction.getPlug("normalizeOutput").set(True)
        safeOffset.getPlug("outColor").connectTo(direction.getPlug("input1"))

        # d = |v| - radius
        distance = graph._node("plusMinusAverage", "distance")
        distance.getPlug("operation").set(2)
        length.getPlug("distance").connectTo(distance.getPlug("input1D")[0])
        radius.connectTo(distance.getPlug("input1D")[1])
        d = distance.getPlug("output1D")
        d.connectTo(owner.getPlug("distance"))

        soft = PlaneCollision._pushGraph(graph, d, owner.getPlug("softness"))
        push = graph._node("condition", "centerGate")
        push.getPlug("operation").set(2)
        length.getPlug("distance").connectTo(push.getPlug("firstTerm"))
        push.getPlug("secondTerm").set(_CENTER_EPSILON)
        soft.getPlug("output1D").connectTo(push.getPlug("colorIfTrueR"))
        push.getPlug("colorIfFalseR").set(0.0)
        push.getPlug("outColorR").connectTo(owner.getPlug("push"))

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

        # matrix = targetのworldMatrix · T(u * push)
        move = graph._node("multiplyDivide", "move")
        direction.getPlug("output").connectTo(move.getPlug("input1"))
        for item in "XYZ":
            push.getPlug("outColorR").connectTo(move.getPlug("input2" + item))
        translate = graph._node("composeMatrix", "translate")
        move.getPlug("output").connectTo(translate.getPlug("inputTranslate"))
        world = graph._node("multMatrix", "world")
        target.getPlug("worldMatrix")[0].connectTo(world.getPlug("matrixIn")[0])
        translate.getPlug("outputMatrix").connectTo(world.getPlug("matrixIn")[1])
        world.getPlug("matrixSum").connectTo(owner.getPlug("matrix"))
