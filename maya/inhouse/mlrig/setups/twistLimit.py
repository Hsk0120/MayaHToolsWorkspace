"""ジョイントのTwistを非対称な可動域へ柔らかく制限する。"""

import math

import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.swingTwist import SwingTwist


class TwistLimit(SwingTwist):
    """Twist角を下限・上限へ指数関数で近づける標準DG。

    Swingは制限せず、長手軸まわりの回転角だけを縮める。
    """

    #: 限界角の手前で柔らかく曲げ始める幅の下限(度)。softness=0の硬い制限に使う。
    MINIMUM_SOFT_WIDTH = 1e-3

    @classmethod
    def softWidth(cls, minimum, maximum, softness):
        """柔らかい区間の幅を計算する。

        Args:
            minimum (float): 下限角(度)。
            maximum (float): 上限角(度)。
            softness (float): 可動域の半分に対する柔らかい区間の割合。0〜1。

        Returns:
            float: 幅(度)。MINIMUM_SOFT_WIDTH以上。
        """
        return max(softness * (maximum - minimum) * 0.5, cls.MINIMUM_SOFT_WIDTH)

    @classmethod
    def softTwist(cls, angle, minimum, maximum, softness):
        """Twist角を下限・上限の内側へ柔らかく近づけた値を計算する。

        Args:
            angle (float): 基準姿勢からのTwist角(度)。
            minimum (float): 下限角(度)。
            maximum (float): 上限角(度)。
            softness (float): 可動域の半分に対する柔らかい区間の割合。0〜1。

        Returns:
            float: 制限後のTwist角(度)。minimum〜maximumの範囲。
        """
        width = cls.softWidth(minimum, maximum, softness)
        upper = maximum - width
        lower = minimum + width
        if angle > upper:
            return upper + width * (1 - math.exp(-(angle - upper) / width))
        if angle < lower:
            return lower - width * (1 - math.exp(-(lower - angle) / width))
        return angle

    @classmethod
    @undoTransaction("mlrig.TwistLimit.create")
    def create(cls, joint, name="twistLimit", axis="x", minimum=-45.0, maximum=45.0, softness=0.2):
        """親空間でTwistを制限した行列を生成する。

        Args:
            joint (str | Node): 親transformを持つjoint。
            name (str): 一意なcontainer名。
            axis (str): 基準姿勢での骨の長手(Twist)軸x/y/z。
            minimum (float): Twistの下限角。度、-179以上でmaximum未満。
            maximum (float): Twistの上限角。度、179以下。
            softness (float): 可動域の半分に対する柔らかい区間の割合。0で硬い制限、1で中央から緩める。

        Returns:
            TwistLimit: matrix・restMatrix・limitedTwistMatrix・limitedTwist・excessTwistの所有者。

        Raises:
            ValueError: 軸・角度・softnessが範囲外の場合。

        Note:
            基準は生成時の姿勢。Twist角tはSwingTwistの符号付きtwist(-180〜180度)。
            w=max(softness*(max-min)/2, 0.001)、hi=max-w、lo=min+w として、
            t>hiなら hi + w*(1-exp(-(t-hi)/w))、t<loなら lo - w*(1-exp(-(lo-t)/w))、それ以外はt。
            制限後の角度で長手軸まわりの回転を作り直し、twist * swing * 基準回転とする。
            位置は入力の現在位置、Swingは入力のまま。scale・shearは出力しない。
            入力Twistが±180度をまたぐと符号が反転するため、そこでは連続しない。
        """
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be x, y or z")
        for value in (minimum, maximum, softness):
            if not math.isfinite(value):
                raise ValueError("limit angles and softness must be finite")
        if not -179 <= minimum < maximum <= 179:
            raise ValueError("limits must satisfy -179 <= minimum < maximum <= 179 degrees")
        if not 0 <= softness <= 1:
            raise ValueError("softness must be between 0 and 1")
        joint = mlib.nodes.Node(joint)
        rest = Matrix(joint.getPlug("matrix").get()) * Matrix(joint.getPlug("offsetParentMatrix").get())
        rest_rotation = rest.quaternion.asMatrix()
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        base = SwingTwist.create(joint, name=name, axis=axis)
        graph = cls(base.container)
        owner = graph.container
        scalar = ScalarGraph(owner)
        for attr, value in (("minimum", minimum), ("maximum", maximum)):
            owner.addAttr(longName=attr, attributeType="double", defaultValue=value,
                          minValue=-179, maxValue=179, keyable=True)
        owner.addAttr(longName="softness", attributeType="double", defaultValue=softness,
                      minValue=0, maxValue=1, keyable=True)
        outputs = ("limitedTwist", "excessTwist")
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        for attr in ("matrix", "restMatrix", "limitedTwistMatrix"):
            owner.addAttr(longName=attr, dataType="matrix")

        # 可動域の半分×softnessを柔らかい区間の幅とし、上下の開始角を求める。
        twist = owner.getPlug("twist")
        span = scalar.sum("span", owner.getPlug("maximum"), owner.getPlug("minimum"), subtract=True)
        raw_width = scalar.multiply("softWidthRaw", scalar.multiply("halfSpan", span, 0.5), owner.getPlug("softness"))
        width = scalar.condition("softWidth", raw_width, cls.MINIMUM_SOFT_WIDTH, raw_width, cls.MINIMUM_SOFT_WIDTH)
        upper = scalar.sum("upperStart", owner.getPlug("maximum"), width, subtract=True)
        lower = scalar.sum("lowerStart", owner.getPlug("minimum"), width)

        def falloff(role, excess):
            """開始角からの超過量 e を w*(1-exp(-e/w)) へ変換する。"""
            positive = scalar.condition(role + "Positive", excess, 0, excess, 0)
            exponent = scalar.multiply(role + "Exponent", positive, width, operation=2)
            decay = scalar.multiply(role + "Decay", math.exp(-1), exponent, operation=3)
            return scalar.multiply(role + "Range", width, scalar.sum(role + "Falloff", 1, decay, subtract=True))

        upper_excess = scalar.sum("upperExcess", twist, upper, subtract=True)
        lower_excess = scalar.sum("lowerExcess", lower, twist, subtract=True)
        upper_soft = scalar.sum("upperSoft", upper, falloff("upper", upper_excess))
        lower_soft = scalar.sum("lowerSoft", lower, falloff("lower", lower_excess), subtract=True)
        inner = scalar.condition("lowerLimited", lower_excess, 0, lower_soft, twist)
        limited = scalar.condition("limited", upper_excess, 0, upper_soft, inner)
        limited.connectTo(owner.getPlug("limitedTwist"))
        scalar.sum("excess", twist, limited, subtract=True).connectTo(owner.getPlug("excessTwist"))

        # 制限後の角度(度→ラジアン)で長手軸まわりの回転行列を作る。
        radians = graph._node("unitConversion", "limitedRadians")
        radians.getPlug("conversionFactor").set(math.pi / 180)
        limited.connectTo(radians.getPlug("input"))
        twist_matrix = graph._node("composeMatrix", "limitedTwist")
        radians.getPlug("output").connectTo(twist_matrix.getPlug("inputRotate" + axis.upper()))
        twist_matrix.getPlug("outputMatrix").connectTo(owner.getPlug("limitedTwistMatrix"))

        # 行ベクトル規約: twist * swing * 基準回転 = 親空間の回転。
        orient = graph._node("multMatrix", "limitedRotation")
        twist_matrix.getPlug("outputMatrix").connectTo(orient.getPlug("matrixIn")[0])
        owner.getPlug("swingMatrix").connectTo(orient.getPlug("matrixIn")[1])
        orient.getPlug("matrixIn")[2].set(rest_rotation)
        relative = graph._node("multMatrix", "sourceLocal")
        joint.getPlug("matrix").connectTo(relative.getPlug("matrixIn")[0])
        joint.getPlug("offsetParentMatrix").connectTo(relative.getPlug("matrixIn")[1])
        position = graph._node("decomposeMatrix", "sourcePosition")
        relative.getPlug("matrixSum").connectTo(position.getPlug("inputMatrix"))
        rotation = graph._node("decomposeMatrix", "resultRotation")
        orient.getPlug("matrixSum").connectTo(rotation.getPlug("inputMatrix"))
        result = graph._node("composeMatrix", "result")
        result.getPlug("useEulerRotation").set(False)
        rotation.getPlug("outputQuat").connectTo(result.getPlug("inputQuat"))
        position.getPlug("outputTranslate").connectTo(result.getPlug("inputTranslate"))
        result.getPlug("outputMatrix").connectTo(owner.getPlug("matrix"))
        owner.getPlug("restMatrix").set(Matrix.compose(translate=rest.translate, rotate=rest.quaternion))
        owner.setAttrFlags(list(outputs), keyable=False, channelBox=True)
        extra = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if extra:
            mlib.nodes.Container(owner).addMembers(*extra)
        return graph
