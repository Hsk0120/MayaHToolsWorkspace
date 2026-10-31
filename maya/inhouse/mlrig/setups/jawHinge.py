"""顎の開閉角を閉じた姿勢で柔らかく止め、開くほど顎を前へ滑らせる標準DGを構築する。"""

import math

import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.eyelidFollow import EyelidFollow
from mlrig.setups.twistDistribution import TwistDistribution


class JawHinge(TwistDistribution):
    """顎の開き角(Pitch)を閉じ側だけ制限し、開き角に比例した平行移動を加える標準DG。

    人の顎は開くときに回転だけでなく下顎頭が前へ滑る。開き角に比例した移動でこれを近似し、
    閉じた姿勢(生成時)を越えて上顎へめり込む入力は、-softness度へ指数関数で近づけて止める。
    開く側(0度以上)は変えないため、生成時の姿勢で出力は跳ねない。
    """

    #: 柔らかい区間の幅の下限(度)。softness=0の硬い制限に使う。
    MINIMUM_SOFT_WIDTH = 1e-3

    @classmethod
    def limitedOpen(cls, angle, softness):
        """開き角を、閉じた姿勢(0度)からsoftness度より閉じないように柔らかく制限する。

        Args:
            angle (float): 基準姿勢からの開き角(度)。開く向きが正。
            softness (float): 閉じた姿勢を越えてよい最大の角度(度)。0以上。

        Returns:
            float: 制限後の開き角(度)。angle>=0ではangleと同じ、angle<0では-softness以上(数学的には-softnessに届かず、浮動小数では丸めで届き得る)。
        """
        width = max(softness, cls.MINIMUM_SOFT_WIDTH)
        if angle >= 0:
            return angle
        return -width * (1 - math.exp(angle / width))

    @classmethod
    @undoTransaction("mlrig.JawHinge.create")
    def create(cls, jaw, name="jawHinge", pitchAxis="x", yawAxis="y", openDirection=1, softness=2.0,
               slide=(0.0, 0.0, 0.02)):
        """顎の親空間行列を生成する。

        Args:
            jaw (str | Node): 親transformを持つ顎のtransform。回転中心を顎関節に置き、閉じた姿勢で生成する。
            name (str): 一意なcontainer名。
            pitchAxis (str): 親空間で顎を開閉する軸x/y/z。
            yawAxis (str): 親空間で顎を左右へ振る軸x/y/z。pitchAxisと異なる。
            openDirection (int): 顎が開く向きのpitchAxisまわりの符号。1または-1。
            softness (float): 閉じた姿勢を越えてよい最大の角度。度、0以上45以下。0で硬い制限。
            slide (tuple[float, float, float]): 開き角1度あたりの親空間での移動量(cm)。

        Returns:
            JawHinge: matrix・openAngle・limitedOpen・slideOffsetの所有者。

        Raises:
            ValueError: 親子関係・軸・符号・softness・slideが不正な場合、またはnameが既に存在する場合。

        Note:
            基準は生成時の姿勢(閉じた姿勢)。顎の現在のローカル回転Lと基準回転J0から、
            親空間での差分 D = J0^-1 * L(行ベクトル規約)を、Pitchを先・Yawを後に回すEuler角へ分解する。
            開き角 a = openDirection*pitch、w = max(softness, 0.001) として、
            a>=0 なら o = a、それ以外は o = -w*(1-exp(a/w))(-wへ漸近し、a=0で傾き1のまま接続)。
            出力の回転は J0 * Euler(pitch=openDirection*o, 入力のYaw・Roll)、
            位置は顎の現在位置 + slide*o。o<0ではslideの逆向きへ最大w度分だけ動く。
            Yawが±90度に近い姿勢はEuler分解が不定、負・非一様scaleは対象外。
        """
        axes = ("x", "y", "z")
        if pitchAxis not in axes or yawAxis not in axes or pitchAxis == yawAxis:
            raise ValueError("pitchAxis and yawAxis must be two different axes of x, y and z")
        if openDirection not in (1, -1):
            raise ValueError("openDirection must be 1 or -1")
        if not math.isfinite(softness) or not 0 <= softness <= 45:
            raise ValueError("softness must be between 0 and 45 degrees")
        slide = tuple(float(value) for value in slide)
        if len(slide) != 3 or not all(math.isfinite(value) for value in slide):
            raise ValueError("slide must be three finite values")
        if mlib.objExists(name):
            raise ValueError("JawHinge container already exists: " + name)
        jaw = mlib.nodes.Node(jaw)
        if not isinstance(jaw, mlib.nodes.Transform) or jaw.getParent() is None:
            raise ValueError("Expected a jaw transform with a parent transform")
        local = Matrix(jaw.getPlug("matrix").get()) * Matrix(jaw.getPlug("offsetParentMatrix").get())
        rest_rotation = local.quaternion.asMatrix()
        order = EyelidFollow.rotateOrder(pitchAxis, yawAxis)
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        scalar = ScalarGraph(owner)
        owner.addAttr(longName="softness", attributeType="double", defaultValue=softness,
                      minValue=0, maxValue=45, keyable=True)
        # mlibのaddAttrはdouble3の子(X/Y/Z)も作る。
        owner.addAttr(longName="slide", attributeType="double3")
        owner.getPlug("slide").set(slide)
        for attr in ("slideX", "slideY", "slideZ"):
            owner.setAttrFlags([attr], keyable=True)
        outputs = ("openAngle", "limitedOpen")
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        owner.addAttr(longName="slideOffset", attributeType="double3")
        owner.addAttr(longName="matrix", dataType="matrix")

        # 親空間での差分回転 D = J0^-1 * L を、Pitchを先・Yawを後に回すEuler角へ分解する。
        local_matrix = graph._node("multMatrix", "jawLocal")
        jaw.getPlug("matrix").connectTo(local_matrix.getPlug("matrixIn")[0])
        jaw.getPlug("offsetParentMatrix").connectTo(local_matrix.getPlug("matrixIn")[1])
        decompose = graph._node("decomposeMatrix", "jawDecompose")
        local_matrix.getPlug("matrixSum").connectTo(decompose.getPlug("inputMatrix"))
        rotation = graph._node("composeMatrix", "jawRotation")
        rotation.getPlug("useEulerRotation").set(False)
        decompose.getPlug("outputQuat").connectTo(rotation.getPlug("inputQuat"))
        delta = graph._node("multMatrix", "jawDelta")
        delta.getPlug("matrixIn")[0].set(rest_rotation.inverse())
        rotation.getPlug("outputMatrix").connectTo(delta.getPlug("matrixIn")[1])
        angles = graph._node("decomposeMatrix", "jawAngles")
        angles.getPlug("inputRotateOrder").set(order)
        delta.getPlug("matrixSum").connectTo(angles.getPlug("inputMatrix"))
        degrees = graph._node("unitConversion", "pitchDegrees")
        angles.getPlug("outputRotate" + pitchAxis.upper()).connectTo(degrees.getPlug("input"))
        degrees.getPlug("conversionFactor").set(180 / math.pi)
        opening = scalar.multiply("openAngleRaw", degrees.getPlug("output"), openDirection)
        opening.connectTo(owner.getPlug("openAngle"))

        # 閉じ側(a<0)だけ、-wへ指数関数的に近づける。開く側は通す。
        width = graph._node("clamp", "softWidth")
        width.getPlug("minR").set(cls.MINIMUM_SOFT_WIDTH)
        width.getPlug("maxR").set(45)
        owner.getPlug("softness").connectTo(width.getPlug("inputR"))
        width_plug = width.getPlug("outputR")
        # 開く側の大きな角度で累乗が発散しないよう、指数にはmin(a, 0)を使う。
        closing = scalar.condition("closingAngle", owner.getPlug("openAngle"), 0, 0, owner.getPlug("openAngle"))
        exponent = scalar.multiply("exponent", closing, width_plug, operation=2)
        decay = scalar.multiply("decay", math.e, exponent, operation=3)
        soft = scalar.sum("soft", scalar.multiply("softScaled", width_plug, decay), width_plug, subtract=True)
        limited = scalar.condition("limitedOpenRaw", owner.getPlug("openAngle"), 0, owner.getPlug("openAngle"),
                                   soft)
        limited.connectTo(owner.getPlug("limitedOpen"))

        # Pitchだけを制限後の角度へ置き換え、Yaw・Rollは入力のまま組み直す。
        rebuilt = graph._node("composeMatrix", "limitedDelta")
        rebuilt.getPlug("inputRotateOrder").set(order)
        pitch_degrees = scalar.multiply("limitedPitch", owner.getPlug("limitedOpen"), openDirection)
        radians = graph._node("unitConversion", "limitedPitchRadians")
        pitch_degrees.connectTo(radians.getPlug("input"))
        radians.getPlug("conversionFactor").set(math.pi / 180)
        radians.getPlug("output").connectTo(rebuilt.getPlug("inputRotate" + pitchAxis.upper()))
        for axis in axes:
            if axis != pitchAxis:
                angles.getPlug("outputRotate" + axis.upper()).connectTo(rebuilt.getPlug("inputRotate" + axis.upper()))
        result_rotation = graph._node("multMatrix", "resultRotation")
        result_rotation.getPlug("matrixIn")[0].set(rest_rotation)
        rebuilt.getPlug("outputMatrix").connectTo(result_rotation.getPlug("matrixIn")[1])
        quaternion = graph._node("decomposeMatrix", "resultQuaternion")
        result_rotation.getPlug("matrixSum").connectTo(quaternion.getPlug("inputMatrix"))

        # 開き角に比例した移動を、顎の現在位置へ足す。
        offset = graph._node("multiplyDivide", "slideOffsetRaw")
        owner.getPlug("slide").connectTo(offset.getPlug("input1"))
        for component in "XYZ":
            owner.getPlug("limitedOpen").connectTo(offset.getPlug("input2" + component))
        offset.getPlug("output").connectTo(owner.getPlug("slideOffset"))
        position = graph._node("plusMinusAverage", "position")
        decompose.getPlug("outputTranslate").connectTo(position.getPlug("input3D")[0])
        offset.getPlug("output").connectTo(position.getPlug("input3D")[1])
        result = graph._node("composeMatrix", "result")
        result.getPlug("useEulerRotation").set(False)
        quaternion.getPlug("outputQuat").connectTo(result.getPlug("inputQuat"))
        position.getPlug("output3D").connectTo(result.getPlug("inputTranslate"))
        result.getPlug("outputMatrix").connectTo(owner.getPlug("matrix"))
        owner.setAttrFlags(list(outputs), keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph
