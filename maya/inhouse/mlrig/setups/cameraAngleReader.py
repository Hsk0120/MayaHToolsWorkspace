"""顔(頭)から見たカメラの方向を水平角・垂直角に分け、角度ごとの補正の重みへ変える標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Vector

from mlrig.setups.twistDistribution import TwistDistribution

#: 重みの出力名。前・左・右・上・下・後ろの順。
WEIGHTS = ("weightFront", "weightLeft", "weightRight", "weightAbove", "weightBelow", "weightBack")


class CameraAngleReader(TwistDistribution):
    """カメラの見る角度に応じて、顔の補正(ブレンドシェイプ・補助骨)を切り替える重みを出す標準DG。

    頭のローカル空間でカメラの位置を求め、正面を0度として、水平角 yaw(-180〜180度、
    頭の左側にカメラがあると正)と垂直角 pitch(-90〜90度、頭より上にカメラがあると正)に分ける。
    yaw・pitch の平面に「正面・左・右・上・下」の5点を十字に置き、隣り合う点の間を線形に補間した
    重みと、真後ろへ近づくと後ろの重みへ移る重みを出す。重みの和は常に1で、カメラがどう動いても
    連続に変わる(真後ろで左右が入れ替わるところも、後ろの重みが1になるので跳ねない)。
    """

    @classmethod
    def weights(cls, yaw, pitch, yawRange=90.0, pitchRange=60.0, backFade=30.0):
        """水平角・垂直角から6つの重みを計算する。DGと同じ式。

        Args:
            yaw (float): 水平角(度、-180〜180)。左が正。
            pitch (float): 垂直角(度、-90〜90)。上が正。
            yawRange (float): 左・右の重みが1になる水平角(度)。
            pitchRange (float): 上・下の重みが1になる垂直角(度)。
            backFade (float): 真後ろ(±180度)から何度の範囲で後ろの重みへ移すか(度、正)。

        Returns:
            dict[str, float]: :data:`WEIGHTS` の名前ごとの重み。和は1。

        Note:
            aL = clamp(yaw/yawRange)、aR = clamp(-yaw/yawRange)、bA = clamp(pitch/pitchRange)、
            bB = clamp(-pitch/pitchRange)(clampは0〜1)、sum = aL+aR+bA+bB、s = max(sum, 1)。
            前 = max(1-sum, 0)、左右上下 = 各a・b / s(正面・横・上下の三角形の中は重心座標、
            その外側は横と上下の2点の間の補間)。最後に k = clamp((180-|yaw|)/backFade) を全てに掛け、
            後ろ = 1-k とする。
        """
        def clamp(value):
            return min(max(value, 0.0), 1.0)

        parts = [clamp(yaw / yawRange), clamp(-yaw / yawRange), clamp(pitch / pitchRange), clamp(-pitch / pitchRange)]
        total = sum(parts)
        scale = max(total, 1.0)
        fade = clamp((180.0 - abs(yaw)) / backFade)
        values = [max(1.0 - total, 0.0) * fade] + [part / scale * fade for part in parts] + [1.0 - fade]
        return dict(zip(WEIGHTS, values))

    @classmethod
    @undoTransaction("mlrig.CameraAngleReader.create")
    def create(cls, head, camera, name="cameraAngleReader", forwardAxis="z", upAxis="y",
               yawRange=90.0, pitchRange=60.0, backFade=30.0):
        """頭から見たカメラの角度と、角度ごとの補正の重みを生成する。

        Args:
            head (str | Node): 顔の向きを表すtransform(頭のjointなど)。
            camera (str | Node): カメラ(またはカメラの位置を表す)transform。
            name (str): 一意なcontainer名。
            forwardAxis (str): headのローカルで顔の正面を向く軸。x/y/z、または -x/-y/-z。
            upAxis (str): headのローカルで頭の上を向く軸。forwardAxisと直交する軸。
            yawRange (float): 左・右の重みが1になる水平角(度、0〜180)。
            pitchRange (float): 上・下の重みが1になる垂直角(度、0〜90)。
            backFade (float): 真後ろから何度の範囲で後ろの重みへ移すか(度、0〜180)。

        Returns:
            CameraAngleReader: yaw・pitch・各重みの所有者。

        Raises:
            ValueError: 軸・角度が不正な場合、head・cameraがtransformでない・同じノードの場合、
                または nameが既に存在する場合。

        Note:
            カメラの位置 p = cameraのworldMatrixの位置を headのworldInverseMatrix で頭の空間へ移したもの。
            f = p・forward、u = p・up、l = p・(up×forward)(頭の左向き)。
            yaw = atan2(l, f)、pitch = 90 - (pとupの間の角度)。重みは :meth:`weights` の式。
            yawRange・pitchRange・backFade は作成後も変更できる。カメラが頭の真上・真下・頭と同じ位置に
            あると水平角は決まらない(0として扱われる)。重みは補正シェイプのweightやドリブンキーへ接続する。
        """
        axes = ("x", "y", "z")
        signed = axes + tuple("-" + value for value in axes)
        if forwardAxis not in signed or upAxis not in signed:
            raise ValueError("forwardAxis and upAxis must be x, y, z, -x, -y or -z")
        if forwardAxis[-1] == upAxis[-1]:
            raise ValueError("forwardAxis and upAxis must be perpendicular")
        values = [float(value) for value in (yawRange, pitchRange, backFade)]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("yawRange, pitchRange and backFade must be finite")
        yawRange, pitchRange, backFade = values
        if not 0.0 < yawRange <= 180.0:
            raise ValueError("yawRange must be greater than 0 and at most 180")
        if not 0.0 < pitchRange <= 90.0:
            raise ValueError("pitchRange must be greater than 0 and at most 90")
        if not 0.0 < backFade <= 180.0:
            raise ValueError("backFade must be greater than 0 and at most 180")
        if mlib.ls(name):
            raise ValueError("CameraAngleReader container already exists: " + name)
        head, camera = mlib.nodes.Node(head), mlib.nodes.Node(camera)
        if any(not isinstance(node, mlib.nodes.Transform) for node in (head, camera)):
            raise ValueError("Expected transforms for the head and the camera")
        if head.getUuid() == camera.getUuid():
            raise ValueError("The head and the camera must be different nodes")
        forward = cls._axis(forwardAxis)
        up = cls._axis(upAxis)
        side = up ^ forward

        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        for attr, value, maximum in (
            ("yawRange", yawRange, 180), ("pitchRange", pitchRange, 90), ("backFade", backFade, 180),
        ):
            owner.addAttr(longName=attr, attributeType="double", defaultValue=value, keyable=True,
                          minValue=0.001, maxValue=maximum)
        outputs = ("yaw", "pitch") + WEIGHTS
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")

        # 頭の空間でのカメラの位置と、正面・上・左の成分。
        relative = graph._node("multMatrix", "relative")
        camera.getPlug("worldMatrix")[0].connectTo(relative.getPlug("matrixIn")[0])
        head.getPlug("worldInverseMatrix")[0].connectTo(relative.getPlug("matrixIn")[1])
        location = graph._node("decomposeMatrix", "location")
        relative.getPlug("matrixSum").connectTo(location.getPlug("inputMatrix"))
        components = {}
        for role, vector in (("front", forward), ("up", up), ("left", side)):
            dot = graph._node("vectorProduct", role + "Dot")
            dot.getPlug("operation").set(1)
            dot.getPlug("normalizeOutput").set(False)
            location.getPlug("outputTranslate").connectTo(dot.getPlug("input1"))
            dot.getPlug("input2").set(list(vector))
            components[role] = dot.getPlug("outputX")

        # |yaw| = (f, l, 0) と (1, 0, 0) の間の角度、pitch = 90 - ((f, l, u) と (0, 0, 1) の間の角度)。
        horizontal = graph._node("angleBetween", "horizontal")
        horizontal.getPlug("vector1").set([1.0, 0.0, 0.0])
        components["front"].connectTo(horizontal.getPlug("vector2X"))
        components["left"].connectTo(horizontal.getPlug("vector2Y"))
        horizontal.getPlug("vector2Z").set(0.0)
        vertical = graph._node("angleBetween", "vertical")
        vertical.getPlug("vector1").set([0.0, 0.0, 1.0])
        components["front"].connectTo(vertical.getPlug("vector2X"))
        components["left"].connectTo(vertical.getPlug("vector2Y"))
        components["up"].connectTo(vertical.getPlug("vector2Z"))
        degrees = {}
        for role, node in (("absYaw", horizontal), ("fromUp", vertical)):
            conversion = graph._node("unitConversion", role + "Degrees")
            conversions.add(conversion.getUuid())
            node.getPlug("angle").connectTo(conversion.getPlug("input"))
            conversion.getPlug("conversionFactor").set(180.0 / math.pi)
            degrees[role] = conversion.getPlug("output")
        negative = graph._node("multiplyDivide", "negativeYaw")
        degrees["absYaw"].connectTo(negative.getPlug("input1X"))
        negative.getPlug("input2X").set(-1)
        sign = graph._node("condition", "yawSign")
        sign.getPlug("operation").set(3)  # 左の成分 >= 0 なら正
        components["left"].connectTo(sign.getPlug("firstTerm"))
        degrees["absYaw"].connectTo(sign.getPlug("colorIfTrueR"))
        negative.getPlug("outputX").connectTo(sign.getPlug("colorIfFalseR"))
        sign.getPlug("outColorR").connectTo(owner.getPlug("yaw"))
        pitch = graph._node("plusMinusAverage", "pitch")
        pitch.getPlug("operation").set(2)
        pitch.getPlug("input1D")[0].set(90)
        degrees["fromUp"].connectTo(pitch.getPlug("input1D")[1])
        pitch.getPlug("output1D").connectTo(owner.getPlug("pitch"))

        # yaw/yawRange・pitch/pitchRange を0〜1に切り、左右・上下の成分 aL・aR・bA・bB にする。
        normalized = graph._node("multiplyDivide", "normalized")
        normalized.getPlug("operation").set(2)
        owner.getPlug("yaw").connectTo(normalized.getPlug("input1X"))
        owner.getPlug("pitch").connectTo(normalized.getPlug("input1Y"))
        owner.getPlug("yawRange").connectTo(normalized.getPlug("input2X"))
        owner.getPlug("pitchRange").connectTo(normalized.getPlug("input2Y"))
        flipped = graph._node("multiplyDivide", "flipped")
        normalized.getPlug("output").connectTo(flipped.getPlug("input1"))
        flipped.getPlug("input2").set([-1.0, -1.0, 1.0])
        sides = graph._node("clamp", "sides")
        sides.getPlug("max").set([1.0, 1.0, 1.0])
        normalized.getPlug("outputX").connectTo(sides.getPlug("inputR"))
        flipped.getPlug("outputX").connectTo(sides.getPlug("inputG"))
        levels = graph._node("clamp", "levels")
        levels.getPlug("max").set([1.0, 1.0, 1.0])
        normalized.getPlug("outputY").connectTo(levels.getPlug("inputR"))
        flipped.getPlug("outputY").connectTo(levels.getPlug("inputG"))
        parts = [sides.getPlug("outputR"), sides.getPlug("outputG"), levels.getPlug("outputR"), levels.getPlug("outputG")]

        # sum、s = max(sum, 1)、前 = clamp(1 - sum, 0, 1)
        total = graph._node("plusMinusAverage", "total")
        for index, part in enumerate(parts):
            part.connectTo(total.getPlug("input1D")[index])
        scale = graph._node("clamp", "scale")
        scale.getPlug("min").set([1.0, 0.0, 0.0])
        scale.getPlug("max").set([4.0, 1.0, 0.0])
        total.getPlug("output1D").connectTo(scale.getPlug("inputR"))
        rest = graph._node("plusMinusAverage", "rest")
        rest.getPlug("operation").set(2)
        rest.getPlug("input1D")[0].set(1)
        total.getPlug("output1D").connectTo(rest.getPlug("input1D")[1])
        rest.getPlug("output1D").connectTo(scale.getPlug("inputG"))
        front = scale.getPlug("outputG")

        # 左右上下 = 成分 / s
        divided = []
        for index, group in enumerate((parts[:3], parts[3:])):
            divide = graph._node("multiplyDivide", "divided{}".format(index))
            divide.getPlug("operation").set(2)
            for component, part in zip("XYZ", group):
                part.connectTo(divide.getPlug("input1" + component))
                scale.getPlug("outputR").connectTo(divide.getPlug("input2" + component))
                divided.append(divide.getPlug("output" + component))

        # k = clamp((180 - |yaw|) / backFade, 0, 1)、後ろ = 1 - k、他は k 倍。
        remaining = graph._node("plusMinusAverage", "toBack")
        remaining.getPlug("operation").set(2)
        remaining.getPlug("input1D")[0].set(180)
        degrees["absYaw"].connectTo(remaining.getPlug("input1D")[1])
        fade = graph._node("multiplyDivide", "fade")
        fade.getPlug("operation").set(2)
        remaining.getPlug("output1D").connectTo(fade.getPlug("input1X"))
        owner.getPlug("backFade").connectTo(fade.getPlug("input2X"))
        fadeClamp = graph._node("clamp", "fadeClamp")
        fadeClamp.getPlug("maxR").set(1)
        fade.getPlug("outputX").connectTo(fadeClamp.getPlug("inputR"))
        keep = fadeClamp.getPlug("outputR")
        back = graph._node("plusMinusAverage", "back")
        back.getPlug("operation").set(2)
        back.getPlug("input1D")[0].set(1)
        keep.connectTo(back.getPlug("input1D")[1])
        weighted = [front] + divided
        for index in range(0, len(weighted), 3):
            multiply = graph._node("multiplyDivide", "faded{}".format(index // 3))
            for component, plug, attr in zip("XYZ", weighted[index:index + 3], WEIGHTS[index:index + 3]):
                plug.connectTo(multiply.getPlug("input1" + component))
                keep.connectTo(multiply.getPlug("input2" + component))
                multiply.getPlug("output" + component).connectTo(owner.getPlug(attr))
        back.getPlug("output1D").connectTo(owner.getPlug("weightBack"))

        owner.setAttrFlags(list(outputs), keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph

    @staticmethod
    def _axis(value):
        """``"x"``・``"-z"`` のような軸の指定を単位ベクトルにする。

        Args:
            value (str): 軸の指定。

        Returns:
            Vector: 単位ベクトル。
        """
        sign = -1.0 if value.startswith("-") else 1.0
        return Vector(*[sign * float(axis == value[-1]) for axis in ("x", "y", "z")])
