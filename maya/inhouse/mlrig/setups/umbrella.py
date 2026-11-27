"""傘の親骨・受け骨・ランナー(下ろくろ)の行列を、ランナーの位置から求める標準DGを構築する。"""

import math

import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.decorator import nativeUnits, undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

#: ランナーが上の支点へ重なって割り算が0にならないようにする、slideの下限(cm)。
_MIN_SLIDE = 1e-3


class Umbrella(TwistDistribution):
    """中棒を滑るランナーの位置1つで、放射状に並んだ親骨と受け骨を開閉する標準DG。

    土台の空間(土台のtransformのローカル)で、親骨の付け根(上ろくろ)を原点、中棒を -Y(下)の向きとする。
    ランナーは ``(0, -s, 0)`` にあり、親骨は付け根から ``a`` の所で、長さ ``b`` の受け骨とつながる。
    付け根・ランナー・つなぎ目の三角形(辺 ``s`` ・ ``a`` ・ ``b``)から、
    つなぎ目の中棒に沿った深さ ``d = (a^2 + s^2 - b^2) / (2s)`` 、中棒からの距離 ``h = sqrt(a^2 - d^2)`` 、
    親骨の角度 ``φ = atan2(h, d)`` (中棒の下向きから。0で閉じ、90度で水平)、
    受け骨の角度 ``ψ = atan2(h, s - d)`` (中棒の上向きから)を求める。
    ``s`` は三角形ができる範囲 ``|a - b| 〜 a + b`` で止め、超えた量を ``excess`` へ出す。
    フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def evaluate(cls, slide, ribLength, stretcherLength):
        """止めたslide・超えた量・親骨と受け骨の角度・つなぎ目の半径を計算する(DGと同じ式のPython版)。

        Args:
            slide (float): 親骨の付け根からランナーまでの距離。
            ribLength (float): 親骨の付け根から受け骨のつなぎ目までの長さ(slideと同じ単位)。
            stretcherLength (float): 受け骨の長さ。

        Returns:
            tuple[float, float, float, float, float]: (止めたslide, 超えた量, 親骨の角度(度), 受け骨の角度(度),
            つなぎ目の中棒からの距離)。
        """
        low = max(abs(ribLength - stretcherLength), _MIN_SLIDE)
        clamped = min(max(slide, low), ribLength + stretcherLength)
        depth = (ribLength * ribLength + clamped * clamped - stretcherLength * stretcherLength) / (2.0 * clamped)
        radius = math.sqrt(max(ribLength * ribLength - depth * depth, 0.0))
        rib = math.degrees(math.atan2(radius, depth))
        stretcher = math.degrees(math.atan2(radius, clamped - depth))
        return clamped, slide - clamped, rib, stretcher, radius

    @classmethod
    @undoTransaction("mlrig.Umbrella.create")
    def create(cls, base=None, count=8, ribLength=4.0, stretcherLength=5.0, slide=None, startAngle=0.0,
               name="umbrella"):
        """傘の骨の計算containerを作る。

        Args:
            base (str | Node | None): 土台のtransform(親骨の付け根。-Yが中棒の下向き)。
                出力の行列はこのworldMatrixに追従する。Noneならワールド原点。
            count (int): 親骨の本数(1〜64)。中棒のまわりに等間隔で並べる。
            ribLength (float): 親骨の付け根から受け骨のつなぎ目までの長さ(cm、0より大きい)。
            stretcherLength (float): 受け骨の長さ(cm、0より大きい)。ribLengthより長いと、親骨が水平を超えて開ける。
                短いと、親骨は ``asin(stretcherLength / ribLength)`` までしか開かない。
            slide (float | None): 付け根からランナーまでの距離の初期値(cm、0以上)。
                Noneなら ``ribLength + stretcherLength`` (閉じた状態)。
            startAngle (float): 0本目の親骨の、中棒まわりの向き(度)。0で土台の+X、正で+Xから-Zへ回る。
            name (str): 一意なcontainer名。

        Returns:
            Umbrella: containerに slide・ribLength・stretcherLength(keyable)と、clampedSlide・excess・radius・
                ribAngle・stretcherAngle、``runnerMatrix`` (ランナー)、``rib<k>Matrix`` (付け根を原点、X=親骨の向き)、
                ``stretcher<k>Matrix`` (ランナーを原点、X=受け骨の向き)のワールド行列を持つ。

        Raises:
            ValueError: 本数・長さ・slide・startAngleが不正な場合、baseがtransformでない場合、
                またはnameが既に存在する場合。

        Note:
            全体を内部単位(cm・radian)で組むので、UI単位を変えても自動の unitConversion は入らない。
            slideを小さくする(ランナーを押し上げる)ほど開く。
            親骨・受け骨の行列のZは開閉の蝶番の向き(中棒まわりの接線)で、Yは蝶番とXに垂直。
            計算ノードは単精度なので、閉じきる端の近くでは角度に0.1度程度の誤差が出ることがある。
        """
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 64:
            raise ValueError("count must be an integer between 1 and 64")
        for label, value in (("ribLength", ribLength), ("stretcherLength", stretcherLength)):
            if not math.isfinite(float(value)) or value <= 0.0:
                raise ValueError(label + " must be greater than 0")
        if slide is None:
            slide = ribLength + stretcherLength
        if not math.isfinite(float(slide)) or slide < 0.0:
            raise ValueError("slide must be 0 or more")
        if not math.isfinite(float(startAngle)):
            raise ValueError("startAngle must be finite")
        if mlib.objExists(name):
            raise ValueError("Umbrella container already exists: " + name)
        if base is not None:
            base = mlib.Node(base)
            if not isinstance(base, mlib.Transform):
                raise ValueError("base must be a transform")
        with nativeUnits():
            graph = cls(mlib.createContainer(name=name))
            graph._build(base, count, float(ribLength), float(stretcherLength), float(slide), float(startAngle))
        return graph

    def _build(self, base, count, ribLength, stretcherLength, slide, startAngle):
        """createの本体(内部単位の中で呼ぶ)。

        Args:
            base (Node | None): 土台のtransform。
            count (int): 親骨の本数。
            ribLength (float): 親骨の付け根からつなぎ目までの長さ(cm)。
            stretcherLength (float): 受け骨の長さ(cm)。
            slide (float): 付け根からランナーまでの距離の初期値(cm)。
            startAngle (float): 0本目の親骨の向き(度)。
        """
        owner = self.container
        scalar = ScalarGraph(owner)
        owner.addAttr(longName="slide", attributeType="doubleLinear", defaultValue=slide, keyable=True)
        for attribute, value in (("ribLength", ribLength), ("stretcherLength", stretcherLength)):
            owner.addAttr(longName=attribute, attributeType="doubleLinear", defaultValue=value, minValue=1e-4,
                          keyable=True)
        for attribute in ("clampedSlide", "excess", "radius"):
            owner.addAttr(longName=attribute, attributeType="doubleLinear")
        for attribute in ("ribAngle", "stretcherAngle"):
            owner.addAttr(longName=attribute, attributeType="doubleAngle")
        matrices = ["runnerMatrix"]
        matrices += ["rib%dMatrix" % index for index in range(count)]
        matrices += ["stretcher%dMatrix" % index for index in range(count)]
        for attribute in matrices:
            owner.addAttr(longName=attribute, dataType="matrix")
        a, b = owner.getPlug("ribLength"), owner.getPlug("stretcherLength")

        # s = clamp(slide, max(|a - b|, 下限), a + b)、excess = slide - s
        difference = scalar.sum("lengthDifference", a, b, subtract=True)
        negative = scalar.multiply("lengthDifferenceNegative", difference, -1.0)
        absolute = scalar.condition("lengthDifferenceAbs", difference, 0.0, difference, negative)
        low = scalar.condition("slideLow", absolute, _MIN_SLIDE, absolute, _MIN_SLIDE)
        limit = self._node("clamp", "slideLimit")
        owner.getPlug("slide").connectTo(limit.getPlug("inputR"))
        low.connectTo(limit.getPlug("minR"))
        scalar.sum("slideHigh", a, b).connectTo(limit.getPlug("maxR"))
        limit.getPlug("outputR").connectTo(owner.getPlug("clampedSlide"))
        s = owner.getPlug("clampedSlide")
        scalar.sum("excessRaw", owner.getPlug("slide"), s, subtract=True).connectTo(owner.getPlug("excess"))

        # d = (a^2 + s^2 - b^2) / (2s)、h = sqrt(max(a^2 - d^2, 0))
        a2 = scalar.multiply("ribSquared", a, a)
        b2 = scalar.multiply("stretcherSquared", b, b)
        s2 = scalar.multiply("slideSquared", s, s)
        numerator = scalar.sum("depthNumerator", scalar.sum("ribPlusSlide", a2, s2), b2, subtract=True)
        depth = scalar.multiply("depth", scalar.multiply("depthHalf", numerator, 0.5), s, operation=2)
        rest = scalar.sum("radiusSquared", a2, scalar.multiply("depthSquared", depth, depth), subtract=True)
        floor = self._node("clamp", "radiusFloor")
        floor.getPlug("maxR").set(1e30)
        rest.connectTo(floor.getPlug("inputR"))
        scalar.multiply("radiusRoot", floor.getPlug("outputR"), 0.5, operation=3).connectTo(owner.getPlug("radius"))
        h = owner.getPlug("radius")
        up = scalar.sum("stretcherRise", s, depth, subtract=True)
        down = scalar.multiply("depthNegative", depth, -1.0)
        runner = scalar.multiply("slideNegative", s, -1.0)

        def direction(role, y):
            # 開閉の面(X=中棒から外、Y=上)で、+X から (h, y) への符号付きの角度。
            node = self._node("angleBetween", role)
            node.getPlug("vector1").set((1.0, 0.0, 0.0))
            h.connectTo(node.getPlug("vector2X"))
            y.connectTo(node.getPlug("vector2Y"))
            node.getPlug("vector2Z").set(0.0)
            return node.getPlug("eulerZ")

        def offset(role, source, weight, target):
            # target = weight * source + 90度。
            node = self._node("animBlendNodeAdditiveDA", role)
            source.connectTo(node.getPlug("inputA"))
            node.getPlug("weightA").set(weight)
            node.getPlug("inputB").set(math.pi / 2.0, unit="rad")
            node.getPlug("weightB").set(1.0)
            node.getPlug("output").connectTo(owner.getPlug(target))

        # 親骨の向き (h, -d) は φ - 90度、受け骨の向き (h, s - d) は 90度 - ψ。
        ribRotation = direction("ribRotation", down)
        stretcherRotation = direction("stretcherRotation", up)
        offset("ribAngleOffset", ribRotation, 1.0, "ribAngle")
        offset("stretcherAngleOffset", stretcherRotation, -1.0, "stretcherAngle")

        def place(role, rotation=None, azimuth=0.0, slide=False):
            # R_z(rotation)・R_y(azimuth)・T(0, slide ? -s : 0, 0)・土台のworldMatrix を出力へ。
            local = self._node("composeMatrix", role + "Local")
            if rotation is not None:
                local.getPlug("inputRotateOrder").set(5)
                local.getPlug("inputRotateY").set(azimuth, unit="rad")
                rotation.connectTo(local.getPlug("inputRotateZ"))
            if slide:
                runner.connectTo(local.getPlug("inputTranslateY"))
            target = owner.getPlug(role + "Matrix")
            if base is None:
                local.getPlug("outputMatrix").connectTo(target)
                return
            world = self._node("multMatrix", role + "World")
            local.getPlug("outputMatrix").connectTo(world.getPlug("matrixIn")[0])
            base.getPlug("worldMatrix")[0].connectTo(world.getPlug("matrixIn")[1])
            world.getPlug("matrixSum").connectTo(target)

        place("runner", slide=True)
        for index in range(count):
            azimuth = math.radians(startAngle) + 2.0 * math.pi * index / count
            place("rib%d" % index, ribRotation, azimuth)
            place("stretcher%d" % index, stretcherRotation, azimuth, slide=True)
        owner.setAttrFlags(["clampedSlide", "excess", "radius", "ribAngle", "stretcherAngle"] + matrices,
                           keyable=False)

    def getCount(self):
        """親骨の本数を返す。

        Returns:
            int: containerにある親骨の行列の数。
        """
        count = 0
        while self.container.hasAttr("rib%d" % count + "Matrix"):
            count += 1
        return count
