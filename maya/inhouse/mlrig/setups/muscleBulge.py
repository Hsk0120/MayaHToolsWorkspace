"""子の関節の曲げ角から、親の骨の上に置いた補助骨を膨らませ外へ押し出す標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.twistDistribution import TwistDistribution


class MuscleBulge(TwistDistribution):
    """肘・膝・指を曲げたときの筋肉の膨らみを、補助骨のscaleと移動で表す標準DG。

    補助骨は親の骨の上(親から子の関節までの決まった割合の位置)に置き、親の骨と同じ向きを保つ。
    曲げ角はEuler角ではなく、子の骨の長手軸が生成時の向きから何度傾いたか(ひねりを含まない曲げの大きさ)で測る。
    曲げ角が startAngle を超えてから膨らみ始め、fullAngle で最大になる(間はsmoothstep)。
    """

    @classmethod
    def response(cls, angle, startAngle, fullAngle):
        """曲げ角から膨らみの割合を計算する。

        Args:
            angle (float): 曲げ角(度)。
            startAngle (float): 膨らみ始める角度(度)。
            fullAngle (float): 膨らみが最大になる角度(度)。startAngleより大きい。

        Returns:
            float: 0〜1の割合。t = clamp((angle-startAngle)/(fullAngle-startAngle), 0, 1) の t*t*(3-2t)。
        """
        t = min(max((angle - startAngle) / (fullAngle - startAngle), 0.0), 1.0)
        return t * t * (3.0 - 2.0 * t)

    @classmethod
    @undoTransaction("mlrig.MuscleBulge.create")
    def create(cls, parent, joint, name="muscleBulge", axis="x", pushAxis="y", position=0.5,
               startAngle=45.0, fullAngle=135.0, bulge=0.3, push=0.5):
        """親の骨の上の補助骨の行列を、子の関節の曲げ角から生成する。

        Args:
            parent (str | Node): 補助骨を載せる骨(上腕・大腿など)のtransform。
            joint (str | Node): parentの直接の子で、曲げ角を測る関節(肘・膝など)のtransform。
            name (str): 一意なcontainer名。
            axis (str): parentとjointの長手軸x/y/z。jointのこの軸の傾きを曲げ角とし、
                補助骨はこの軸に直交する2軸を膨らませる。
            pushAxis (str): 膨らみに合わせて補助骨を押し出すparentのローカル軸。
                x/y/z、または負の向きの -x/-y/-z。
            position (float): parentからjointまでのどの割合に補助骨を置くか(0〜1)。
            startAngle (float): 膨らみ始める曲げ角(度、0〜180)。
            fullAngle (float): 膨らみが最大になる曲げ角(度、startAngle〜180)。
            bulge (float): 最大のときに長手軸に直交する2軸のscaleへ足す量(0.3なら1.3倍)。
            push (float): 最大のときにpushAxisへ押し出す距離(cm)。

        Returns:
            MuscleBulge: matrix・worldMatrix・bendAngle・weight・scale・offsetの所有者。

        Raises:
            ValueError: 軸・角度・割合が不正な場合、jointがparentの直接の子でない場合、
                jointがparentと同じ位置にある場合、またはnameが既に存在する場合。

        Note:
            基準は生成時の姿勢。曲げ角 bendAngle = 生成時と現在の、parentの空間で見たjointのaxisの向きの間の角度(度)。
            weight = response(bendAngle, startAngle, fullAngle)、scale = 1 + bulge*weight、
            offset = push*weight(cm)。
            matrix(parentの空間) = S * T。Sは長手軸1・他の2軸scaleの拡大、
            Tの移動は position*(jointの現在の親空間での位置) + pushAxis*offset、回転はparentと同じ。
            worldMatrix = matrix * parentのworldMatrix。補助骨をparentの子に置くなら
            matrix を offsetParentMatrix へ接続する(補助骨自身のtranslate/rotate/scaleは0/0/1にしておく)。
            jointのひねり(axis回り)だけでは膨らまない。曲げ角は向きの差だけを見るので、
            曲げる向き(内側・外側)は区別しない。startAngle・fullAngle・bulge・push・positionは作成後も変更できる。
        """
        axes = ("x", "y", "z")
        if axis not in axes:
            raise ValueError("axis must be x, y or z")
        push_axes = axes + tuple("-" + value for value in axes)
        if pushAxis not in push_axes:
            raise ValueError("pushAxis must be x, y, z, -x, -y or -z")
        values = [float(value) for value in (position, startAngle, fullAngle, bulge, push)]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("position, angles, bulge and push must be finite")
        position, startAngle, fullAngle, bulge, push = values
        if not 0.0 <= position <= 1.0:
            raise ValueError("position must be between 0 and 1")
        if not 0.0 <= startAngle < fullAngle <= 180.0:
            raise ValueError("Expected 0 <= startAngle < fullAngle <= 180")
        if mlib.objExists(name):
            raise ValueError("MuscleBulge container already exists: " + name)
        parent, joint = mlib.nodes.Node(parent), mlib.nodes.Node(joint)
        if any(not isinstance(node, mlib.nodes.Transform) for node in (parent, joint)):
            raise ValueError("Expected transforms for the parent and the joint")
        joint_parent = joint.getParent()
        if joint_parent is None or joint_parent != parent:
            raise ValueError("Expected a direct parent-child pair")
        unit = [float(value == axis) for value in axes]
        relative_rest = Matrix(joint.getPlug("matrix").get()) * Matrix(
            joint.getPlug("offsetParentMatrix").get()
        )
        if Vector(relative_rest.translate).length() < 1e-6:
            raise ValueError("The joint must be away from the parent")
        rest_direction = Vector(Vector(*unit) * relative_rest).normal()
        sign = -1.0 if pushAxis.startswith("-") else 1.0
        push_vector = [sign * float(value == pushAxis[-1]) for value in axes]

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        for attr, value, bounds in (
            ("position", position, {"minValue": 0, "maxValue": 1}),
            ("startAngle", startAngle, {"minValue": 0, "maxValue": 180}),
            ("fullAngle", fullAngle, {"minValue": 0.001, "maxValue": 180}),
            ("bulge", bulge, {}),
            ("push", push, {}),
        ):
            owner.addAttr(longName=attr, attributeType="double", defaultValue=value, keyable=True, **bounds)
        outputs = ("bendAngle", "weight", "scale", "offset")
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        for attr in ("matrix", "worldMatrix"):
            owner.addAttr(longName=attr, dataType="matrix")

        # jointの親空間での現在の行列(OPMを含む)と、その長手軸の向き。
        relative = graph._node("multMatrix", "relative")
        joint.getPlug("matrix").connectTo(relative.getPlug("matrixIn")[0])
        joint.getPlug("offsetParentMatrix").connectTo(relative.getPlug("matrixIn")[1])
        direction = graph._node("vectorProduct", "direction")
        direction.getPlug("operation").set(3)
        direction.getPlug("input1").set(unit)
        direction.getPlug("normalizeOutput").set(True)
        relative.getPlug("matrixSum").connectTo(direction.getPlug("matrix"))
        # 曲げ角: 生成時の向きとの間の角度。ひねりは向きを変えないので含まれない。
        angle = graph._node("angleBetween", "bend")
        angle.getPlug("vector1").set(list(rest_direction))
        direction.getPlug("output").connectTo(angle.getPlug("vector2"))
        degrees = graph._node("unitConversion", "bendDegrees")
        conversions.add(degrees.getUuid())
        angle.getPlug("angle").connectTo(degrees.getPlug("input"))
        degrees.getPlug("conversionFactor").set(180.0 / math.pi)
        degrees.getPlug("output").connectTo(owner.getPlug("bendAngle"))

        # t = clamp((bendAngle - startAngle) / (fullAngle - startAngle), 0, 1)
        ranged = graph._node("setRange", "range")
        owner.getPlug("bendAngle").connectTo(ranged.getPlug("valueX"))
        owner.getPlug("startAngle").connectTo(ranged.getPlug("oldMinX"))
        owner.getPlug("fullAngle").connectTo(ranged.getPlug("oldMaxX"))
        ranged.getPlug("minX").set(0)
        ranged.getPlug("maxX").set(1)
        clamped = graph._node("clamp", "rangeClamp")
        clamped.getPlug("maxR").set(1)
        ranged.getPlug("outValueX").connectTo(clamped.getPlug("inputR"))
        t = clamped.getPlug("outputR")
        # weight = t*t*(3-2t)(smoothstep)。膨らみ始めは緩やかに、途中から急に膨らむ。
        powers = graph._node("multiplyDivide", "smoothTerms")
        t.connectTo(powers.getPlug("input1X"))
        t.connectTo(powers.getPlug("input2X"))
        t.connectTo(powers.getPlug("input1Y"))
        powers.getPlug("input2Y").set(-2)
        falloff = graph._node("plusMinusAverage", "smoothFalloff")
        powers.getPlug("outputY").connectTo(falloff.getPlug("input1D")[0])
        falloff.getPlug("input1D")[1].set(3)
        smooth = graph._node("multiplyDivide", "smooth")
        powers.getPlug("outputX").connectTo(smooth.getPlug("input1X"))
        falloff.getPlug("output1D").connectTo(smooth.getPlug("input2X"))
        smooth.getPlug("outputX").connectTo(owner.getPlug("weight"))

        # scale = 1 + bulge*weight、offset = push*weight
        amounts = graph._node("multiplyDivide", "amounts")
        owner.getPlug("bulge").connectTo(amounts.getPlug("input1X"))
        owner.getPlug("push").connectTo(amounts.getPlug("input1Y"))
        owner.getPlug("weight").connectTo(amounts.getPlug("input2X"))
        owner.getPlug("weight").connectTo(amounts.getPlug("input2Y"))
        scale = graph._node("plusMinusAverage", "scale")
        amounts.getPlug("outputX").connectTo(scale.getPlug("input1D")[0])
        scale.getPlug("input1D")[1].set(1)
        scale.getPlug("output1D").connectTo(owner.getPlug("scale"))
        amounts.getPlug("outputY").connectTo(owner.getPlug("offset"))

        # 移動 = position * jointの現在の位置 + pushAxis * offset(cm)
        location = graph._node("decomposeMatrix", "jointLocation")
        relative.getPlug("matrixSum").connectTo(location.getPlug("inputMatrix"))
        along = graph._node("multiplyDivide", "along")
        location.getPlug("outputTranslate").connectTo(along.getPlug("input1"))
        for component in "XYZ":
            owner.getPlug("position").connectTo(along.getPlug("input2" + component))
        pushed = graph._node("multiplyDivide", "pushed")
        pushed.getPlug("input2").set(push_vector)
        for component in "XYZ":
            owner.getPlug("offset").connectTo(pushed.getPlug("input1" + component))
        translate = graph._node("plusMinusAverage", "translate")
        along.getPlug("output").connectTo(translate.getPlug("input3D")[0])
        pushed.getPlug("output").connectTo(translate.getPlug("input3D")[1])

        compose = graph._node("composeMatrix", "local")
        translate.getPlug("output3D").connectTo(compose.getPlug("inputTranslate"))
        for component in "XYZ":
            if component.lower() != axis:
                owner.getPlug("scale").connectTo(compose.getPlug("inputScale" + component))
        compose.getPlug("outputMatrix").connectTo(owner.getPlug("matrix"))
        world = graph._node("multMatrix", "world")
        compose.getPlug("outputMatrix").connectTo(world.getPlug("matrixIn")[0])
        parent.getPlug("worldMatrix")[0].connectTo(world.getPlug("matrixIn")[1])
        world.getPlug("matrixSum").connectTo(owner.getPlug("worldMatrix"))
        owner.setAttrFlags(list(outputs), keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph
