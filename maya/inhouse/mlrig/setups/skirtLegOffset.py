"""脚の動きに合わせて、スカート・腰布の根元の骨を脚から離れる向きへ自動で開く標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.twistDistribution import TwistDistribution

#: 骨の向きの指定に使える軸。
AXES = ("x", "y", "z", "-x", "-y", "-z")


class SkirtLegOffset(TwistDistribution):
    """脚(股関節→膝)がスカートの骨に近づくと、その骨を外側へ回して脚へめり込まないようにする補助骨のDG。

    スカートの骨ごとに、骨の向き s と、腰の中心から骨の位置へ向かう向きから「骨が外へ開く面」を決める。
    脚の向きをその面へ写した角度(骨の向きから外側へ測る、度)が ``-clearance`` を超えると、
    超えた分だけ骨を面の中で外側へ回す。脚が面から横へ外れるほど( ``spread`` 度で0)押す量を弱め、
    ``maxAngle`` で頭打ちにし、複数の脚のうち大きい方を使う。揺れ物のシミュレーションや手付けの
    アニメーションは、この開いた姿勢の上に重ねる(めり込んでいない姿勢から計算を始められる)。

    フレームごとのPython・エクスプレッション・独自プラグインは使わない。
    """

    @staticmethod
    def push(planeAngle, lateralAngle, clearance=10.0, maxAngle=80.0, spread=45.0):
        """1本の脚が1つの骨を押す角度を計算する(DGと同じ式のPython版)。

        Args:
            planeAngle (float): 骨の開く面へ写した脚の向きの、骨の向きから外側へ測った角度(度、-180〜180)。
            lateralAngle (float): 脚の向きが骨の開く面から横へ外れた角度(度、0〜90)。
            clearance (float): 脚が骨に届く手前から開き始める角度(度)。大きいほど早く開く。
            maxAngle (float): 開く角度の上限(度)。
            spread (float): 押す量が0になる横への外れの角度(度、正)。

        Returns:
            float: 骨を外側へ回す角度(度、0〜maxAngle)。

        Note:
            push = clamp((planeAngle + clearance) * clamp(1 - |lateralAngle| / spread, 0, 1), 0, maxAngle)。
        """
        falloff = min(max(1.0 - abs(lateralAngle) / spread, 0.0), 1.0)
        return min(max((planeAngle + clearance) * falloff, 0.0), maxAngle)

    @classmethod
    @undoTransaction("mlrig.SkirtLegOffset.create")
    def create(cls, parent, skirts, legs, name="skirtLegOffset", skirtAxis=None, clearance=10.0,
               maxAngle=80.0, spread=45.0, connect=False):
        """スカートの骨ごとに、脚から離れる向きへ開く行列を生成する。

        Args:
            parent (str | Node): 腰(スカートの骨と脚の付け根の共通の親)のtransform。
            skirts (Sequence[str | Node]): スカート・腰布の根元の骨(transform/joint、1個以上)。
            legs (Sequence[tuple[str | Node, str | Node]]): 脚ごとの (付け根, 先) のtransform。
                付け根→先(股関節→膝など)を脚の向きとする。1組以上。
            name (str): 一意なcontainer名。
            skirtAxis (str | None): 骨のローカルで骨が伸びる向きの軸(x/y/z、-付き可)。
                Noneなら各骨の最初の子transformへの向き。
            clearance (float): 脚が骨に届く手前から開き始める角度(度)。
            maxAngle (float): 開く角度の上限(度、0〜180)。
            spread (float): 押す量が0になる、脚が骨の開く面から横へ外れる角度(度、0〜90)。
            connect (bool): Trueなら各骨の ``offsetParentMatrix`` へ ``offsetMatrix<i>`` を接続する。
                骨は parent の直接の子で、offsetParentMatrix が単位行列・未接続であること。

        Returns:
            SkirtLegOffset: 出力の所有者。container に clearance・maxAngle・spread・weight(keyable)、
                骨ごとに angle<i>(度)・offsetMatrix<i>(parent空間の回転の差分)・matrix<i>(parent空間)・
                worldMatrix<i> を持つ。

        Raises:
            ValueError: 軸・角度・骨・脚の指定が不正な場合、骨の向きや開く面が決まらない場合、
                connect の条件を満たさない場合、または nameが既に存在する場合。

        Note:
            生成時の骨の parent 空間の行列 M、骨の向き s、位置 p から、開く面の法線(回転軸) t = normal(s × p)、
            外向き n = t × s を定数として持つ。脚の向き l(parent空間)の成分 (l·t, l·s, l·n) から、
            planeAngle = (0, l·s, l·n) と (0, 1, 0) の角度(l·n の符号付き)、lateralAngle = |90 - (l と t の角度)|
            を求め、:meth:`push` の式で脚ごとの角度を出して最大を取り、weight を掛けて angle<i> とする。
            G = (行 t, s, n, 位置 p の行列)として offsetMatrix = G^-1 · Rx(angle) · G(p を通る t 回りの回転)、
            matrix = M · offsetMatrix、worldMatrix = matrix · parent の worldMatrix。生成時に脚が clearance より
            離れていれば angle は0で、出力は生成時の骨と一致する(跳ねない)。
        """
        if skirtAxis is not None and skirtAxis not in AXES:
            raise ValueError("skirtAxis must be None, x, y, z, -x, -y or -z")
        values = [float(value) for value in (clearance, maxAngle, spread)]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("clearance, maxAngle and spread must be finite")
        clearance, maxAngle, spread = values
        if not 0.0 <= maxAngle <= 180.0:
            raise ValueError("maxAngle must be between 0 and 180")
        if not 0.0 < spread <= 90.0:
            raise ValueError("spread must be greater than 0 and at most 90")
        if mlib.objExists(name):
            raise ValueError("SkirtLegOffset container already exists: " + name)
        skirts = list(skirts)
        legs = [tuple(leg) for leg in legs]
        if not skirts:
            raise ValueError("Expected at least one skirt transform")
        if not legs or any(len(leg) != 2 for leg in legs):
            raise ValueError("legs must be one or more (start, end) pairs")
        parent = mlib.nodes.Node(parent)
        skirts = [mlib.nodes.Node(skirt) for skirt in skirts]
        legs = [tuple(mlib.nodes.Node(node) for node in leg) for leg in legs]
        nodes = [parent] + skirts + [node for leg in legs for node in leg]
        if any(not isinstance(node, mlib.nodes.Transform) for node in nodes):
            raise ValueError("Expected transforms for the parent, the skirts and the legs")
        if len({node.getUuid() for node in [parent] + skirts}) != len(skirts) + 1:
            raise ValueError("The parent and the skirts must be different nodes")
        if any(start == end for start, end in legs):
            raise ValueError("The start and the end of a leg must be different nodes")

        to_parent = Matrix(parent.getPlug("worldMatrix")[0].get()).inverse()
        frames = []
        for skirt in skirts:
            rest = Matrix(skirt.getPlug("worldMatrix")[0].get()) * to_parent
            position = Vector(rest.translate)
            if skirtAxis is None:
                children = [child for child in skirt.getChildren() if isinstance(child, mlib.nodes.Transform)]
                if not children:
                    raise ValueError("The skirt has no child to give its direction: " + skirt.getFullName())
                tip = Matrix(children[0].getPlug("worldMatrix")[0].get()) * to_parent
                direction = Vector(tip.translate) - position
            else:
                sign = -1.0 if skirtAxis.startswith("-") else 1.0
                local = Vector(*[sign * float(axis == skirtAxis[-1]) for axis in ("x", "y", "z")])
                direction = local * rest
            if direction.length() < 1e-6:
                raise ValueError("The direction of the skirt is not defined: " + skirt.getFullName())
            direction = direction.normal()
            hinge = direction ^ position
            if hinge.length() < 1e-6 * max(position.length(), 1.0) or position.length() < 1e-6:
                raise ValueError("The skirt must be away from the parent and not point straight out from it: "
                                 + skirt.getFullName())
            hinge = hinge.normal()
            outward = (hinge ^ direction).normal()
            frames.append((rest, position, hinge, direction, outward))
        if connect:
            for skirt in skirts:
                above = skirt.getParent()
                if above is None or above != parent:
                    raise ValueError("connect requires the skirts to be direct children of the parent: "
                                     + skirt.getFullName())
                plug = skirt.getPlug("offsetParentMatrix")
                if plug.getSource(skipConversionNodes=True) is not None or not Matrix(plug.get()).isEquivalent(Matrix(), 1e-9):
                    raise ValueError("The offsetParentMatrix of the skirt must be identity and unconnected: "
                                     + skirt.getFullName())

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        owner.addAttr(longName="clearance", attributeType="double", defaultValue=clearance, keyable=True)
        owner.addAttr(longName="maxAngle", attributeType="double", defaultValue=maxAngle, keyable=True,
                      minValue=0.0, maxValue=180.0)
        owner.addAttr(longName="spread", attributeType="double", defaultValue=spread, keyable=True,
                      minValue=0.001, maxValue=90.0)
        owner.addAttr(longName="weight", attributeType="double", defaultValue=1.0, keyable=True, minValue=0.0)
        outputs = []
        for index in range(len(skirts)):
            owner.addAttr(longName="angle" + str(index), attributeType="double")
            outputs.append("angle" + str(index))
            for attr in ("offsetMatrix", "matrix", "worldMatrix"):
                owner.addAttr(longName=attr + str(index), dataType="matrix")

        # 脚ごとの向き l = (先 - 付け根)。どちらも parent の空間へ移した位置から求める。
        directions = []
        for leg_index, leg in enumerate(legs):
            points = []
            for role, node in zip(("start", "end"), leg):
                relative = graph._node("multMatrix", "leg{}{}".format(leg_index, role.capitalize()))
                node.getPlug("worldMatrix")[0].connectTo(relative.getPlug("matrixIn")[0])
                parent.getPlug("worldInverseMatrix")[0].connectTo(relative.getPlug("matrixIn")[1])
                location = graph._node("decomposeMatrix", "leg{}{}Point".format(leg_index, role.capitalize()))
                relative.getPlug("matrixSum").connectTo(location.getPlug("inputMatrix"))
                points.append(location.getPlug("outputTranslate"))
            vector = graph._node("plusMinusAverage", "leg{}Direction".format(leg_index))
            vector.getPlug("operation").set(2)
            points[1].connectTo(vector.getPlug("input3D")[0])
            points[0].connectTo(vector.getPlug("input3D")[1])
            directions.append(vector.getPlug("output3D"))

        def degrees(plug, role):
            """angleBetweenの角度を、UIの角度単位によらず度の値へ変換する。"""
            conversion = graph._node("unitConversion", role)
            conversions.add(conversion.getUuid())
            plug.connectTo(conversion.getPlug("input"))
            conversion.getPlug("conversionFactor").set(180.0 / math.pi)
            return conversion.getPlug("output")

        for index, (rest, position, hinge, direction, outward) in enumerate(frames):
            # 列が t・s・n の行列。行ベクトル l に掛けると (l·t, l·s, l·n)。
            components = Matrix([
                hinge.x, direction.x, outward.x, 0.0,
                hinge.y, direction.y, outward.y, 0.0,
                hinge.z, direction.z, outward.z, 0.0,
                0.0, 0.0, 0.0, 1.0,
            ])
            pushes = []
            for leg_index, leg_direction in enumerate(directions):
                role = "skirt{}Leg{}".format(index, leg_index)
                local = graph._node("vectorProduct", role + "Local")
                local.getPlug("operation").set(3)
                local.getPlug("normalizeOutput").set(False)
                leg_direction.connectTo(local.getPlug("input1"))
                local.getPlug("matrix").set(components)

                # planeAngle: 面へ写した脚の向き (0, l·s, l·n) と骨の向き (0, 1, 0) の角度に、l·n の符号を付ける。
                plane = graph._node("angleBetween", role + "Plane")
                plane.getPlug("vector1").set([0.0, 1.0, 0.0])
                plane.getPlug("vector2X").set(0.0)
                local.getPlug("outputY").connectTo(plane.getPlug("vector2Y"))
                local.getPlug("outputZ").connectTo(plane.getPlug("vector2Z"))
                sign = graph._node("condition", role + "Sign")
                sign.getPlug("operation").set(3)  # l·n >= 0 なら外側(正)
                local.getPlug("outputZ").connectTo(sign.getPlug("firstTerm"))
                sign.getPlug("colorIfTrueR").set(1.0)
                sign.getPlug("colorIfFalseR").set(-1.0)
                signed = graph._node("multiplyDivide", role + "Signed")
                degrees(plane.getPlug("angle"), role + "PlaneDegrees").connectTo(signed.getPlug("input1X"))
                sign.getPlug("outColorR").connectTo(signed.getPlug("input2X"))
                reach = graph._node("plusMinusAverage", role + "Reach")
                signed.getPlug("outputX").connectTo(reach.getPlug("input1D")[0])
                owner.getPlug("clearance").connectTo(reach.getPlug("input1D")[1])

                # lateralAngle = |90 - (l と t の角度)|、falloff = clamp(1 - lateral / spread)。
                lateral = graph._node("angleBetween", role + "Lateral")
                lateral.getPlug("vector1").set([1.0, 0.0, 0.0])
                local.getPlug("output").connectTo(lateral.getPlug("vector2"))
                offPlane = graph._node("plusMinusAverage", role + "OffPlane")
                offPlane.getPlug("operation").set(2)
                offPlane.getPlug("input1D")[0].set(90.0)
                degrees(lateral.getPlug("angle"), role + "LateralDegrees").connectTo(offPlane.getPlug("input1D")[1])
                absolute = graph._node("multiplyDivide", role + "Absolute")
                absolute.getPlug("operation").set(3)
                offPlane.getPlug("output1D").connectTo(absolute.getPlug("input1X"))
                absolute.getPlug("input2X").set(2.0)
                root = graph._node("multiplyDivide", role + "AbsoluteRoot")
                root.getPlug("operation").set(3)
                absolute.getPlug("outputX").connectTo(root.getPlug("input1X"))
                root.getPlug("input2X").set(0.5)
                ratio = graph._node("multiplyDivide", role + "LateralRatio")
                ratio.getPlug("operation").set(2)
                root.getPlug("outputX").connectTo(ratio.getPlug("input1X"))
                owner.getPlug("spread").connectTo(ratio.getPlug("input2X"))
                remain = graph._node("plusMinusAverage", role + "Remain")
                remain.getPlug("operation").set(2)
                remain.getPlug("input1D")[0].set(1.0)
                ratio.getPlug("outputX").connectTo(remain.getPlug("input1D")[1])
                falloff = graph._node("clamp", role + "Falloff")
                falloff.getPlug("maxR").set(1.0)
                remain.getPlug("output1D").connectTo(falloff.getPlug("inputR"))

                # push = clamp(reach * falloff, 0, maxAngle)
                scaled = graph._node("multiplyDivide", role + "Scaled")
                reach.getPlug("output1D").connectTo(scaled.getPlug("input1X"))
                falloff.getPlug("outputR").connectTo(scaled.getPlug("input2X"))
                limit = graph._node("clamp", role + "Push")
                scaled.getPlug("outputX").connectTo(limit.getPlug("inputR"))
                owner.getPlug("maxAngle").connectTo(limit.getPlug("maxR"))
                pushes.append(limit.getPlug("outputR"))

            # 脚のうち大きい方 → weight を掛けて angle<i>。
            largest = pushes[0]
            for leg_index, value in enumerate(pushes[1:], 1):
                choose = graph._node("condition", "skirt{}Max{}".format(index, leg_index))
                choose.getPlug("operation").set(2)
                value.connectTo(choose.getPlug("firstTerm"))
                largest.connectTo(choose.getPlug("secondTerm"))
                value.connectTo(choose.getPlug("colorIfTrueR"))
                largest.connectTo(choose.getPlug("colorIfFalseR"))
                largest = choose.getPlug("outColorR")
            weighted = graph._node("multiplyDivide", "skirt{}Weighted".format(index))
            largest.connectTo(weighted.getPlug("input1X"))
            owner.getPlug("weight").connectTo(weighted.getPlug("input2X"))
            weighted.getPlug("outputX").connectTo(owner.getPlug("angle" + str(index)))

            # offsetMatrix = G^-1 · Rx(angle) · G。角度は度からラジアンへ明示的に変換する。
            radians = graph._node("unitConversion", "skirt{}Radians".format(index))
            conversions.add(radians.getUuid())
            owner.getPlug("angle" + str(index)).connectTo(radians.getPlug("input"))
            radians.getPlug("conversionFactor").set(math.pi / 180.0)
            rotate = graph._node("composeMatrix", "skirt{}Rotate".format(index))
            radians.getPlug("output").connectTo(rotate.getPlug("inputRotateX"))
            frame = Matrix([
                hinge.x, hinge.y, hinge.z, 0.0,
                direction.x, direction.y, direction.z, 0.0,
                outward.x, outward.y, outward.z, 0.0,
                position.x, position.y, position.z, 1.0,
            ])
            for attr, before, after in (
                ("offsetMatrix", [], []),
                ("matrix", [rest], []),
                ("worldMatrix", [rest], [parent.getPlug("worldMatrix")[0]]),
            ):
                product = graph._node("multMatrix", "skirt{}{}".format(index, attr[0].upper() + attr[1:]))
                inputs = product.getPlug("matrixIn")
                slot = 0
                for value in before + [frame.inverse()]:
                    inputs[slot].set(value)
                    slot += 1
                rotate.getPlug("outputMatrix").connectTo(inputs[slot])
                inputs[slot + 1].set(frame)
                slot += 2
                for plug in after:
                    plug.connectTo(inputs[slot])
                    slot += 1
                product.getPlug("matrixSum").connectTo(owner.getPlug(attr + str(index)))
            if connect:
                owner.getPlug("offsetMatrix" + str(index)).connectTo(skirts[index].getPlug("offsetParentMatrix"))

        owner.setAttrFlags(outputs, keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph
