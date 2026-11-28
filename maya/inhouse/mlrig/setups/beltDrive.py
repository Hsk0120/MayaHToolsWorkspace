"""2つのプーリーにかかるベルトの直線部・巻き付け角・回転の比を、軸間距離と半径から求める標準DGを構築する。"""

import math

import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.decorator import nativeUnits, undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

#: 2つのプーリーの中心が重なって割り算が0にならないようにする、軸間距離の下限(cm)。
_MIN_DISTANCE = 1e-3


class BeltDrive(TwistDistribution):
    """駆動プーリーの回転1つで、従動プーリーとベルトの直線部(上下2本)を動かす標準DG。

    土台の空間(土台のtransformのローカル)で、駆動プーリーの中心を原点、従動プーリーの中心を ``(d, 0, 0)`` 、
    回転軸をZとする。半径 ``r1`` ・ ``r2`` の2円の共通接線を、平行掛け(オープン、 ``k = r1 - r2``)と
    十字掛け(クロス、 ``k = r1 + r2``)で同じ式で解く。接点へ向かう半径の角度 ``θ = acos(k / d)`` 、
    直線部の長さ ``L = sqrt(d^2 - k^2)`` 、上の直線部は駆動側の接点 ``r1 (cosθ, sinθ)`` から
    ``(sinθ, -cosθ)`` の向きへ ``L`` 伸びる。従動プーリーは ``±r1 / r2`` 倍で回る(十字掛けは逆回り)。
    ``d`` は共通接線が引ける範囲 ``|k|`` 以上で止め、足りない量を ``excess`` へ出す。
    フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def evaluate(cls, distance, driverRadius, drivenRadius, crossed=False):
        """止めた軸間距離・足りない量・接点の角度・直線部と巻き付け・ベルトの長さ・回転の比を計算する(DGと同じ式のPython版)。

        Args:
            distance (float): 2つのプーリーの軸間距離。
            driverRadius (float): 駆動プーリーの半径(distanceと同じ単位)。
            drivenRadius (float): 従動プーリーの半径。
            crossed (bool): Trueなら十字掛け(ベルトが途中で交差し、従動プーリーが逆に回る)。

        Returns:
            tuple[float, float, float, float, float, float, float, float]: (止めた軸間距離, 足りない量(0以下),
            接点の角度θ(度), 直線部の長さ, 駆動側の巻き付け角(度), 従動側の巻き付け角(度), ベルトの長さ, 回転の比)。
        """
        sign = -1.0 if crossed else 1.0
        reach = driverRadius - sign * drivenRadius
        clamped = max(distance, abs(reach), _MIN_DISTANCE)
        span = math.sqrt(max(clamped * clamped - reach * reach, 0.0))
        tangent = math.atan2(span, reach)
        driverWrap = 2.0 * math.pi - 2.0 * tangent
        drivenWrap = math.pi + sign * (2.0 * tangent - math.pi)
        length = 2.0 * span + driverRadius * driverWrap + drivenRadius * drivenWrap
        return (clamped, distance - clamped, math.degrees(tangent), span, math.degrees(driverWrap),
                math.degrees(drivenWrap), length, sign * driverRadius / drivenRadius)

    @classmethod
    @undoTransaction("mlrig.BeltDrive.create")
    def create(cls, base=None, driverRadius=2.0, drivenRadius=1.0, distance=6.0, crossed=False, name="beltDrive"):
        """ベルト伝動の計算containerを作る。

        Args:
            base (str | Node | None): 土台のtransform(駆動プーリーの中心。+Xが従動プーリーの向き、Zが回転軸)。
                出力の行列はこのworldMatrixに追従する。Noneならワールド原点。
            driverRadius (float): 駆動プーリーの半径(cm、0より大きい)。
            drivenRadius (float): 従動プーリーの半径(cm、0より大きい)。
            distance (float): 軸間距離の初期値(cm、0以上)。
            crossed (bool): Trueなら十字掛け。Falseなら平行掛け。
            name (str): 一意なcontainer名。

        Returns:
            BeltDrive: containerに rotation(駆動プーリーの回転)・driverRadius・drivenRadius・distance・crossed(keyable)と、
                clampedDistance・excess・spanLength・beltLength・travel・ratio・tangentAngle・driverWrap・drivenWrap・
                drivenRotation、``driverMatrix`` ・ ``drivenMatrix`` (プーリー)、``upperSpanMatrix`` ・ ``lowerSpanMatrix``
                (駆動側の接点を原点、X=従動側の接点への向き)のワールド行列を持つ。

        Raises:
            ValueError: 半径・distanceが不正な場合、crossedがboolでない場合、baseがtransformでない場合、
                またはnameが既に存在する場合。

        Note:
            全体を内部単位(cm・radian)で組むので、UI単位を変えても自動の unitConversion は入らない。
            直線部の行列のローカル ``(spanLength, 0, 0)`` が従動側の接点。上の直線部のYはベルトの外側を向く。
            ベルトの伸び・たるみ・滑りは扱わず、ベルトの長さは ``beltLength`` へ出すだけで一定には保たない。
        """
        for label, value in (("driverRadius", driverRadius), ("drivenRadius", drivenRadius)):
            if isinstance(value, bool) or not math.isfinite(float(value)) or value <= 0.0:
                raise ValueError(label + " must be greater than 0")
        if isinstance(distance, bool) or not math.isfinite(float(distance)) or distance < 0.0:
            raise ValueError("distance must be 0 or more")
        if not isinstance(crossed, bool):
            raise ValueError("crossed must be a bool")
        if mlib.objExists(name):
            raise ValueError("BeltDrive container already exists: " + name)
        if base is not None:
            base = mlib.Node(base)
            if not isinstance(base, mlib.Transform):
                raise ValueError("base must be a transform")
        with nativeUnits():
            graph = cls(mlib.createContainer(name=name))
            graph._build(base, float(driverRadius), float(drivenRadius), float(distance), crossed)
        return graph

    def _build(self, base, driverRadius, drivenRadius, distance, crossed):
        """createの本体(内部単位の中で呼ぶ)。

        Args:
            base (Node | None): 土台のtransform。
            driverRadius (float): 駆動プーリーの半径(cm)。
            drivenRadius (float): 従動プーリーの半径(cm)。
            distance (float): 軸間距離の初期値(cm)。
            crossed (bool): 十字掛けならTrue。
        """
        owner = self.container
        scalar = ScalarGraph(owner)
        owner.addAttr(longName="rotation", attributeType="doubleAngle", defaultValue=0.0, keyable=True)
        for attribute, value in (("driverRadius", driverRadius), ("drivenRadius", drivenRadius)):
            owner.addAttr(longName=attribute, attributeType="doubleLinear", defaultValue=value, minValue=1e-4,
                          keyable=True)
        owner.addAttr(longName="distance", attributeType="doubleLinear", defaultValue=distance, keyable=True)
        owner.addAttr(longName="crossed", attributeType="bool", defaultValue=crossed, keyable=True)
        lengths = ["clampedDistance", "excess", "spanLength", "beltLength", "travel"]
        angles = ["tangentAngle", "driverWrap", "drivenWrap", "drivenRotation"]
        matrices = ["driverMatrix", "drivenMatrix", "upperSpanMatrix", "lowerSpanMatrix"]
        for attribute in lengths:
            owner.addAttr(longName=attribute, attributeType="doubleLinear")
        owner.addAttr(longName="ratio", attributeType="double")
        for attribute in angles:
            owner.addAttr(longName=attribute, attributeType="doubleAngle")
        for attribute in matrices:
            owner.addAttr(longName=attribute, dataType="matrix")
        r1, r2 = owner.getPlug("driverRadius"), owner.getPlug("drivenRadius")

        # sign = 十字掛けなら -1、平行掛けなら +1。k = r1 - sign * r2
        sign = scalar.condition("crossSign", owner.getPlug("crossed"), 0.5, -1.0, 1.0)
        reach = scalar.sum("reach", r1, scalar.multiply("signedDriven", sign, r2), subtract=True)

        # d = max(distance, |k|, 下限)、excess = distance - d
        negative = scalar.multiply("reachNegative", reach, -1.0)
        absolute = scalar.condition("reachAbs", reach, 0.0, reach, negative)
        low = scalar.condition("distanceLow", absolute, _MIN_DISTANCE, absolute, _MIN_DISTANCE)
        scalar.condition("distanceLimit", owner.getPlug("distance"), low, owner.getPlug("distance"), low).connectTo(
            owner.getPlug("clampedDistance"))
        d = owner.getPlug("clampedDistance")
        scalar.sum("excessRaw", owner.getPlug("distance"), d, subtract=True).connectTo(owner.getPlug("excess"))

        # L = sqrt(max(d^2 - k^2, 0))
        rest = scalar.sum("spanSquared", scalar.multiply("distanceSquared", d, d),
                          scalar.multiply("reachSquared", reach, reach), subtract=True)
        floor = self._node("clamp", "spanFloor")
        floor.getPlug("maxR").set(1e30)
        rest.connectTo(floor.getPlug("inputR"))
        scalar.multiply("spanRoot", floor.getPlug("outputR"), 0.5, operation=3).connectTo(owner.getPlug("spanLength"))
        span = owner.getPlug("spanLength")

        # 上の直線部の向き (L, -k) の、+X からの符号付きの角度 = θ - 90度(-90〜90度)。
        turn = self._node("angleBetween", "spanRotation")
        turn.getPlug("vector1").set((1.0, 0.0, 0.0))
        span.connectTo(turn.getPlug("vector2X"))
        negative.connectTo(turn.getPlug("vector2Y"))
        turn.getPlug("vector2Z").set(0.0)
        upper = turn.getPlug("eulerZ")

        def blend(role, source, weight, offset, target=None):
            # weight * source + offset(radian)の角度。weightは数値かplug。
            node = self._node("animBlendNodeAdditiveDA", role)
            source.connectTo(node.getPlug("inputA"))
            if isinstance(weight, float):
                node.getPlug("weightA").set(weight)
            else:
                weight.connectTo(node.getPlug("weightA"))
            node.getPlug("inputB").set(offset, unit="rad")
            node.getPlug("weightB").set(1.0)
            if target is not None:
                node.getPlug("output").connectTo(owner.getPlug(target))
            return node.getPlug("output")

        # θ = 向き + 90度、駆動側の巻き付け = 360度 - 2θ、従動側 = 180度 + sign * (2θ - 180度)
        blend("tangentAngleOffset", upper, 1.0, math.pi / 2.0, "tangentAngle")
        blend("driverWrapOffset", upper, -2.0, math.pi, "driverWrap")
        blend("drivenWrapOffset", upper, scalar.multiply("signDouble", sign, 2.0), math.pi, "drivenWrap")
        lower = blend("lowerSpanRotation", upper, -1.0, 0.0)

        # 回転の比 = sign * r1 / r2、従動プーリーの回転 = 比 * rotation、ベルトの送り = r1 * rotation(radian)
        scalar.multiply("ratioRaw", scalar.multiply("signedDriver", sign, r1), r2, operation=2).connectTo(
            owner.getPlug("ratio"))
        blend("drivenRotationBlend", owner.getPlug("rotation"), owner.getPlug("ratio"), 0.0, "drivenRotation")
        scalar.multiply("travelRaw", owner.getPlug("rotation"), r1).connectTo(owner.getPlug("travel"))

        # ベルトの長さ = 2L + r1 * 駆動側の巻き付け + r2 * 従動側の巻き付け(radian)
        arcs = scalar.sum("wrapLength", scalar.multiply("driverArc", owner.getPlug("driverWrap"), r1),
                          scalar.multiply("drivenArc", owner.getPlug("drivenWrap"), r2))
        scalar.sum("beltLengthRaw", scalar.multiply("spanDouble", span, 2.0), arcs).connectTo(
            owner.getPlug("beltLength"))

        # 駆動側の接点 = r1 * (k / d, ±L / d)
        contactX = scalar.multiply("contactX", scalar.multiply("contactCos", reach, d, operation=2), r1)
        contactY = scalar.multiply("contactY", scalar.multiply("contactSin", span, d, operation=2), r1)
        contactLow = scalar.multiply("contactYNegative", contactY, -1.0)

        def place(role, rotation, x=None, y=None):
            # R_z(rotation)・T(x, y, 0)・土台のworldMatrix を出力へ。
            local = self._node("composeMatrix", role + "Local")
            rotation.connectTo(local.getPlug("inputRotateZ"))
            if x is not None:
                x.connectTo(local.getPlug("inputTranslateX"))
            if y is not None:
                y.connectTo(local.getPlug("inputTranslateY"))
            target = owner.getPlug(role + "Matrix")
            if base is None:
                local.getPlug("outputMatrix").connectTo(target)
                return
            world = self._node("multMatrix", role + "World")
            local.getPlug("outputMatrix").connectTo(world.getPlug("matrixIn")[0])
            base.getPlug("worldMatrix")[0].connectTo(world.getPlug("matrixIn")[1])
            world.getPlug("matrixSum").connectTo(target)

        place("driver", owner.getPlug("rotation"))
        place("driven", owner.getPlug("drivenRotation"), x=d)
        place("upperSpan", upper, x=contactX, y=contactY)
        place("lowerSpan", lower, x=contactX, y=contactLow)
        owner.setAttrFlags(lengths + ["ratio"] + angles + matrices, keyable=False)
