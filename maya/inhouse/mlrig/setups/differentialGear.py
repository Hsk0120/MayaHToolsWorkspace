"""デフケースと左右のサイドギヤの回転を平均の関係で連動させ、十字軸のピニオンを自転させる差動歯車の標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution

#: 3つの部材。このうち1つを ``driven`` (求める側)にし、残りの2つを入力(None なら固定)にする。
MEMBERS = ("left", "right", "case")

#: 軸の名前とマトリクスの行の番号。
_AXES = {"x": 0, "y": 1, "z": 2}


def _coefficients(driven):
    """2つの入力の変化に対する、各部材と ``sideSpin`` (ΔL - ΔC)の変化の係数を返す。

    Args:
        driven (str): 求める部材(``MEMBERS``)。

    Returns:
        dict: ``left`` ・ ``right`` ・ ``case`` ・ ``sideSpin`` をキーに、 ``{入力の部材: 係数}`` の辞書。
    """
    if driven == "case":
        result = {"left": {"left": 1.0}, "right": {"right": 1.0}, "case": {"left": 0.5, "right": 0.5}}
    elif driven == "left":
        result = {"right": {"right": 1.0}, "case": {"case": 1.0}, "left": {"case": 2.0, "right": -1.0}}
    else:
        result = {"left": {"left": 1.0}, "case": {"case": 1.0}, "right": {"case": 2.0, "left": -1.0}}
    spin = {}
    for terms, factor in ((result["left"], 1.0), (result["case"], -1.0)):
        for key, value in terms.items():
            spin[key] = spin.get(key, 0.0) + value * factor
    result["sideSpin"] = spin
    return result


def _row(matrix, index):
    """マトリクスの行(軸の向き、または index = 3 で位置)を3つの数で返す。"""
    return [matrix[index * 4 + column] for column in range(3)]


def _dot(a, b):
    """3次元の内積。"""
    return sum(x * y for x, y in zip(a, b))


class DifferentialGear(TwistDistribution):
    """左右のサイドギヤ・デフケースのうち2つの回転から残り1つを求め、十字軸のピニオン(スパイダー)を自転させる差動歯車。

    左右のサイドギヤは同じ歯数で、ケースから見ると逆向きに同じ量だけ回る。このため ``ΔL + ΔR = 2 ΔC`` (ケースは左右の
    平均)になる。スパイダーのケースに対する自転は ``±(Zs / Zp)(ΔL - ΔC)`` で、符号は生成時のスパイダーの位置と軸の向きから
    決める。どれも角度の1次式なので、角度のまま足す標準ノードだけで組み、フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def motion(cls, left, right, case, sideTeeth, spiderTeeth, driven="case"):
        """生成時からの各部材の回転の変化を計算する(DGと同じ式のPython版)。

        Args:
            left (float): 左のサイドギヤの回転の変化。driven が ``"left"`` なら使わない。
            right (float): 右のサイドギヤの回転の変化。driven が ``"right"`` なら使わない。
            case (float): デフケースの回転の変化。driven が ``"case"`` なら使わない。
            sideTeeth (float): サイドギヤの歯数 Zs。
            spiderTeeth (float): スパイダーの歯数 Zp。
            driven (str): 求める部材(``MEMBERS``)。

        Returns:
            dict: ``left`` ・ ``right`` ・ ``case`` (各部材の回転の変化)、``sideSpin`` (左のサイドギヤのケースに対する
            回転 ΔL - ΔC。右は符号が逆)、``spiderSpin`` (スパイダーのケースに対する自転の大きさ (Zs / Zp) sideSpin。
            各スパイダーには生成時の向きで決まる符号を掛ける)。単位は入力と同じ。
        """
        inputs = {"left": left, "right": right, "case": case}
        result = {key: sum(inputs[member] * weight for member, weight in terms.items())
                  for key, terms in _coefficients(driven).items()}
        result["spiderSpin"] = result["sideSpin"] * float(sideTeeth) / float(spiderTeeth)
        return result

    @classmethod
    def spiderSign(cls, case, side, spider, axis="x", spiderAxis="y", sideIsLeft=True):
        """スパイダーの自転の符号(+1 か -1)を、現在のワールドの位置と軸の向きから求める。

        Args:
            case (str | Node): デフケースのtransform。ローカルの axis が車軸。
            side (str | Node): 左(sideIsLeft=True)または右のサイドギヤのtransform。位置で側を決める。
            spider (str | Node): スパイダーのtransform。ローカルの spiderAxis が十字軸。
            axis (str): ケースとサイドギヤの回転軸 x/y/z。
            spiderAxis (str): スパイダーの回転軸 x/y/z。
            sideIsLeft (bool): side が左のサイドギヤならTrue。

        Returns:
            float: ``spiderRotate = 生成時の値 + 符号 × spiderSpin`` の符号。

        Raises:
            ValueError: サイドギヤが車軸の方向にずれていない場合、スパイダーが車軸の上にある場合、または
                スパイダーの軸が車軸からスパイダーへ向かう放射方向に沿っていない場合。
        """
        matrices = [Matrix(mlib.Node(node).getPlug("worldMatrix")[0].get()) for node in (case, side, spider)]
        axle = _row(matrices[0], _AXES[axis])
        length = math.sqrt(_dot(axle, axle))
        axle = [value / length for value in axle]
        origin, sideCenter, spiderCenter = (_row(matrix, 3) for matrix in matrices)
        offset = _dot(axle, [a - b for a, b in zip(sideCenter, spiderCenter)])
        if abs(offset) < 1e-6:
            raise ValueError("The side gear must be offset from the spider along the axle")
        relative = [a - b for a, b in zip(spiderCenter, origin)]
        along = _dot(relative, axle)
        radial = [value - along * direction for value, direction in zip(relative, axle)]
        distance = math.sqrt(_dot(radial, radial))
        if distance < 1e-6:
            raise ValueError("The spider must be off the axle: " + mlib.Node(spider).getFullName())
        pin = _row(matrices[2], _AXES[spiderAxis])
        cosine = _dot(pin, radial) / (distance * math.sqrt(_dot(pin, pin)))
        if abs(cosine) < 0.5:
            raise ValueError("The spider axis must point along the cross pin (toward the axle): "
                             + mlib.Node(spider).getFullName())
        sign = -math.copysign(1.0, offset) * math.copysign(1.0, cosine)
        return sign if sideIsLeft else -sign

    @classmethod
    @undoTransaction("mlrig.DifferentialGear.create")
    def create(cls, left, right, case, spiders=(), sideTeeth=16, spiderTeeth=10, driven="case",
               name="differentialGear", axis="x", spiderAxis="y", connect=True):
        """2つの部材の回転に連動して、残りの部材とスパイダーの回転を生成する。

        Args:
            left (str | Node | None): 左のサイドギヤ(左の車輪・車軸)のtransform。入力なら None で固定(回らない)とする。
            right (str | Node | None): 右のサイドギヤのtransform。入力なら None で固定とする。
            case (str | Node | None): デフケース(リングギヤと一緒に回る、十字軸を持つ箱)のtransform。入力なら None で
                固定とする。
            spiders (Sequence[str | Node]): ピニオン(スパイダー)のtransform(0個以上)。ケースの子に置き、ローカルの
                ``rotate<spiderAxis>`` を動かす。軸は車軸からスパイダーへ向かう向き(十字軸)に沿わせる。
            sideTeeth (float): サイドギヤの歯数 Zs (0より大きい。左右同じ)。生成時に固定する。
            spiderTeeth (float): スパイダーの歯数 Zp (0より大きい)。生成時に固定する。
            driven (str): 求める部材 ``"left"`` ・ ``"right"`` ・ ``"case"`` 。None の部材はここに指定すると出力だけを作る。
            name (str): 一意なcontainer名。
            axis (str): 左右のサイドギヤとケースのローカルの回転軸(車軸) x/y/z。
            spiderAxis (str): スパイダーのローカルの回転軸(十字軸) x/y/z。
            connect (bool): Trueなら driven の部材とスパイダーの回転へ出力を接続する。

        Returns:
            DifferentialGear: drivenRotate・leftAngle・rightAngle・caseAngle・sideSpin・spiderSpin・
                spiderRotate<i> の所有者。containerに固定の sideTeeth・spiderTeeth と、各スパイダーの符号
                spiderSign<i> を持つ。

        Raises:
            ValueError: 軸・driven・歯数が不正な場合、入力が両方 None の場合、transformでない・重複する場合、
                スパイダーがあるのにケースか左右のどちらも無い場合、スパイダーの位置・軸が十字軸に合わない場合、
                出力先のチャンネルが既に接続されている場合(connect=True)、またはnameが既に存在する場合。

        Note:
            各入力の変化 Δ = rotate<axis> - 生成時の値(None は 0)。
            driven = case: ΔC = (ΔL + ΔR) / 2、driven = left: ΔL = 2 ΔC - ΔR、driven = right: ΔR = 2 ΔC - ΔL。
            sideSpin = ΔL - ΔC (右のサイドギヤのケースに対する回転は -sideSpin)、spiderSpin = (Zs / Zp) sideSpin。
            drivenRotate = 生成時の driven の rotate<axis> + Δ(driven)、
            spiderRotate<i> = 生成時のスパイダーの rotate<spiderAxis> + spiderSign<i> × spiderSpin。
            spiderSign は :meth:`spiderSign` で生成時に決める。生成時は変化が0なので、接続しても跳ねない。
        """
        if axis not in _AXES or spiderAxis not in _AXES:
            raise ValueError("axis and spiderAxis must be x, y or z")
        if driven not in MEMBERS:
            raise ValueError("driven must be left, right or case")
        numbers = (sideTeeth, spiderTeeth)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numbers):
            raise ValueError("sideTeeth and spiderTeeth must be numbers")
        if sideTeeth <= 0.0 or spiderTeeth <= 0.0:
            raise ValueError("sideTeeth and spiderTeeth must be more than 0")
        members = {"left": left, "right": right, "case": case}
        inputs = [member for member in MEMBERS if member != driven]
        if all(members[member] is None for member in inputs):
            raise ValueError("At least one input member is required: " + " or ".join(inputs))
        if mlib.objExists(name):
            raise ValueError("DifferentialGear container already exists: " + name)
        nodes = {key: mlib.Node(value) for key, value in members.items() if value is not None}
        spiders = [mlib.Node(spider) for spider in spiders]
        every = list(nodes.values()) + spiders
        if not all(isinstance(node, mlib.Transform) for node in every):
            raise ValueError("Expected transforms for the gears and the case")
        if len({node.getFullName() for node in every}) != len(every):
            raise ValueError("The gears and the case must be different nodes")
        signs = []
        if spiders:
            sides = [key for key in ("left", "right") if key in nodes]
            if "case" not in nodes or not sides:
                raise ValueError("The case and a side gear are required to orient the spiders")
            signs = [cls.spiderSign(nodes["case"], nodes[sides[0]], spider, axis, spiderAxis,
                                    sideIsLeft=sides[0] == "left") for spider in spiders]
        channel = "rotate" + axis.upper()
        spiderChannel = "rotate" + spiderAxis.upper()
        if connect:
            targets = [(spider, spiderChannel) for spider in spiders]
            targets += [(nodes[driven], channel)] if driven in nodes else []
            for target, attribute in targets:
                if target.getPlug(attribute).getConnections(input=True, skipConversionNodes=True) is not None:
                    raise ValueError("The rotation is already connected: " + target.getFullName())

        zs, zp = float(sideTeeth), float(spiderTeeth)
        coefficients = _coefficients(driven)
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        constants = [("sideTeeth", zs), ("spiderTeeth", zp)]
        constants += [("spiderSign" + str(index), sign) for index, sign in enumerate(signs)]
        for attribute, value in constants:
            owner.addAttr(longName=attribute, attributeType="double")
            owner.getPlug(attribute).set(value)
        outputs = ["drivenRotate", "leftAngle", "rightAngle", "caseAngle", "sideSpin", "spiderSpin"]
        outputs += ["spiderRotate" + str(index) for index in range(len(spiders))]
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
        sideSpin = combination("sideSpin", "sideSpin")
        sideSpin.connectTo(owner.getPlug("sideSpin"))
        spiderSpin = total("spiderSpin", [(sideSpin, zs / zp)])
        spiderSpin.connectTo(owner.getPlug("spiderSpin"))
        rest = nodes[driven].getPlug(channel).get(unit="rad") if driven in nodes else 0.0
        combination("drivenRotate", driven, rest).connectTo(owner.getPlug("drivenRotate"))
        for index, (spider, sign) in enumerate(zip(spiders, signs)):
            attribute = "spiderRotate" + str(index)
            start = spider.getPlug(spiderChannel).get(unit="rad")
            total(attribute, [(spiderSpin, sign)], start).connectTo(owner.getPlug(attribute))
        if connect:
            if driven in nodes:
                owner.getPlug("drivenRotate").connectTo(nodes[driven].getPlug(channel))
            for index, spider in enumerate(spiders):
                owner.getPlug("spiderRotate" + str(index)).connectTo(spider.getPlug(spiderChannel))
        owner.setAttrFlags(outputs + [attribute for attribute, _ in constants], keyable=False, channelBox=True)
        return graph
