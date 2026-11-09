"""肋骨をポンプハンドルとバケットハンドルの2つの軸で回し、胸骨を追従させる呼吸の標準DGを構築する。"""

import math

import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.forearmPronation import ForearmPronation


class RibBreathing(ForearmPronation):
    """1つの呼吸の値から、複数の肋骨の行列と胸骨の行列を作る標準DG。

    肋骨は根元を通る固定の2つの軸のまわりで回る。ポンプハンドルの軸は「肋骨の方向 × 上方向」で、胸骨側の端を
    持ち上げる。バケットハンドルの軸は根元と胸骨側の端を結ぶ線で、両端を動かさずに肋骨の中央を持ち上げる。
    胸骨は肋骨の胸骨側の端の平均の移動と、上半分と下半分を結ぶ線の傾きに追従する。
    """

    #: 1つのセットアップで扱う肋骨の最大本数。
    MAXIMUM_RIBS = 64

    @classmethod
    @undoTransaction("mlrig.RibBreathing.create")
    def create(cls, spine, ribs, name="ribBreathing", sternum=None, sternalRibs=None, up=(0.0, 1.0, 0.0),
               pumpAngle=10.0, bucketAngle=10.0, minBreath=-0.5, maxBreath=1.5, softness=0.1):
        """呼吸の値に応じて肋骨を回す行列を生成する。

        Args:
            spine (str | Node): 胸椎のtransform。肋骨の親の空間で、毎フレーム読む。
            ribs (Sequence[tuple[str | Node, str | Node, str | Node]]): 肋骨ごとの(根元, 中央, 胸骨側の端)の
                transform。生成時の姿勢だけを使う。根元の行列が出力の基準。2本以上。順番は問わない。
            name (str): 一意なcontainer名。
            sternum (str | Node | None): 胸骨のtransform。生成時の行列だけを使う。Noneなら胸骨の出力を作らない。
            sternalRibs (Sequence[int] | None): 胸骨に付く肋骨のribsの番号。Noneならすべて。
            up (Sequence[float]): spineの空間での上方向。
            pumpAngle (float): breath=1で重み1の肋骨をポンプハンドルの軸で回す角度(度、0〜45)。
            bucketAngle (float): breath=1で重み1の肋骨をバケットハンドルの軸で回す角度(度、0〜45)。
            minBreath (float): 呼吸の値の下限(強く吐いた状態)。負の値。
            maxBreath (float): 呼吸の値の上限(深く吸った状態)。正の値。
            softness (float): 範囲の半分に対する柔らかい区間の割合。0で硬い制限。breath=0が柔らかい区間に入らない値まで。

        Returns:
            RibBreathing: ribMatrix[]・midMatrix[]・tipMatrix[]・effectiveBreath・excessBreath・expansion、
            sternumを指定したときはsternumMatrix・sternumLiftの所有者。

        Raises:
            ValueError: 引数が範囲外の場合、入力がtransformでない場合、肋骨の根元と端が同じ位置の場合、肋骨の方向が
                上方向と平行な場合、中央の点からバケットの向きを決められない場合、すべての根元が同じ高さの場合、
                sternalRibsの番号が範囲外の場合、またはnameが既に存在する場合。

        Note:
            基準は生成時の姿勢。spineの空間で H = 根元、M = 中央、T = 端、v = T - H、u = 上方向とする。
            F_b = 原点H・X軸 normalize(v) のフレーム、F_p = 原点H・X軸 normalize(v × u) のフレーム。
            s = (hmax - H·u) / (hmax - hmin) (最上段0、最下段1)、既定の重みは
            pumpWeight = 1 - 0.5s、bucketWeight = 0.5 + 0.5s。
            effectiveBreath = softLimit(breath, minBreath, maxBreath, softness)、excessBreath = breath - effectiveBreath。
            rp = effectiveBreath × pumpAngle × pumpWeight、
            rb = effectiveBreath × bucketAngle × bucketWeight × 符号(中央が上がる向き)。
            ribMatrix = R0 × F_b⁻¹ × Rx(rb) × F_b × F_p⁻¹ × Rx(rp) × F_p × spineのワールド行列(R0は生成時の根元の行列)。
            midMatrix・tipMatrixは同じ向きで生成時の中央・端の位置。expansionは中央の点の移動量の平均(spineの空間のcm)。
            sternumMatrix = S0 × P⁻¹ × R(a0→a) × P × T(Δ) × spineのワールド行列。S0は生成時の胸骨の行列、Pはその位置、
            Δは胸骨に付く肋骨の端の平均の移動、a0・aは上半分の端の平均から下半分の端の平均へのベクトルの
            生成時と現在の値。sternumLift = Δ·u。
            胸骨に付く肋骨がすべて同じ高さなら傾きは0。肋骨と胸骨の閉じた連結は解かず、端と胸骨の間は肋軟骨の変形で吸収する想定。
        """
        for value in (pumpAngle, bucketAngle, minBreath, maxBreath, softness):
            if not math.isfinite(value):
                raise ValueError("angles, limits and softness must be finite")
        if not (0 <= pumpAngle <= 45 and 0 <= bucketAngle <= 45):
            raise ValueError("pumpAngle and bucketAngle must be between 0 and 45 degrees")
        if not minBreath < 0 < maxBreath:
            raise ValueError("minBreath must be negative and maxBreath must be positive")
        if not 0 <= softness <= 1:
            raise ValueError("softness must be between 0 and 1")
        if softness * (maxBreath - minBreath) * 0.5 > min(-minBreath, maxBreath):
            raise ValueError("softness is too large: breath=0 must stay outside the soft range")
        up_axis = Vector(*up)
        if up_axis.length() < 1e-6:
            raise ValueError("up must not be a zero vector")
        up_axis = up_axis.normal()
        if not 2 <= len(ribs) <= cls.MAXIMUM_RIBS:
            raise ValueError("ribs must contain between 2 and {} ribs".format(cls.MAXIMUM_RIBS))
        if mlib.objExists(name):
            raise ValueError("RibBreathing container already exists: " + name)
        spine = mlib.Node(spine)
        nodes = []
        for rib in ribs:
            if len(rib) != 3:
                raise ValueError("Each rib must be a (head, middle, tip) sequence")
            nodes.append([mlib.Node(item) for item in rib])
        sternum = None if sternum is None else mlib.Node(sternum)
        for node in [spine] + [item for rib in nodes for item in rib] + ([] if sternum is None else [sternum]):
            if not isinstance(node, mlib.Transform):
                raise ValueError("Expected transforms for the spine, ribs and sternum")
        if any(item.getFullName() == spine.getFullName() for rib in nodes for item in rib):
            raise ValueError("A rib point must not be the spine node")
        indices = list(range(len(nodes))) if sternalRibs is None else list(sternalRibs)
        if sternum is not None and (not indices or any(not 0 <= index < len(nodes) for index in indices)):
            raise ValueError("sternalRibs must contain valid rib indices")

        def world(node):
            """生成時のワールド行列を返す。"""
            return Matrix(node.getPlug("worldMatrix")[0].get())

        spine_inverse = world(spine).inverse()
        rests = []
        for head, middle, tip in nodes:
            head_rest = world(head)
            head_local = head_rest * spine_inverse
            head_point = Vector(head_local.translate)
            middle_point = Vector((world(middle) * spine_inverse).translate)
            tip_point = Vector((world(tip) * spine_inverse).translate)
            chord = tip_point - head_point
            if chord.length() < 1e-6:
                raise ValueError("The head and tip of a rib must be at different positions")
            pump_axis = chord ^ up_axis
            if pump_axis.length() < 1e-6:
                raise ValueError("A rib must not be parallel to the up direction")
            # 弦から中央の点へのずれが上がる向きを、バケットの回転の正の向きにする。
            bucket_axis = chord.normal()
            offset = middle_point - head_point
            offset = offset - bucket_axis * (offset * bucket_axis)
            lift = (bucket_axis ^ offset) * up_axis
            if abs(lift) < 1e-6:
                raise ValueError("The middle of a rib must be off the line and must not bulge along the up direction")
            rests.append(dict(local=head_local, head=head_point, middle=middle_point, tip=tip_point,
                              bucket=cls._axisFrame(head_point, tip_point),
                              pump=cls._axisFrame(head_point, head_point + pump_axis.normal()),
                              sign=1.0 if lift > 0 else -1.0, height=head_point * up_axis,
                              middleOffset=Matrix.compose(translate=(world(middle) * head_rest.inverse()).translate),
                              tipOffset=Matrix.compose(translate=(world(tip) * head_rest.inverse()).translate)))
        heights = [rest["height"] for rest in rests]
        highest, lowest = max(heights), min(heights)
        if highest - lowest < 1e-6:
            raise ValueError("The heads of the ribs must not all be at the same height")
        levels = [(highest - height) / (highest - lowest) for height in heights]
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        scalar = ScalarGraph(owner)
        owner.addAttr(longName="breath", attributeType="double", defaultValue=0.0, keyable=True)
        owner.addAttr(longName="minBreath", attributeType="double", defaultValue=minBreath, keyable=True)
        owner.addAttr(longName="maxBreath", attributeType="double", defaultValue=maxBreath, keyable=True)
        owner.addAttr(longName="softness", attributeType="double", defaultValue=softness, minValue=0, maxValue=1,
                      keyable=True)
        for attr, value in (("pumpAngle", pumpAngle), ("bucketAngle", bucketAngle)):
            owner.addAttr(longName=attr, attributeType="double", defaultValue=value, minValue=0, maxValue=45,
                          keyable=True)
        for attr in ("pumpWeight", "bucketWeight"):
            owner.addAttr(longName=attr, attributeType="double", multi=True)
        outputs = ["effectiveBreath", "excessBreath", "expansion"]
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        for attr in ("ribMatrix", "midMatrix", "tipMatrix"):
            owner.addAttr(longName=attr, dataType="matrix", multi=True)

        # 呼吸の値を範囲の内側へ柔らかく止める。超えた分は補正シェイプなどで使えるように出力する。
        breath = owner.getPlug("breath")
        limited = cls._softLimitGraph(scalar, breath, owner.getPlug("minBreath"), owner.getPlug("maxBreath"),
                                      owner.getPlug("softness"))
        limited.connectTo(owner.getPlug("effectiveBreath"))
        scalar.sum("excess", breath, limited, subtract=True).connectTo(owner.getPlug("excessBreath"))

        outer = spine.getPlug("worldMatrix")[0]
        average = graph._node("plusMinusAverage", "expansionAverage")
        average.getPlug("operation").set(3)
        tips = []
        explicit = set()
        for index, rest in enumerate(rests):
            prefix = "rib{}".format(index)
            pump_weight = owner.getPlug("pumpWeight")[index]
            bucket_weight = owner.getPlug("bucketWeight")[index]
            pump_weight.set(1.0 - 0.5 * levels[index])
            bucket_weight.set(0.5 + 0.5 * levels[index])

            def spin(role, angle, weight, factor):
                """角度(度) × 呼吸 × 重み × 係数 だけX軸で回す行列のプラグを作る。"""
                degrees = scalar.multiply(prefix + role + "Degrees", scalar.multiply(
                    prefix + role + "Weighted", scalar.multiply(prefix + role + "Breath", limited, angle), weight), factor)
                radians = graph._node("unitConversion", prefix + role + "Radians")
                radians.getPlug("conversionFactor").set(math.pi / 180)
                explicit.add(radians.getUuid())
                degrees.connectTo(radians.getPlug("input"))
                matrix = graph._node("composeMatrix", prefix + role + "Spin")
                radians.getPlug("output").connectTo(matrix.getPlug("inputRotateX"))
                return matrix.getPlug("outputMatrix")

            # R0 F_b⁻¹ Rx(rb) F_b F_p⁻¹ Rx(rp) F_p の順に掛ける。
            local = graph._node("multMatrix", prefix + "Local")
            local.getPlug("matrixIn")[0].set(rest["local"] * rest["bucket"].inverse())
            spin("Bucket", owner.getPlug("bucketAngle"), bucket_weight, rest["sign"]).connectTo(local.getPlug("matrixIn")[1])
            local.getPlug("matrixIn")[2].set(rest["bucket"] * rest["pump"].inverse())
            spin("Pump", owner.getPlug("pumpAngle"), pump_weight, 1.0).connectTo(local.getPlug("matrixIn")[3])
            local.getPlug("matrixIn")[4].set(rest["pump"])
            rib_world = graph._node("multMatrix", prefix + "World")
            local.getPlug("matrixSum").connectTo(rib_world.getPlug("matrixIn")[0])
            outer.connectTo(rib_world.getPlug("matrixIn")[1])
            rib_world.getPlug("matrixSum").connectTo(owner.getPlug("ribMatrix")[index])

            positions = {}
            for role, attr in (("middle", "midMatrix"), ("tip", "tipMatrix")):
                offset = graph._node("multMatrix", prefix + role.capitalize() + "Local")
                offset.getPlug("matrixIn")[0].set(rest[role + "Offset"])
                local.getPlug("matrixSum").connectTo(offset.getPlug("matrixIn")[1])
                point_world = graph._node("multMatrix", prefix + role.capitalize() + "World")
                offset.getPlug("matrixSum").connectTo(point_world.getPlug("matrixIn")[0])
                outer.connectTo(point_world.getPlug("matrixIn")[1])
                point_world.getPlug("matrixSum").connectTo(owner.getPlug(attr)[index])
                position = graph._node("decomposeMatrix", prefix + role.capitalize() + "Position")
                offset.getPlug("matrixSum").connectTo(position.getPlug("inputMatrix"))
                positions[role] = position.getPlug("outputTranslate")
            tips.append(positions["tip"])

            distance = graph._node("distanceBetween", prefix + "MiddleDistance")
            positions["middle"].connectTo(distance.getPlug("point1"))
            distance.getPlug("point2").set(tuple(rest["middle"]))
            distance.getPlug("distance").connectTo(average.getPlug("input1D")[index])
        average.getPlug("output1D").connectTo(owner.getPlug("expansion"))

        if sternum is not None:
            owner.addAttr(longName="sternumLift", attributeType="double")
            owner.addAttr(longName="sternumMatrix", dataType="matrix")
            outputs.append("sternumLift")
            graph._buildSternum(scalar, world(sternum) * spine_inverse, [tips[index] for index in indices],
                                [rests[index]["tip"] for index in indices], [levels[index] for index in indices],
                                up_axis, outer)

        owner.setAttrFlags(outputs, keyable=False, channelBox=True)
        # 位置の値はすべて内部単位(cm)のまま計算するので、UIの長さ単位で挿入された変換は係数1にする。
        added = [node for node in mlib.ls(type="unitConversion")
                 if node.getUuid() not in conversions and node.getUuid() not in explicit]
        for node in added:
            node.getPlug("conversionFactor").set(1.0)
        if added:
            owner.addMembers(*added)
        return graph

    def _buildSternum(self, scalar, rest, tips, rests, levels, up_axis, outer):
        """胸骨に付く肋骨の端から胸骨の行列を作る。

        Args:
            scalar (ScalarGraph): 演算ノードの生成先。
            rest (Matrix): 生成時の胸骨のspine空間の行列。
            tips (list[Plug]): 肋骨の端のspine空間の位置。
            rests (list[Vector]): 肋骨の端の生成時の位置。
            levels (list[float]): 肋骨の高さの割合(最上段0、最下段1)。
            up_axis (Vector): 上方向(単位ベクトル)。
            outer (Plug): spineのワールド行列。
        """
        owner = self.container

        def mean(role, plugs):
            """位置のプラグの平均を作る。"""
            node = self._node("plusMinusAverage", role)
            node.getPlug("operation").set(3)
            for index, plug in enumerate(plugs):
                plug.connectTo(node.getPlug("input3D")[index])
            return node.getPlug("output3D")

        current = mean("sternumTipAverage", tips)
        origin = Vector(0, 0, 0)
        for point in rests:
            origin += point
        origin *= 1.0 / len(rests)
        delta = self._node("plusMinusAverage", "sternumDelta")
        delta.getPlug("operation").set(2)
        current.connectTo(delta.getPlug("input3D")[0])
        delta.getPlug("input3D")[1].set(tuple(origin))
        lift = self._node("vectorProduct", "sternumLiftDot")
        lift.getPlug("operation").set(1)
        delta.getPlug("output3D").connectTo(lift.getPlug("input1"))
        lift.getPlug("input2").set(tuple(up_axis))
        lift.getPlug("outputX").connectTo(owner.getPlug("sternumLift"))

        pivot = Matrix.compose(translate=rest.translate)
        local = self._node("multMatrix", "sternumLocal")
        local.getPlug("matrixIn")[0].set(rest * pivot.inverse())
        middle = 0.5 * (min(levels) + max(levels))
        upper = [index for index, level in enumerate(levels) if level < middle]
        lower = [index for index, level in enumerate(levels) if level >= middle]
        if upper and lower and max(levels) - min(levels) > 1e-6:
            # 上半分の端の平均から下半分の端の平均への向きの変化だけ、胸骨の位置を中心に回す。
            def direction(points):
                """点の平均を返す。"""
                total = Vector(0, 0, 0)
                for point in points:
                    total += point
                return total * (1.0 / len(points))

            before = direction([rests[index] for index in lower]) - direction([rests[index] for index in upper])
            vector = self._node("plusMinusAverage", "sternumAxis")
            vector.getPlug("operation").set(2)
            mean("sternumLowerAverage", [tips[index] for index in lower]).connectTo(vector.getPlug("input3D")[0])
            mean("sternumUpperAverage", [tips[index] for index in upper]).connectTo(vector.getPlug("input3D")[1])
            between = self._node("angleBetween", "sternumTilt")
            between.getPlug("vector1").set(tuple(before))
            vector.getPlug("output3D").connectTo(between.getPlug("vector2"))
            tilt = self._node("composeMatrix", "sternumTiltMatrix")
            between.getPlug("euler").connectTo(tilt.getPlug("inputRotate"))
            tilt.getPlug("outputMatrix").connectTo(local.getPlug("matrixIn")[1])
        shift = self._node("composeMatrix", "sternumShift")
        delta.getPlug("output3D").connectTo(shift.getPlug("inputTranslate"))
        local.getPlug("matrixIn")[2].set(pivot)
        shift.getPlug("outputMatrix").connectTo(local.getPlug("matrixIn")[3])
        outer.connectTo(local.getPlug("matrixIn")[4])
        local.getPlug("matrixSum").connectTo(owner.getPlug("sternumMatrix"))
