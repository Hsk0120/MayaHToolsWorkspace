"""1つのrollとbankの値から、かかと・母指球・つま先・内外の縁を支点に足を転がす逆足(リバースフット)の標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.twistDistribution import TwistDistribution

#: 角度のクランプに使う十分大きな値(度)。
_LARGE = 1e6


class FootRoll(TwistDistribution):
    """足のコントロールの1つの値で、かかと→母指球→つま先の順に足を転がす逆足の標準DG。

    逆足の階層(swivel > 外縁 > 内縁 > かかと > つま先 > 母指球 > 足首、つま先の下にtoeTap)と同じ計算を、
    transformの階層を作らずに
    ``multMatrix`` の行列の積で行う。各支点の位置は生成時のコントロールの空間で固定するので、
    コントロールを動かすと足全体が付いて行き、roll・bankが0なら出力は生成時の姿勢と一致する(跳ねない)。
    """

    #: 回転軸として受け付ける軸の名前。先頭の ``-`` は逆回り。
    AXES = ("x", "y", "z", "-x", "-y", "-z")

    @classmethod
    def angles(cls, roll, bank, breakAngle):
        """rollとbankを各支点の回転角へ分ける。

        Args:
            roll (float): 足を転がす量(度)。負はかかと、正は母指球→つま先。
            bank (float): 足を横へ傾ける量(度)。正は外縁、負は内縁を支点にする。
            breakAngle (float): 母指球からつま先へ支点が移る角度(度)。

        Returns:
            dict[str, float]: heel・ball・toe・outer・innerの回転角(度)。
        """
        return {
            "heel": min(roll, 0.0),
            "ball": min(max(roll, 0.0), breakAngle),
            "toe": max(roll - breakAngle, 0.0),
            "outer": max(bank, 0.0),
            "inner": min(bank, 0.0),
        }

    @classmethod
    @undoTransaction("mlrig.FootRoll.create")
    def create(
        cls,
        control,
        ankle,
        ball,
        toe,
        heel,
        inner,
        outer,
        name="footRoll",
        rollAxis="x",
        bankAxis="z",
        swivelAxis="y",
        breakAngle=30.0,
    ):
        """足首と母指球(つま先の骨の付け根)のワールド行列を出力する逆足を生成する。

        Args:
            control (str | Node): 足のコントロール(IKのゴールを動かすtransform)。
            ankle (str | Node): 足首のtransform。生成時のワールド行列を基準にする。
            ball (str | Node): 母指球(つま先の骨の付け根)のtransform。位置はrollの支点にもなる。
            toe (str | Node): つま先の先端の支点。位置だけを使う。
            heel (str | Node): かかとの支点。位置だけを使う。
            inner (str | Node): 負のbankの支点(足の内側の縁)。位置だけを使う。
            outer (str | Node): 正のbankの支点(足の外側の縁)。位置だけを使う。
            name (str): 一意なcontainer名。
            rollAxis (str): rollの回転軸。controlのローカル軸x/y/z(``-`` 付きで逆回り)。
            bankAxis (str): bankの回転軸。rollAxisと異なる軸。
            swivelAxis (str): swivel(母指球を中心に足を水平に回す)の回転軸。
                rollAxis・bankAxisと異なる軸。
            breakAngle (float): 母指球からつま先へ支点が移る角度(度、0以上)。

        Returns:
            FootRoll: roll・bank・swivel・toeTap・breakAngle(keyable)、各支点の角度、ankleMatrix・ballMatrixの所有者。

        Raises:
            ValueError: 軸・角度が不正な場合、同じノードが重複する場合、またはnameが既に存在する場合。

        Note:
            各支点の回転角は heel = min(roll, 0)、ball = clamp(roll, 0, breakAngle)、
            toe = max(roll - breakAngle, 0)、outer = max(bank, 0)、inner = min(bank, 0)(度)。
            支点pの回転は P = T(-p) * R(軸, 角度) * T(p)(pとRは生成時のcontrolの空間)。
            swivelとtoeTapは値をそのまま角度にし、swivelは母指球を中心にswivelAxis、
            toeTapは母指球を中心にrollAxisで回す。
            ankleMatrix = A * P_ball * P_toe * P_heel * P_inner * P_outer * P_swivel * controlのワールド行列、
            ballMatrix = B * P_toeTap * P_toe * P_heel * P_inner * P_outer * P_swivel * controlのワールド行列
            (A・Bは生成時の足首・母指球のワールド行列をcontrolの空間へ移した定数)。
            出力はワールド行列なので、親が原点にあるtransformのoffsetParentMatrix、またはIKのゴールへ
            ワールド空間で渡す。つま先の骨はballMatrixに付けると、つま先の支点の回転だけを受けて地面に残る。
            負・非一様scaleのcontrolは対象外。
        """
        axes = (rollAxis, bankAxis, swivelAxis)
        if any(axis not in cls.AXES for axis in axes) or len({axis[-1] for axis in axes}) != 3:
            raise ValueError(
                "rollAxis, bankAxis and swivelAxis must be three different axes of x, y and z (optionally with -)"
            )
        breakAngle = float(breakAngle)
        if not math.isfinite(breakAngle) or breakAngle < 0:
            raise ValueError("breakAngle must be a finite angle of 0 or more degrees")
        if mlib.objExists(name):
            raise ValueError("FootRoll container already exists: " + name)
        nodes = [mlib.nodes.Node(node) for node in (control, ankle, ball, toe, heel, inner, outer)]
        if len({node.getUuid() for node in nodes}) != len(nodes) or any(
            not isinstance(node, mlib.nodes.Transform) for node in nodes
        ):
            raise ValueError("Expected seven different transforms for the foot")
        control, ankle, ball = nodes[:3]
        control_world = Matrix(control.getPlug("worldMatrix")[0].get())
        to_control = control_world.inverse()

        def local(node):
            """nodeの生成時のワールド行列をcontrolの空間へ移した行列。"""
            return Matrix(node.getPlug("worldMatrix")[0].get()) * to_control

        def translation(position):
            """位置positionへ平行移動する行列。"""
            return Matrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, position.x, position.y, position.z, 1])

        pivots = {
            role: Vector(local(node).translate)
            for role, node in zip(("ball", "toe", "heel", "inner", "outer"), nodes[2:])
        }
        # swivelとtoeTapは母指球を中心に回す。
        pivots["swivel"] = pivots["toeTap"] = pivots["ball"]

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="roll", attributeType="double", keyable=True)
        owner.addAttr(longName="bank", attributeType="double", keyable=True)
        owner.addAttr(longName="swivel", attributeType="double", keyable=True)
        owner.addAttr(longName="toeTap", attributeType="double", keyable=True)
        owner.addAttr(longName="breakAngle", attributeType="double", defaultValue=breakAngle, minValue=0, keyable=True)
        outputs = ("heelAngle", "ballAngle", "toeAngle", "outerAngle", "innerAngle")
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        for attr in ("ankleMatrix", "ballMatrix"):
            owner.addAttr(longName=attr, dataType="matrix")
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}

        # 角度の分配: clampのR/G/Bで負の部分・0〜breakAngle・breakAngleを超えた部分を取り出す。
        over = graph._node("plusMinusAverage", "overBreak")
        over.getPlug("operation").set(2)
        owner.getPlug("roll").connectTo(over.getPlug("input1D")[0])
        owner.getPlug("breakAngle").connectTo(over.getPlug("input1D")[1])
        roll_parts = graph._node("clamp", "rollParts")
        owner.getPlug("roll").connectTo(roll_parts.getPlug("inputR"))
        roll_parts.getPlug("minR").set(-_LARGE)
        owner.getPlug("roll").connectTo(roll_parts.getPlug("inputG"))
        owner.getPlug("breakAngle").connectTo(roll_parts.getPlug("maxG"))
        over.getPlug("output1D").connectTo(roll_parts.getPlug("inputB"))
        roll_parts.getPlug("maxB").set(_LARGE)
        bank_parts = graph._node("clamp", "bankParts")
        owner.getPlug("bank").connectTo(bank_parts.getPlug("inputR"))
        bank_parts.getPlug("maxR").set(_LARGE)
        owner.getPlug("bank").connectTo(bank_parts.getPlug("inputG"))
        bank_parts.getPlug("minG").set(-_LARGE)
        sources = {
            "heel": (roll_parts.getPlug("outputR"), rollAxis),
            "ball": (roll_parts.getPlug("outputG"), rollAxis),
            "toe": (roll_parts.getPlug("outputB"), rollAxis),
            "outer": (bank_parts.getPlug("outputR"), bankAxis),
            "inner": (bank_parts.getPlug("outputG"), bankAxis),
            "swivel": (owner.getPlug("swivel"), swivelAxis),
            "toeTap": (owner.getPlug("toeTap"), rollAxis),
        }

        outputs_roles = ("heel", "ball", "toe", "outer", "inner")
        rotations = {}
        for role, (plug, axis) in sources.items():
            angle = plug
            if role in outputs_roles:
                plug.connectTo(owner.getPlug(role + "Angle"))
                angle = owner.getPlug(role + "Angle")
            # 度をラジアンへ明示的に変換し、UIの角度単位によらず同じ回転にする。軸の符号もここで掛ける。
            radians = graph._node("unitConversion", role + "Radians")
            conversions.add(radians.getUuid())
            angle.connectTo(radians.getPlug("input"))
            sign = -1.0 if axis.startswith("-") else 1.0
            radians.getPlug("conversionFactor").set(sign * math.pi / 180.0)
            compose = graph._node("composeMatrix", role + "Rotate")
            radians.getPlug("output").connectTo(compose.getPlug("inputRotate" + axis[-1].upper()))
            rotations[role] = compose.getPlug("outputMatrix")

        def chain(role, rest, order):
            """生成時の行列restへ、order順に支点の回転を掛けてcontrolのワールド行列を掛ける。"""
            product = graph._node("multMatrix", role + "World")
            inputs = product.getPlug("matrixIn")
            inputs[0].set(rest)
            index = 1
            for pivot in order:
                inputs[index].set(translation(-pivots[pivot]))
                rotations[pivot].connectTo(inputs[index + 1])
                inputs[index + 2].set(translation(pivots[pivot]))
                index += 3
            control.getPlug("worldMatrix")[0].connectTo(inputs[index])
            product.getPlug("matrixSum").connectTo(owner.getPlug(role + "Matrix"))

        chain("ankle", local(ankle), ("ball", "toe", "heel", "inner", "outer", "swivel"))
        chain("ball", local(ball), ("toeTap", "toe", "heel", "inner", "outer", "swivel"))
        owner.setAttrFlags(list(outputs), keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph
