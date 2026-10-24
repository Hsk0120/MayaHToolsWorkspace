"""目の向きに上下のまぶたを追従させ、まばたきと上下の交差防止を標準DGで構築する。"""

import math

import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution

#: Mayaの回転順序名と番号(rotateOrder・inputRotateOrderの値)。
_ROTATE_ORDERS = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")


class EyelidFollow(TwistDistribution):
    """目の上下(Pitch)・左右(Yaw)の一部を上下のまぶたへ移し、まばたきで閉じる標準DG。

    角度はすべて「閉じる向き」を正とする座標で計算する。上まぶたの縁は基準で0度、
    下まぶたの縁は基準でopenAngle度の位置にあり、上が下を越えないように開きを0以上へ制限する。
    """

    @classmethod
    def rotateOrder(cls, pitchAxis, yawAxis):
        """Pitchを先、Yawを後に回す回転順序の番号を返す。

        Args:
            pitchAxis (str): まぶたを開閉する軸x/y/z。
            yawAxis (str): 目の左右の軸x/y/z。pitchAxisと異なる。

        Returns:
            int: Mayaの回転順序番号。
        """
        roll = [axis for axis in "xyz" if axis not in (pitchAxis, yawAxis)][0]
        return _ROTATE_ORDERS.index(pitchAxis + yawAxis + roll)

    @classmethod
    def lidAngles(cls, pitch, yaw, upperFollow=0.8, lowerFollow=0.4, yawFollow=0.1, openAngle=40.0,
                  blink=0.0, blinkHeight=0.2, closeDirection=1):
        """目の角度からまぶたの角度を計算する(DGと同じ式のPython版)。

        Args:
            pitch (float): 目のPitch角(度)。pitchAxisまわりの右手系の角度。
            yaw (float): 目のYaw角(度)。
            upperFollow (float): 上まぶたが目のPitchに追従する割合。
            lowerFollow (float): 下まぶたが目のPitchに追従する割合。
            yawFollow (float): 上下のまぶたが目のYawに追従する割合。
            openAngle (float): 基準での上下のまぶたの縁の開き(度)。
            blink (float): まばたきの量。0で開き、1で閉じる。
            blinkHeight (float): 閉じる位置。0で下まぶたの縁、1で上まぶたの縁。
            closeDirection (int): 上まぶたが閉じる向きのPitchの符号。1または-1。

        Returns:
            dict: upperAngle・lowerAngle(各まぶたの基準からのPitch角、度)、lidYaw(度)、
            gap(閉じる向きで測った上下の縁の開き、度。0以上)。
        """
        closing = closeDirection * pitch
        upper = upperFollow * closing
        lower = openAngle + lowerFollow * closing
        difference = lower - upper
        meet = lower - blinkHeight * difference
        gap = max(difference, 0.0)
        opening = 1.0 - blink
        upper_edge = meet - opening * (1.0 - blinkHeight) * gap
        lower_edge = meet + opening * blinkHeight * gap
        return {
            "upperAngle": closeDirection * upper_edge,
            "lowerAngle": closeDirection * (lower_edge - openAngle),
            "lidYaw": yawFollow * yaw,
            "gap": lower_edge - upper_edge,
        }

    @classmethod
    @undoTransaction("mlrig.EyelidFollow.create")
    def create(cls, eye, upperLid, lowerLid, name="eyelidFollow", pitchAxis="x", yawAxis="y",
               closeDirection=1, upperFollow=0.8, lowerFollow=0.4, yawFollow=0.1, openAngle=40.0,
               blinkHeight=0.2):
        """上下のまぶたの親空間行列を生成する。

        Args:
            eye (str | Node): 目のtransform。まぶたと同じ親を持つ。
            upperLid (str | Node): 上まぶたのtransform。回転中心を目の中心に置く。
            lowerLid (str | Node): 下まぶたのtransform。回転中心を目の中心に置く。
            name (str): 一意なcontainer名。
            pitchAxis (str): 親空間でまぶたを開閉する軸(目の上下の軸)x/y/z。
            yawAxis (str): 親空間での目の左右の軸x/y/z。pitchAxisと異なる。
            closeDirection (int): 上まぶたが閉じる(下がる)向きのpitchAxisまわりの符号。1または-1。
            upperFollow (float): 上まぶたが目のPitchに追従する割合。0〜1。
            lowerFollow (float): 下まぶたが目のPitchに追従する割合。0〜1。
            yawFollow (float): 上下のまぶたが目のYawに追従する割合。0〜1。
            openAngle (float): 基準での上下のまぶたの縁の開き。度、0より大きく179以下。
            blinkHeight (float): まばたきで閉じる位置。0で下まぶたの縁、1で上まぶたの縁。

        Returns:
            EyelidFollow: upperMatrix・lowerMatrix・eyePitch・eyeYaw・upperAngle・lowerAngle・
            lidYaw・gapの所有者。containerのblinkでまばたきする。

        Raises:
            ValueError: 親子関係・軸・符号・割合・角度が不正な場合、またはnameが既に存在する場合。

        Note:
            基準は生成時の姿勢。目の現在のローカル回転Lと基準回転E0から、親空間での差分
            D = E0^-1 * L(行ベクトル規約)を、Pitchを先・Yawを後に回すEuler角へ分解する。
            閉じる向きの座標で e = closeDirection*pitch、u = upperFollow*e、l = openAngle + lowerFollow*e、
            meet = l - blinkHeight*(l-u)、g = max(l-u, 0) として、
            上の縁 = meet - (1-blink)*(1-blinkHeight)*g、下の縁 = meet + (1-blink)*blinkHeight*g。
            upperAngle = closeDirection*上の縁、lowerAngle = closeDirection*(下の縁 - openAngle)。
            各まぶたの出力は、まぶたの現在の回転に親空間のPitch(upper/lowerAngle)とYaw(lidYaw)を重ね、
            まぶたの現在位置を保った行列。目のRoll(視線まわり)は使わない。
            Yawが±90度に近い姿勢はEuler分解が不定、負・非一様scaleは対象外。
        """
        axes = ("x", "y", "z")
        if pitchAxis not in axes or yawAxis not in axes or pitchAxis == yawAxis:
            raise ValueError("pitchAxis and yawAxis must be two different axes of x, y and z")
        if closeDirection not in (1, -1):
            raise ValueError("closeDirection must be 1 or -1")
        for value in (upperFollow, lowerFollow, yawFollow, openAngle, blinkHeight):
            if not math.isfinite(value):
                raise ValueError("follow ratios, openAngle and blinkHeight must be finite")
        for value in (upperFollow, lowerFollow, yawFollow, blinkHeight):
            if not 0 <= value <= 1:
                raise ValueError("follow ratios and blinkHeight must be between 0 and 1")
        if not 0 < openAngle <= 179:
            raise ValueError("openAngle must be greater than 0 and at most 179 degrees")
        if mlib.ls(name):
            raise ValueError("EyelidFollow container already exists: " + name)
        eye, upperLid, lowerLid = (mlib.nodes.Node(node) for node in (eye, upperLid, lowerLid))
        nodes = (eye, upperLid, lowerLid)
        if len({node.getUuid() for node in nodes}) != 3 or any(
            not isinstance(node, mlib.nodes.Transform) for node in nodes
        ):
            raise ValueError("Expected three different transforms for the eye and both eyelids")
        parents = [node.getParent() for node in nodes]
        if parents[0] is None or any(
            parent is None or parent.getUuid() != parents[0].getUuid() for parent in parents
        ):
            raise ValueError("The eye and both eyelids must share the same parent transform")

        def localRotation(node):
            """matrix * offsetParentMatrix の回転だけの行列。"""
            local = Matrix(node.getPlug("matrix").get()) * Matrix(node.getPlug("offsetParentMatrix").get())
            return local.quaternion.asMatrix()

        eye_rest = localRotation(eye)
        order = cls.rotateOrder(pitchAxis, yawAxis)
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        scalar = ScalarGraph(owner)
        ratios = (
            ("upperFollow", upperFollow),
            ("lowerFollow", lowerFollow),
            ("yawFollow", yawFollow),
            ("blink", 0.0),
            ("blinkHeight", blinkHeight),
        )
        for attr, value in ratios:
            owner.addAttr(longName=attr, attributeType="double", defaultValue=value,
                          minValue=0, maxValue=1, keyable=True)
        owner.addAttr(longName="openAngle", attributeType="double", defaultValue=openAngle,
                      minValue=0.001, maxValue=179, keyable=True)
        outputs = ("eyePitch", "eyeYaw", "upperAngle", "lowerAngle", "lidYaw", "gap")
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        for attr in ("upperMatrix", "lowerMatrix"):
            owner.addAttr(longName=attr, dataType="matrix")

        def rotationOnly(node, role):
            """ノードのローカル行列から(回転だけの行列, 位置)のPlugを返す。"""
            local = graph._node("multMatrix", role + "Local")
            node.getPlug("matrix").connectTo(local.getPlug("matrixIn")[0])
            node.getPlug("offsetParentMatrix").connectTo(local.getPlug("matrixIn")[1])
            decompose = graph._node("decomposeMatrix", role + "Decompose")
            local.getPlug("matrixSum").connectTo(decompose.getPlug("inputMatrix"))
            rotation = graph._node("composeMatrix", role + "Rotation")
            rotation.getPlug("useEulerRotation").set(False)
            decompose.getPlug("outputQuat").connectTo(rotation.getPlug("inputQuat"))
            return rotation.getPlug("outputMatrix"), decompose.getPlug("outputTranslate")

        # 親空間での目の差分回転 D = E0^-1 * L を、Pitchを先・Yawを後に回すEuler角(度)へ分解する。
        eye_rotation, _ = rotationOnly(eye, "eye")
        delta = graph._node("multMatrix", "eyeDelta")
        delta.getPlug("matrixIn")[0].set(eye_rest.inverse())
        eye_rotation.connectTo(delta.getPlug("matrixIn")[1])
        angles = graph._node("decomposeMatrix", "eyeAngles")
        angles.getPlug("inputRotateOrder").set(order)
        delta.getPlug("matrixSum").connectTo(angles.getPlug("inputMatrix"))
        for attr, axis in (("eyePitch", pitchAxis), ("eyeYaw", yawAxis)):
            degrees = graph._node("unitConversion", attr + "Degrees")
            angles.getPlug("outputRotate" + axis.upper()).connectTo(degrees.getPlug("input"))
            degrees.getPlug("conversionFactor").set(180 / math.pi)
            degrees.getPlug("output").connectTo(owner.getPlug(attr))

        # 閉じる向きを正とする座標で、上下の縁の追従位置と交差しない開きを求める。
        closing = scalar.multiply("closing", owner.getPlug("eyePitch"), closeDirection)
        upper = scalar.multiply("upperFollowEdge", closing, owner.getPlug("upperFollow"))
        lower_offset = scalar.multiply("lowerFollowOffset", closing, owner.getPlug("lowerFollow"))
        lower = scalar.sum("lowerFollowEdge", owner.getPlug("openAngle"), lower_offset)
        difference = scalar.sum("difference", lower, upper, subtract=True)
        meet = scalar.sum(
            "meet", lower, scalar.multiply("meetOffset", owner.getPlug("blinkHeight"), difference), subtract=True
        )
        gap = scalar.condition("positiveGap", difference, 0, difference, 0)
        opening = scalar.sum("opening", 1, owner.getPlug("blink"), subtract=True)
        lower_share = scalar.multiply("lowerShare", opening, owner.getPlug("blinkHeight"))
        upper_share = scalar.sum("upperShare", opening, lower_share, subtract=True)
        upper_edge = scalar.sum(
            "upperEdge", meet, scalar.multiply("upperGap", upper_share, gap), subtract=True
        )
        lower_edge = scalar.sum("lowerEdge", meet, scalar.multiply("lowerGap", lower_share, gap))
        scalar.sum("gapRaw", lower_edge, upper_edge, subtract=True).connectTo(owner.getPlug("gap"))
        scalar.multiply("upperAngleRaw", upper_edge, closeDirection).connectTo(owner.getPlug("upperAngle"))
        lower_rest = scalar.sum("lowerFromRest", lower_edge, owner.getPlug("openAngle"), subtract=True)
        scalar.multiply("lowerAngleRaw", lower_rest, closeDirection).connectTo(owner.getPlug("lowerAngle"))
        scalar.multiply("lidYawRaw", owner.getPlug("eyeYaw"), owner.getPlug("yawFollow")).connectTo(
            owner.getPlug("lidYaw")
        )

        # まぶたの現在の回転へ、親空間のPitch・Yawを重ねて現在位置を保つ。
        for role, lid in (("upper", upperLid), ("lower", lowerLid)):
            lid_rotation, position = rotationOnly(lid, role + "Lid")
            follow = graph._node("composeMatrix", role + "Follow")
            follow.getPlug("inputRotateOrder").set(order)
            for attr, axis in ((role + "Angle", pitchAxis), ("lidYaw", yawAxis)):
                radians = graph._node("unitConversion", role + "_" + attr + "Radians")
                owner.getPlug(attr).connectTo(radians.getPlug("input"))
                radians.getPlug("conversionFactor").set(math.pi / 180)
                radians.getPlug("output").connectTo(follow.getPlug("inputRotate" + axis.upper()))
            combined = graph._node("multMatrix", role + "Combined")
            lid_rotation.connectTo(combined.getPlug("matrixIn")[0])
            follow.getPlug("outputMatrix").connectTo(combined.getPlug("matrixIn")[1])
            rotation = graph._node("decomposeMatrix", role + "ResultRotation")
            combined.getPlug("matrixSum").connectTo(rotation.getPlug("inputMatrix"))
            result = graph._node("composeMatrix", role + "Result")
            result.getPlug("useEulerRotation").set(False)
            rotation.getPlug("outputQuat").connectTo(result.getPlug("inputQuat"))
            position.connectTo(result.getPlug("inputTranslate"))
            result.getPlug("outputMatrix").connectTo(owner.getPlug(role + "Matrix"))
        owner.setAttrFlags(list(outputs), keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph
