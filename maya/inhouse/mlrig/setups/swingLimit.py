"""ジョイントのSwingを楕円コーンの可動域へ柔らかく制限する。"""

import math

import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.swingTwist import SwingTwist


class SwingLimit(SwingTwist):
    """曲げ角を楕円の限界角へ指数関数で近づける標準DG。

    Twistは制限せず、Swingの回転軸を保ったまま角度だけを縮める。
    """

    #: 限界角の手前で柔らかく曲げ始める幅の下限(度)。softness=0の硬い制限に使う。
    MINIMUM_SOFT_WIDTH = 1e-3

    @staticmethod
    def perpendicularAxes(axis):
        """Twist軸に直交する2軸を右手系の順で返す。

        Args:
            axis (str): Twist軸x/y/z。

        Returns:
            tuple: (limit1の軸, limit2の軸)。例: xなら("y", "z")。
        """
        index = "xyz".index(axis)
        return "yzx"[index], "zxy"[index]

    @classmethod
    def limitAngle(cls, limit1, limit2, direction1, direction2):
        """曲げる向きに対する楕円コーンの限界角を計算する。

        Args:
            limit1 (float): limit1の軸側へ曲げたときの限界角(度)。
            limit2 (float): limit2の軸側へ曲げたときの限界角(度)。
            direction1 (float): 先端方向のlimit1軸成分。
            direction2 (float): 先端方向のlimit2軸成分。

        Returns:
            float: 限界角(度)。向きが定まらない場合はlimit1とlimit2の小さい方。
        """
        denominator = math.hypot(limit2 * direction1, limit1 * direction2)
        if denominator <= 1e-9:
            return min(limit1, limit2)
        return limit1 * limit2 * math.hypot(direction1, direction2) / denominator

    @classmethod
    def softAngle(cls, angle, limit, softness):
        """曲げ角を限界角へ柔らかく近づけた値を計算する。

        Args:
            angle (float): 基準姿勢からの曲げ角(度)。
            limit (float): 限界角(度)。
            softness (float): 限界角に対する柔らかい区間の割合。0〜1。

        Returns:
            float: 制限後の曲げ角(度)。limitを超えない。
        """
        width = max(softness * limit, cls.MINIMUM_SOFT_WIDTH)
        start = limit - width
        if angle <= start:
            return angle
        return start + width * (1 - math.exp(-(angle - start) / width))

    @classmethod
    @undoTransaction("mlrig.SwingLimit.create")
    def create(cls, joint, name="swingLimit", axis="x", limit1=60.0, limit2=30.0, softness=0.2):
        """親空間での可動域制限済みの行列を生成する。

        Args:
            joint (str | Node): 親transformを持つjoint。
            name (str): 一意なcontainer名。
            axis (str): 基準姿勢での骨の長手(Twist)軸x/y/z。
            limit1 (float): ``perpendicularAxes(axis)[0]`` の軸側へ曲げる限界角。度、0より大きく179以下。
            limit2 (float): ``perpendicularAxes(axis)[1]`` の軸側へ曲げる限界角。度、0より大きく179以下。
            softness (float): 限界角に対する柔らかい区間の割合。0で硬い制限、1で0度から緩める。

        Returns:
            SwingLimit: matrix・restMatrix・swingAngle・limitAngle・limitedAngle・excessAngle・ratioの所有者。

        Raises:
            ValueError: 軸・角度・softnessが範囲外の場合。

        Note:
            基準は生成時の姿勢。曲げ角θは基準の長手軸と現在の長手軸のなす角。
            楕円の限界角 L = l1*l2*r / sqrt((l2*c)^2 + (l1*s)^2)。c・sは先端方向の直交2軸成分、r=sqrt(c^2+s^2)。
            制限後の角度は w=max(softness*L, 0.001)、start=L-wとして、θ<=startならθ、
            それ以外はstart + w*(1-exp(-(θ-start)/w))。SwingをQuaternionで ratio=制限後/θ だけ補間する。
            excessAngle = θ - 制限後の角度(0以上)。
            位置は入力の現在位置、Twistは入力のまま。scale・shearは出力しない。
            180度付近の曲げはSwingの向きが不定、負・非一様scaleは対象外。
        """
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be x, y or z")
        for value in (limit1, limit2):
            if not math.isfinite(value) or not 0 < value <= 179:
                raise ValueError("limit angles must be greater than 0 and at most 179 degrees")
        cls._checkSoftness(softness)
        return cls._build(joint, name, axis, (("limit1", limit1), ("limit2", limit2)), softness)

    @staticmethod
    def _checkSoftness(softness):
        """softnessが0〜1の有限値か検査する。"""
        if not math.isfinite(softness) or not 0 <= softness <= 1:
            raise ValueError("softness must be between 0 and 1")

    @classmethod
    def _limitGraph(cls, scalar, owner, c, s):
        """曲げる向きの成分c・sから楕円の限界角Lを求めるDGを作る。

        Args:
            scalar (ScalarGraph): ノードを作るヘルパー。
            owner (Node): 限界角のアトリビュートを持つcontainer。
            c (Plug): 先端方向のlimit1軸成分。
            s (Plug): 先端方向のlimit2軸成分。

        Returns:
            Plug: 限界角(度)。
        """
        l1, l2 = owner.getPlug("limit1"), owner.getPlug("limit2")
        smaller = scalar.condition("smallerLimit", l1, l2, l2, l1)
        return cls._ellipseGraph(scalar, l1, l2, c, s, smaller)

    @staticmethod
    def _ellipseGraph(scalar, l1, l2, c, s, fallback):
        """L = l1*l2*r / sqrt((l2*c)^2 + (l1*s)^2) を作る。向きが定まらなければfallback。"""
        term1 = scalar.multiply("term1", l2, c)
        term2 = scalar.multiply("term2", l1, s)
        squared = scalar.sum(
            "denominatorSquared",
            scalar.multiply("term1Squared", term1, term1),
            scalar.multiply("term2Squared", term2, term2),
        )
        denominator = scalar.multiply("denominator", squared, 0.5, operation=3)
        radius = scalar.multiply(
            "radius",
            scalar.sum("radiusSquared", scalar.multiply("cSquared", c, c), scalar.multiply("sSquared", s, s)),
            0.5, operation=3,
        )
        numerator = scalar.multiply("numerator", scalar.multiply("limitProduct", l1, l2), radius)
        safe_denominator = scalar.condition("safeDenominator", denominator, 1e-9, denominator, 1)
        ellipse = scalar.multiply("ellipse", numerator, safe_denominator, operation=2)
        return scalar.condition("limit", denominator, 1e-9, ellipse, fallback)

    @classmethod
    def _build(cls, joint, name, axis, limits, softness):
        """検査済みの引数でグラフを作る。

        Args:
            joint (str | Node): 親transformを持つjoint。
            name (str): 一意なcontainer名。
            axis (str): Twist軸x/y/z。
            limits (tuple): (アトリビュート名, 限界角)の組。``_limitGraph`` が読む。
            softness (float): 柔らかい区間の割合。

        Returns:
            SwingLimit: 生成したグラフ。
        """
        joint = mlib.nodes.Node(joint)
        rest = Matrix(joint.getPlug("matrix").get()) * Matrix(joint.getPlug("offsetParentMatrix").get())
        rest_rotation = rest.quaternion.asMatrix()
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        base = SwingTwist.create(joint, name=name, axis=axis)
        graph = cls(base.container)
        owner = graph.container
        scalar = ScalarGraph(owner)
        for attr, value in limits:
            owner.addAttr(longName=attr, attributeType="double", defaultValue=value,
                          minValue=0.001, maxValue=179, keyable=True)
        owner.addAttr(longName="softness", attributeType="double", defaultValue=softness,
                      minValue=0, maxValue=1, keyable=True)
        outputs = ("swingAngle", "limitAngle", "limitedAngle", "excessAngle", "ratio")
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        for attr in ("matrix", "restMatrix", "limitedSwingMatrix"):
            owner.addAttr(longName=attr, dataType="matrix")

        # 基準の長手軸をSwingで回し、先端方向と曲げ角θ(度)を求める。
        unit = [float(name_ == axis) for name_ in "xyz"]
        tip = graph._node("vectorProduct", "tipDirection")
        tip.getPlug("operation").set(3)
        tip.getPlug("normalizeOutput").set(True)
        tip.getPlug("input1").set(unit)
        owner.getPlug("swingMatrix").connectTo(tip.getPlug("matrix"))
        bend = graph._node("angleBetween", "bendAngle")
        bend.getPlug("vector1").set(unit)
        tip.getPlug("output").connectTo(bend.getPlug("vector2"))
        degrees = graph._node("unitConversion", "bendDegrees")
        bend.getPlug("angle").connectTo(degrees.getPlug("input"))
        degrees.getPlug("conversionFactor").set(180 / math.pi)
        angle = degrees.getPlug("output")
        angle.connectTo(owner.getPlug("swingAngle"))

        # 楕円の限界角。向きが定まらないほど小さい曲げでは小さい方の限界角を使う。
        first, second = cls.perpendicularAxes(axis)
        c = tip.getPlug("output" + first.upper())
        s = tip.getPlug("output" + second.upper())
        limit = cls._limitGraph(scalar, owner, c, s)
        limit.connectTo(owner.getPlug("limitAngle"))

        # Soft IKと同じ指数関数で、θがstartを超えた分をlimitへ漸近させる。
        raw_width = scalar.multiply("softWidthRaw", owner.getPlug("softness"), limit)
        width = scalar.condition("softWidth", raw_width, cls.MINIMUM_SOFT_WIDTH, raw_width, cls.MINIMUM_SOFT_WIDTH)
        start = scalar.sum("softStart", limit, width, subtract=True)
        excess = scalar.sum("excess", angle, start, subtract=True)
        positive = scalar.condition("positiveExcess", excess, 0, excess, 0)
        exponent = scalar.multiply("exponent", positive, width, operation=2)
        decay = scalar.multiply("decay", math.exp(-1), exponent, operation=3)
        falloff = scalar.sum("falloff", 1, decay, subtract=True)
        softened = scalar.sum("softened", start, scalar.multiply("softRange", width, falloff))
        limited = scalar.condition("limited", excess, 0, softened, angle)
        limited.connectTo(owner.getPlug("limitedAngle"))
        # 制限で削った角度。補正シェイプ等のドライバーに使う。
        scalar.sum("excessAngleRaw", angle, limited, subtract=True).connectTo(owner.getPlug("excessAngle"))

        # 曲げ角がほぼ0なら比率を1に固定し、0除算を避ける。
        safe_angle = scalar.condition("safeAngle", angle, 1e-4, angle, 1)
        safe_limited = scalar.condition("safeLimited", angle, 1e-4, limited, 1)
        ratio = scalar.multiply("ratioRaw", safe_limited, safe_angle, operation=2)
        ratio.connectTo(owner.getPlug("ratio"))

        blend = graph._node("blendMatrix", "limitedSwing")
        owner.getPlug("swingMatrix").connectTo(blend.getPlug("target")[0]["targetMatrix"])
        ratio.connectTo(blend.getPlug("target")[0]["weight"])
        # Maya 2022はbool、2025以降は連続ウェイトで成分を選択する。
        attrs = (
            ("translateWeight", "scaleWeight", "shearWeight")
            if blend.hasAttr("target[0].translateWeight")
            else ("useTranslate", "useScale", "useShear")
        )
        for attr in attrs:
            blend.getPlug("target")[0][attr].set(0)
        blend.getPlug("outputMatrix").connectTo(owner.getPlug("limitedSwingMatrix"))

        # 行ベクトル規約: twist * swing * 基準回転 = 親空間の回転。
        orient = graph._node("multMatrix", "limitedRotation")
        owner.getPlug("twistMatrix").connectTo(orient.getPlug("matrixIn")[0])
        blend.getPlug("outputMatrix").connectTo(orient.getPlug("matrixIn")[1])
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
