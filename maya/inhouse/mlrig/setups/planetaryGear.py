"""太陽歯車・内歯車・キャリアと遊星歯車の回転を、Willisの式で連動させる遊星歯車機構の標準DGを構築する。"""

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

#: 3つの部材。このうち1つを ``driven`` (求める側)にし、残りの2つを入力(None なら固定)にする。
MEMBERS = ("sun", "ring", "carrier")


def _coefficients(sunTeeth, planetTeeth, driven):
    """2つの入力の変化に対する、各部材と遊星歯車の変化の係数を返す。

    Args:
        sunTeeth (float): 太陽歯車の歯数 Zs。
        planetTeeth (float): 遊星歯車の歯数 Zp。
        driven (str): 求める部材(``MEMBERS``)。

    Returns:
        dict: ``sun`` ・ ``ring`` ・ ``carrier`` ・ ``planetSpin`` ・ ``planetAngle`` をキーに、
        ``{入力の部材: 係数}`` の辞書。
    """
    zs, zp = float(sunTeeth), float(planetTeeth)
    zr = zs + 2.0 * zp
    total = zs + zr
    if driven == "carrier":
        result = {"sun": {"sun": 1.0}, "ring": {"ring": 1.0}, "carrier": {"sun": zs / total, "ring": zr / total}}
    elif driven == "ring":
        result = {"sun": {"sun": 1.0}, "carrier": {"carrier": 1.0}, "ring": {"carrier": total / zr, "sun": -zs / zr}}
    else:
        result = {"ring": {"ring": 1.0}, "carrier": {"carrier": 1.0}, "sun": {"carrier": total / zs, "ring": -zr / zs}}

    def combine(*pairs):
        """(係数の辞書, 倍率) の和。"""
        merged = {}
        for terms, factor in pairs:
            for key, value in terms.items():
                merged[key] = merged.get(key, 0.0) + value * factor
        return merged

    # 遊星歯車のキャリアに対する自転: θp - θc = -(Zs / Zp)(θs - θc)
    result["planetSpin"] = combine((result["sun"], -zs / zp), (result["carrier"], zs / zp))
    result["planetAngle"] = combine((result["planetSpin"], 1.0), (result["carrier"], 1.0))
    return result


