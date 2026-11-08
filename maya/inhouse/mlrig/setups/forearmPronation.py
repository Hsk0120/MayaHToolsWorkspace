"""橈骨の頭と尺骨の頭を結ぶ固定の軸のまわりで橈骨を回す前腕の回内・回外の標準DGを構築する。"""

import math

import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.twistLimit import TwistLimit


class ForearmPronation(TwistLimit):
    """手のTwistから回内・回外の角度を求め、橈骨を尺骨のまわりで回す標準DG。

    前腕の回内・回外では尺骨はほぼ動かず、橈骨が「橈骨の頭の中心と尺骨の頭の中心を結ぶ軸」のまわりを回る。
    手の回転を尺骨から見た相対回転にして、この軸まわりのTwistだけを取り出し、回内側・回外側で別々の
    可動域へ柔らかく制限してから橈骨を回す。橈骨は剛体のまま軸のまわりを回るので長さは変わらない。
    """

    @staticmethod
    def _axisFrame(origin, target):
        """originからtargetへ向く軸をXとする回転+位置の行列を作る。

        Args:
            origin (Vector): 軸の始点(行列の位置)。
            target (Vector): 軸の終点。

        Returns:
            Matrix: X軸が origin→target の正規直交フレーム。
        """
        x_axis = (target - origin).normal()
        # 軸と最も平行でない座標軸から、軸に垂直なYを作る。
        helper = min((Vector(1, 0, 0), Vector(0, 1, 0), Vector(0, 0, 1)), key=lambda item: abs(item * x_axis))
        z_axis = (x_axis ^ helper).normal()
        y_axis = z_axis ^ x_axis
        return Matrix([x_axis.x, x_axis.y, x_axis.z, 0,
                       y_axis.x, y_axis.y, y_axis.z, 0,
                       z_axis.x, z_axis.y, z_axis.z, 0,
                       origin.x, origin.y, origin.z, 1])

    @classmethod
    @undoTransaction("mlrig.ForearmPronation.create")
    def create(cls, ulna, ulnaTip, radius, radiusTip, hand, name="forearmPronation", pronationLimit=80.0,
               supinationLimit=85.0, softness=0.1, weight=1.0, sign=1):
        """手のTwistに追従して橈骨を回す行列を生成する。

        Args:
            ulna (str | Node): 尺骨(上腕の先の肘)のtransform。橈骨の親の空間で、毎フレーム読む。
            ulnaTip (str | Node): 尺骨の頭の中心のtransform。生成時の位置だけを使う。
            radius (str | Node): 橈骨の頭の中心のtransform。生成時の位置と向きだけを使う。
            radiusTip (str | Node): 橈骨の手首側の端のtransform。生成時の位置だけを使う。
            hand (str | Node): 手のtransform。毎フレーム読み、尺骨に対する回転からTwistを取り出す。
            name (str): 一意なcontainer名。
            pronationLimit (float): 回内側の可動域(度、1〜179)。
            supinationLimit (float): 回外側の可動域(度、1〜179)。
            softness (float): 可動域の半分に対する柔らかい区間の割合。0で硬い制限、1で中央から緩める。
            weight (float): 手のTwistを橈骨へ伝える割合。0〜1。
            sign (int): 軸(橈骨の頭→尺骨の頭)まわりの正の回転を回内とするなら1、回外とするなら-1。

        Returns:
            ForearmPronation: matrix・tipMatrix・handTwist・rawPronation・pronation・excessPronation・
            pronationWeight・supinationWeight・interosseousDistanceの所有者。

        Raises:
            ValueError: 引数が範囲外の場合、入力がtransformでない場合、ulnaとhandまたはradiusと
                radiusTipが同じノードの場合、橈骨の頭と尺骨の頭が同じ位置の場合、またはnameが既に存在する場合。

        Note:
            基準は生成時の姿勢。尺骨の空間で P = 橈骨の頭、U = 尺骨の頭、a = normalize(U - P)、F = 原点P・X軸aのフレーム、
            Mu・Mh = 尺骨・手のワールド回転、0は生成時の値とする。行ベクトル規約で
            Δ = F (Mh0 Mu0⁻¹)⁻¹ (Mh Mu⁻¹) F⁻¹ の軸成分のクォータニオン(x, w)から
            handTwist = atan2(2wx, w² - x²)(-180〜180度)。
            rawPronation = sign × handTwist × weight、
            pronation = softTwist(rawPronation, -supinationLimit, pronationLimit, softness)。
            excessPronation = rawPronation - pronation、pronationWeight = max(pronation / pronationLimit, 0)、
            supinationWeight = max(-pronation / supinationLimit, 0)。
            matrix = 生成時の橈骨の尺骨空間の行列 × F⁻¹ × Rx(sign × pronation) × F × 尺骨のワールド行列。
            tipMatrixは同じ向きで生成時のradiusTipの位置。
            interosseousDistance = 尺骨の空間で (P + D) / 2 と U / 2 の距離(cm。Dは回した後の橈骨の先、
            尺骨の始点は原点)。
            Twistが±180度をまたぐと符号が反転する。手の位置を橈骨へ追従させる処理は行わない。
        """
        for value in (pronationLimit, supinationLimit, softness, weight):
            if not math.isfinite(value):
                raise ValueError("limits, softness and weight must be finite")
        if not (1 <= pronationLimit <= 179 and 1 <= supinationLimit <= 179):
            raise ValueError("pronationLimit and supinationLimit must be between 1 and 179 degrees")
        if not 0 <= softness <= 1:
            raise ValueError("softness must be between 0 and 1")
        if not 0 <= weight <= 1:
            raise ValueError("weight must be between 0 and 1")
        if sign not in (1, -1):
            raise ValueError("sign must be 1 or -1")
        if mlib.objExists(name):
            raise ValueError("ForearmPronation container already exists: " + name)
        ulna, ulnaTip, radius, radiusTip, hand = [mlib.Node(item) for item in (ulna, ulnaTip, radius, radiusTip, hand)]
        for node in (ulna, ulnaTip, radius, radiusTip, hand):
            if not isinstance(node, mlib.Transform):
                raise ValueError("Expected transforms for the forearm inputs")
        if ulna.getFullName() == hand.getFullName():
            raise ValueError("ulna and hand must be different nodes")
        if radius.getFullName() == radiusTip.getFullName():
            raise ValueError("radius and radiusTip must be different nodes")

        def world(node):
            """生成時のワールド行列を返す。"""
            return Matrix(node.getPlug("worldMatrix")[0].get())

        ulna_rest = world(ulna)
        ulna_inverse = ulna_rest.inverse()
        radius_rest = world(radius)
        radius_local = radius_rest * ulna_inverse
        head = Vector(radius_local.translate)
        ulna_head = Vector((world(ulnaTip) * ulna_inverse).translate)
        if (ulna_head - head).length() < 1e-6:
            raise ValueError("radius and ulnaTip must be at different positions")
        frame = cls._axisFrame(head, ulna_head)
        frame_rotation = Matrix.compose(rotate=frame.quaternion)
        tip_offset = Matrix.compose(translate=(world(radiusTip) * radius_rest.inverse()).translate)
        hand_relative = world(hand).quaternion.asMatrix() * ulna_rest.quaternion.asMatrix().inverse()
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        scalar = ScalarGraph(owner)
        for attr, value in (("pronationLimit", pronationLimit), ("supinationLimit", supinationLimit)):
            owner.addAttr(longName=attr, attributeType="double", defaultValue=value, minValue=1, maxValue=179,
                          keyable=True)
        for attr, value in (("softness", softness), ("weight", weight)):
            owner.addAttr(longName=attr, attributeType="double", defaultValue=value, minValue=0, maxValue=1,
                          keyable=True)
        owner.addAttr(longName="sign", attributeType="double", defaultValue=sign, minValue=-1, maxValue=1,
                      keyable=True)
        outputs = ("handTwist", "rawPronation", "pronation", "excessPronation", "pronationWeight", "supinationWeight",
                   "interosseousDistance")
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        for attr in ("matrix", "tipMatrix"):
            owner.addAttr(longName=attr, dataType="matrix")

        # 尺骨から見た手の回転を、軸がXになるフレームで生成時からの差にする。
        hand_rotation = graph._node("pickMatrix", "handRotation")
        for flag in ("useTranslate", "useScale", "useShear"):
            hand_rotation.getPlug(flag).set(False)
        hand.getPlug("worldMatrix")[0].connectTo(hand_rotation.getPlug("inputMatrix"))
        # 尺骨の回転の逆行列は、クォータニオンのベクトル部の符号を反転して作る(scaleの影響を受けない)。
        ulna_quaternion = graph._node("decomposeMatrix", "ulnaQuaternion")
        ulna.getPlug("worldMatrix")[0].connectTo(ulna_quaternion.getPlug("inputMatrix"))
        conjugate = graph._node("multiplyDivide", "ulnaConjugate")
        conjugate.getPlug("input2").set((-1, -1, -1))
        ulna_rotation_inverse = graph._node("composeMatrix", "ulnaRotationInverse")
        ulna_rotation_inverse.getPlug("useEulerRotation").set(False)
        for component in "XYZ":
            ulna_quaternion.getPlug("outputQuat" + component).connectTo(conjugate.getPlug("input1" + component))
            conjugate.getPlug("output" + component).connectTo(ulna_rotation_inverse.getPlug("inputQuat" + component))
        ulna_quaternion.getPlug("outputQuatW").connectTo(ulna_rotation_inverse.getPlug("inputQuatW"))
        delta = graph._node("multMatrix", "handDelta")
        delta.getPlug("matrixIn")[0].set(frame_rotation * hand_relative.inverse())
        hand_rotation.getPlug("outputMatrix").connectTo(delta.getPlug("matrixIn")[1])
        ulna_rotation_inverse.getPlug("outputMatrix").connectTo(delta.getPlug("matrixIn")[2])
        delta.getPlug("matrixIn")[3].set(frame_rotation.inverse())
        quaternion = graph._node("decomposeMatrix", "handDeltaQuaternion")
        delta.getPlug("matrixSum").connectTo(quaternion.getPlug("inputMatrix"))
        x = quaternion.getPlug("outputQuatX")
        w = quaternion.getPlug("outputQuatW")

        # (w²-x², 2wx) は長さに依らず (cosθ, sinθ) の向きなので、angleBetweenで0〜180度の角度にして符号を付ける。
        cosine = scalar.sum("twistCosine", scalar.multiply("twistWW", w, w), scalar.multiply("twistXX", x, x),
                            subtract=True)
        sine = scalar.multiply("twistSine", scalar.multiply("twistWX", w, x), 2)
        between = graph._node("angleBetween", "twistAngle")
        between.getPlug("vector1").set((1, 0, 0))
        cosine.connectTo(between.getPlug("vector2X"))
        sine.connectTo(between.getPlug("vector2Y"))
        between.getPlug("vector2Z").set(0)
        degrees = graph._node("unitConversion", "twistDegrees")
        degrees.getPlug("conversionFactor").set(180 / math.pi)
        between.getPlug("angle").connectTo(degrees.getPlug("input"))
        unsigned = degrees.getPlug("output")
        negative = scalar.multiply("twistNegative", unsigned, -1)
        twist = scalar.condition("twistSigned", sine, 0, unsigned, negative)
        twist.connectTo(owner.getPlug("handTwist"))

        # rawPronation = sign × handTwist × weight を回内側・回外側の可動域へ制限する。
        raw = scalar.multiply("rawPronationValue", scalar.multiply("weighted", twist, owner.getPlug("weight")),
                              owner.getPlug("sign"))
        raw.connectTo(owner.getPlug("rawPronation"))
        minimum = scalar.multiply("minimumPronation", owner.getPlug("supinationLimit"), -1)
        limited = cls._softLimitGraph(scalar, raw, minimum, owner.getPlug("pronationLimit"), owner.getPlug("softness"))
        limited.connectTo(owner.getPlug("pronation"))
        scalar.sum("excess", raw, limited, subtract=True).connectTo(owner.getPlug("excessPronation"))
        pronated = scalar.multiply("pronationRatio", limited, owner.getPlug("pronationLimit"), operation=2)
        scalar.condition("pronationPositive", pronated, 0, pronated, 0).connectTo(owner.getPlug("pronationWeight"))
        supinated = scalar.multiply("supinationRatio", scalar.multiply("supination", limited, -1),
                                    owner.getPlug("supinationLimit"), operation=2)
        scalar.condition("supinationPositive", supinated, 0, supinated, 0).connectTo(owner.getPlug("supinationWeight"))

        # 軸まわりの回転 F⁻¹ × Rx × F を生成時の橈骨へ掛ける。
        radians = graph._node("unitConversion", "axisRadians")
        radians.getPlug("conversionFactor").set(math.pi / 180)
        scalar.multiply("axisDegrees", limited, owner.getPlug("sign")).connectTo(radians.getPlug("input"))
        spin = graph._node("composeMatrix", "axisSpin")
        radians.getPlug("output").connectTo(spin.getPlug("inputRotateX"))
        local = graph._node("multMatrix", "radiusLocal")
        local.getPlug("matrixIn")[0].set(radius_local * frame.inverse())
        spin.getPlug("outputMatrix").connectTo(local.getPlug("matrixIn")[1])
        local.getPlug("matrixIn")[2].set(frame)
        outer = ulna.getPlug("worldMatrix")[0]
        result = graph._node("multMatrix", "radiusWorld")
        local.getPlug("matrixSum").connectTo(result.getPlug("matrixIn")[0])
        outer.connectTo(result.getPlug("matrixIn")[1])
        result.getPlug("matrixSum").connectTo(owner.getPlug("matrix"))
        tip_local = graph._node("multMatrix", "tipLocal")
        tip_local.getPlug("matrixIn")[0].set(tip_offset)
        local.getPlug("matrixSum").connectTo(tip_local.getPlug("matrixIn")[1])
        tip_world = graph._node("multMatrix", "tipWorld")
        tip_local.getPlug("matrixSum").connectTo(tip_world.getPlug("matrixIn")[0])
        outer.connectTo(tip_world.getPlug("matrixIn")[1])
        tip_world.getPlug("matrixSum").connectTo(owner.getPlug("tipMatrix"))

        # 尺骨の空間で橈骨の中点と尺骨の中点の距離を測る。
        tip_position = graph._node("decomposeMatrix", "tipLocalPosition")
        tip_local.getPlug("matrixSum").connectTo(tip_position.getPlug("inputMatrix"))
        midpoint = graph._node("plusMinusAverage", "radiusMidpoint")
        midpoint.getPlug("operation").set(3)
        midpoint.getPlug("input3D")[0].set((head.x, head.y, head.z))
        tip_position.getPlug("outputTranslate").connectTo(midpoint.getPlug("input3D")[1])
        distance = graph._node("distanceBetween", "interosseous")
        midpoint.getPlug("output3D").connectTo(distance.getPlug("point1"))
        distance.getPlug("point2").set((ulna_head.x * 0.5, ulna_head.y * 0.5, ulna_head.z * 0.5))
        distance.getPlug("distance").connectTo(owner.getPlug("interosseousDistance"))

        owner.setAttrFlags(list(outputs), keyable=False, channelBox=True)
        # 位置の値はすべて内部単位(cm)のまま計算するので、UIの長さ単位で挿入された変換は係数1にする。
        explicit = {degrees.getUuid(), radians.getUuid()}
        added = [node for node in mlib.ls(type="unitConversion")
                 if node.getUuid() not in conversions and node.getUuid() not in explicit]
        for node in added:
            node.getPlug("conversionFactor").set(1.0)
        if added:
            owner.addMembers(*added)
        return graph