class PlanetaryGear(TwistDistribution):
    """太陽歯車・内歯車(リング)・キャリアのうち2つの回転から、残り1つの回転と遊星歯車の自転を求める遊星歯車機構。

    内歯車の歯数は同心のかみ合いの条件 ``Zr = Zs + 2 Zp`` で決まる。Willisの式 ``Zs θs + Zr θr = (Zs + Zr) θc`` で
    3つの部材の回転を結び、遊星歯車のキャリアに対する自転を ``-(Zs / Zp)(θs - θc)`` で求める。どれも角度の1次式なので、
    角度のまま足す標準ノードだけで組み、フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def ringTeeth(cls, sunTeeth, planetTeeth):
        """同心にかみ合う内歯車の歯数 ``Zs + 2 Zp`` を返す。

        Args:
            sunTeeth (float): 太陽歯車の歯数。
            planetTeeth (float): 遊星歯車の歯数。

        Returns:
            float: 内歯車の歯数。
        """
        return float(sunTeeth) + 2.0 * float(planetTeeth)

    @classmethod
    def canSpaceEvenly(cls, sunTeeth, planetTeeth, count):
        """遊星歯車 count 個を等間隔に置いて、太陽歯車と内歯車の両方へかみ合わせられるかを返す。

        Args:
            sunTeeth (int): 太陽歯車の歯数。
            planetTeeth (int): 遊星歯車の歯数。
            count (int): 遊星歯車の数(1以上)。

        Returns:
            bool: ``Zs + Zr`` が count で割り切れるならTrue。

        Raises:
            ValueError: 歯数・数が正の整数でない場合。
        """
        values = (sunTeeth, planetTeeth, count)
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in values):
            raise ValueError("sunTeeth, planetTeeth and count must be positive integers")
        return (2 * sunTeeth + 2 * planetTeeth) % count == 0

    @classmethod
    def motion(cls, sun, ring, carrier, sunTeeth, planetTeeth, driven="carrier"):
        """生成時からの各部材の回転の変化を計算する(DGと同じ式のPython版)。

        Args:
            sun (float): 太陽歯車の回転の変化。driven が ``"sun"`` なら使わない。
            ring (float): 内歯車の回転の変化。driven が ``"ring"`` なら使わない。
            carrier (float): キャリアの回転の変化。driven が ``"carrier"`` なら使わない。
            sunTeeth (float): 太陽歯車の歯数 Zs。
            planetTeeth (float): 遊星歯車の歯数 Zp。
            driven (str): 求める部材(``MEMBERS``)。

        Returns:
            dict: ``sun`` ・ ``ring`` ・ ``carrier`` (各部材の回転の変化)、``planetSpin`` (遊星歯車のキャリアに対する
            自転)、``planetAngle`` (遊星歯車の固定した空間での自転 = carrier + planetSpin)。単位は入力と同じ。
        """
        inputs = {"sun": sun, "ring": ring, "carrier": carrier}
        coefficients = _coefficients(sunTeeth, planetTeeth, driven)
        return {key: sum(inputs[member] * weight for member, weight in terms.items())
                for key, terms in coefficients.items()}

    @classmethod
    @undoTransaction("mlrig.PlanetaryGear.create")
    def create(cls, sun, ring, carrier, planets=(), sunTeeth=24, planetTeeth=12, driven="carrier",
               name="planetaryGear", axis="z", followCarrier=True, connect=True):
        """2つの部材の回転に連動して、残りの部材と遊星歯車の回転を生成する。

        Args:
            sun (str | Node | None): 太陽歯車のtransform。入力なら None で固定(回らない)とする。
            ring (str | Node | None): 内歯車のtransform。入力なら None で固定とする。
            carrier (str | Node | None): キャリア(遊星歯車の軸を持つ腕)のtransform。入力なら None で固定とする。
            planets (Sequence[str | Node]): 遊星歯車のtransform(0個以上)。ローカルの ``rotate<axis>`` を動かす。
            sunTeeth (float): 太陽歯車の歯数 Zs (0より大きい)。生成時に固定する。
            planetTeeth (float): 遊星歯車の歯数 Zp (0より大きい)。内歯車は ``Zs + 2 Zp`` 。生成時に固定する。
            driven (str): 求める部材 ``"sun"`` ・ ``"ring"`` ・ ``"carrier"`` 。None の部材はここに指定すると出力だけを作る。
            name (str): 一意なcontainer名。
            axis (str): 全ての歯車とキャリアのローカルの回転軸 x/y/z。
            followCarrier (bool): Trueなら遊星歯車はキャリアの子(キャリアと一緒に回る空間)とし、キャリアに対する自転を
                書く。Falseならキャリアと一緒に回らない空間とし、固定した空間での自転(キャリアの回転を足した値)を書く。
            connect (bool): Trueなら driven の部材と遊星歯車の ``rotate<axis>`` へ出力を接続する。

        Returns:
            PlanetaryGear: drivenRotate・sunAngle・ringAngle・carrierAngle・planetSpin・planetAngle・planetRotate<i>
                の所有者。containerに固定の sunTeeth・planetTeeth・ringTeeth を持つ。

        Raises:
            ValueError: 軸・driven・歯数が不正な場合、入力が両方 None の場合、transformでない・重複する場合、
                出力先のチャンネルが既に接続されている場合(connect=True)、またはnameが既に存在する場合。

        Note:
            Zr = Zs + 2 Zp。各入力の変化 Δ = rotate<axis> - 生成時の値(None は 0)。
            driven = carrier: Δc = (Zs Δs + Zr Δr) / (Zs + Zr)、driven = ring: Δr = ((Zs + Zr) Δc - Zs Δs) / Zr、
            driven = sun: Δs = ((Zs + Zr) Δc - Zr Δr) / Zs (いずれもWillisの式 Zs (θs - θc) = -Zr (θr - θc))。
            planetSpin = -(Zs / Zp)(Δs - Δc) = (Zr / Zp)(Δr - Δc)、planetAngle = Δc + planetSpin。
            drivenRotate = 生成時の driven の rotate<axis> + Δ(driven)、
            planetRotate<i> = 生成時の遊星歯車の rotate<axis> + (followCarrier なら planetSpin、違えば planetAngle)。
            生成時は変化が0なので、接続しても跳ねない。歯のかみ合わせの見た目は生成時の遊星歯車の角度で合わせる。
        """
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be x, y or z")
        if driven not in MEMBERS:
            raise ValueError("driven must be sun, ring or carrier")
        numbers = (sunTeeth, planetTeeth)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numbers):
            raise ValueError("sunTeeth and planetTeeth must be numbers")
        if sunTeeth <= 0.0 or planetTeeth <= 0.0:
            raise ValueError("sunTeeth and planetTeeth must be more than 0")
        members = {"sun": sun, "ring": ring, "carrier": carrier}
        inputs = [member for member in MEMBERS if member != driven]
        if all(members[member] is None for member in inputs):
            raise ValueError("At least one input member is required: " + " or ".join(inputs))
        if mlib.objExists(name):
            raise ValueError("PlanetaryGear container already exists: " + name)
        nodes = {key: mlib.Node(value) for key, value in members.items() if value is not None}
        planets = [mlib.Node(planet) for planet in planets]
        every = list(nodes.values()) + planets
        if not all(isinstance(node, mlib.Transform) for node in every):
            raise ValueError("Expected transforms for the gears and the carrier")
        if len({node.getName(full=True) for node in every}) != len(every):
            raise ValueError("The gears and the carrier must be different nodes")
        channel = "rotate" + axis.upper()
        targets = list(planets) + ([nodes[driven]] if driven in nodes else [])
        if connect:
            for target in targets:
                if target.getPlug(channel).getConnections(input=True, skipConversionNodes=True) is not None:
                    raise ValueError("The rotation is already connected: " + target.getName(full=True))

        zs, zp = float(sunTeeth), float(planetTeeth)
        coefficients = _coefficients(zs, zp, driven)
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        constants = (("sunTeeth", zs), ("planetTeeth", zp), ("ringTeeth", cls.ringTeeth(zs, zp)))
        for attribute, value in constants:
            owner.addAttr(longName=attribute, attributeType="double")
            owner.getPlug(attribute).set(value)
        outputs = ["drivenRotate", "sunAngle", "ringAngle", "carrierAngle", "planetSpin", "planetAngle"]
        outputs += ["planetRotate" + str(index) for index in range(len(planets))]
        for attribute in outputs:
            owner.addAttr(longName=attribute, attributeType="doubleAngle")

        def total(label, terms, constant=0.0):
            """ラジアンの定数と (角度のPlug, 係数) の和を、角度のまま足す animBlendNodeAdditiveDA の連なりで求める。"""
            current = constant
            terms = [(source, weight) for source, weight in terms if weight != 0.0] or [(None, 0.0)]
            for index, (source, weight) in enumerate(terms):
                node = graph._node("animBlendNodeAdditiveDA", label + str(index))
                if isinstance(current, float):
                    node.getPlug("inputA").set(current, unit="rad")
                else:
                    current.connectTo(node.getPlug("inputA"))
                node.getPlug("weightA").set(1.0)
                if source is not None:
                    source.connectTo(node.getPlug("inputB"))
                node.getPlug("weightB").set(weight)
                current = node.getPlug("output")
            return current

        # 入力の変化 Δ = rotate<axis> - 生成時の値(ラジアンのまま写し、度との往復の丸めを入れない)
        deltas = {}
        for member in inputs:
            if member in nodes:
                plug = nodes[member].getPlug(channel)
                deltas[member] = total(member + "Delta", [(plug, 1.0)], -plug.get(unit="rad"))

        def combination(label, key, constant=0.0):
            """入力の変化の1次結合 + 定数。"""
            terms = [(deltas[member], weight) for member, weight in coefficients[key].items() if member in deltas]
            return total(label, terms, constant)

        for member in MEMBERS:
            combination(member + "Angle", member).connectTo(owner.getPlug(member + "Angle"))
        combination("planetSpin", "planetSpin").connectTo(owner.getPlug("planetSpin"))
        combination("planetAngle", "planetAngle").connectTo(owner.getPlug("planetAngle"))
        rest = nodes[driven].getPlug(channel).get(unit="rad") if driven in nodes else 0.0
        combination("drivenRotate", driven, rest).connectTo(owner.getPlug("drivenRotate"))
        planetKey = "planetSpin" if followCarrier else "planetAngle"
        for index, planet in enumerate(planets):
            attribute = "planetRotate" + str(index)
            combination(attribute, planetKey, planet.getPlug(channel).get(unit="rad")).connectTo(owner.getPlug(attribute))
        if connect:
            if driven in nodes:
                owner.getPlug("drivenRotate").connectTo(nodes[driven].getPlug(channel))
            for index, planet in enumerate(planets):
                owner.getPlug("planetRotate" + str(index)).connectTo(planet.getPlug(channel))
        owner.setAttrFlags(outputs + [attribute for attribute, _ in constants], keyable=False, channelBox=True)
        return graph
