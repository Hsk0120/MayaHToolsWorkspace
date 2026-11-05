"""曲がった2本の軸の間で回転を伝えるユニバーサルジョイント(カルダン継手・十字軸継手)の標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

# 角速度比の分母 cos²β + (a・(u×v))² の下限。曲げ角90度でピンが曲げ平面にあるときの0除算を避ける。
_MIN_DENOMINATOR = 1e-9
_AXES = ("x", "y", "z")


class UniversalJoint(TwistDistribution):
    """入力軸の回転を十字軸で出力軸へ伝え、出力軸の行列・曲げ角・角速度比を出力する標準DG。

    入力軸の向きを u、入力ヨークのピンを a(u に垂直)、継手の中心から outputTarget への向きを v とする。
    十字軸のもう一方のピン(出力ヨークのピン)は a と v の両方に垂直な b = a × v で、出力軸の基準の向きは
    v × b = a - v(v・a)、つまり a を v に垂直な面へ射影した向きになる。出力の行列はこの向きを標準の
    ``aimMatrix`` で組む(axis を v へ向け、pinAxis を a へ揃える)。まっすぐのときは入力と同じ向き。
    曲げ平面から測った入力ヨークの角度を γ1、曲げ角を β とすると、出力の角度は tan γ2 = tan γ1 / cos β で、
    出力軸は1回転のうちに cos β 倍から 1/cos β 倍の速さで揺れる。
    """

    @classmethod
    def outputAngle(cls, inputAngle, bendAngle):
        """入力ヨークの角度から出力ヨークの角度を計算する。

        Args:
            inputAngle (float): 曲げ平面から測った入力ヨークのピンの角度 γ1(度)。
            bendAngle (float): 入力軸と出力軸のなす角 β(度、0以上90未満)。

        Returns:
            float: 出力軸で同じ基準から測った出力ヨークの角度 γ2(度)。tan γ2 = tan γ1 / cos β で、
            γ1 と同じ周(-180〜180度の連続な枝)の値。
        """
        gamma = math.radians(inputAngle)
        beta = math.radians(bendAngle)
        return math.degrees(math.atan2(math.sin(gamma), math.cos(gamma) * math.cos(beta)))

    @classmethod
    def speedRatio(cls, inputAngle, bendAngle):
        """出力軸と入力軸の角速度の比を計算する。

        Args:
            inputAngle (float): 曲げ平面から測った入力ヨークのピンの角度 γ1(度)。
            bendAngle (float): 入力軸と出力軸のなす角 β(度、0以上90未満)。

        Returns:
            float: ω2 / ω1 = cos β / (1 - sin²β cos²γ1)。cos β 以上 1/cos β 以下。
        """
        gamma = math.radians(inputAngle)
        beta = math.radians(bendAngle)
        return math.cos(beta) / (1.0 - math.sin(beta) ** 2 * math.cos(gamma) ** 2)

    @classmethod
    @undoTransaction("mlrig.UniversalJoint.create")
    def create(cls, inputShaft, outputTarget, name="universalJoint", axis="x", pinAxis="y", atTarget=False):
        """inputShaftの回転を十字軸で伝えた出力軸の行列を生成する。

        Args:
            inputShaft (str | Node): 継手の中心に置いた入力軸のtransform。axis が軸、pinAxis が入力ヨークのピン。
            outputTarget (str | Node): 出力軸の先の点を表すtransform(位置だけを使う)。
            name (str): 一意なcontainer名。
            axis (str): 入力・出力の軸の向き x/y/z。
            pinAxis (str): 入力ヨークのピンの向き x/y/z。axisと異なる。出力の行列でもこの軸を射影したピンへ揃える。
            atTarget (bool): Trueなら出力の行列の位置を outputTarget に置く(直列にしたときの中間軸の先端)。
                Falseなら継手の中心(inputShaftの位置)。

        Returns:
            UniversalJoint: matrix・bendAngle・speedRatio・pinTwistの所有者。

        Raises:
            ValueError: 軸が不正な場合、inputShaft・outputTargetがtransformでない場合、同じノードの場合、
                またはnameが既に存在する場合。

        Note:
            c = inputShaftのワールド位置、u・a = inputShaftのワールド行列で回した axis・pinAxis(長さ1)、
            v = normalize(outputTargetの位置 - c)。matrix は標準の ``aimMatrix`` で axis を v へ向け、
            pinAxis を a へ揃えた行列(scaleは1)。atTarget では位置を outputTarget に置き、-axis を c へ向ける
            (向きは同じ)。bendAngle = β = u と v のなす角、pinTwist = a・(u × v)(= sin β sin γ1)、
            speedRatio = cos β / (cos²β + pinTwist²)(= cos β / (1 - sin²β cos²γ1)、分母の下限は1e-9)。
            中間軸の先端のヨークのピンは matrix の残りの軸(axis × pinAxis の向き)と平行なので、
            2つ目の継手の pinAxis にその軸を指定すると位相が揃い、2つの曲げ角が等しければ等速になる。
            β = 90 度ではロックし(cos β = 0)、a と v が平行で出力のピンの向きが決まらない。90度を超える曲げは対象外。
        """
        if axis not in _AXES or pinAxis not in _AXES or axis == pinAxis:
            raise ValueError("axis and pinAxis must be two different axes of x, y and z")
        if mlib.objExists(name):
            raise ValueError("UniversalJoint container already exists: " + name)
        inputShaft = mlib.Node(inputShaft)
        outputTarget = mlib.Node(outputTarget)
        for node in (inputShaft, outputTarget):
            if not isinstance(node, mlib.Transform):
                raise ValueError("Expected transforms for the input shaft and the output target")
        if inputShaft.getFullName() == outputTarget.getFullName():
            raise ValueError("inputShaft and outputTarget must be different nodes")
        shaft_axis = [float(item == axis) for item in _AXES]
        pin_axis = [float(item == pinAxis) for item in _AXES]

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="bendAngle", attributeType="doubleAngle")
        for longName in ("speedRatio", "pinTwist"):
            owner.addAttr(longName=longName, attributeType="double")
        owner.addAttr(longName="matrix", dataType="matrix")

        # 中心 c と出力軸の先の点 p
        shaftMatrix = inputShaft.getPlug("worldMatrix")[0]
        center = graph._node("decomposeMatrix", "center")
        shaftMatrix.connectTo(center.getPlug("inputMatrix"))
        target = graph._node("decomposeMatrix", "target")
        outputTarget.getPlug("worldMatrix")[0].connectTo(target.getPlug("inputMatrix"))
        c = center.getPlug("outputTranslate")
        p = target.getPlug("outputTranslate")

        # 入力軸 u・入力ヨークのピン a(ワールド、長さ1)と、出力軸 v = normalize(p - c)
        u = graph._node("vectorProduct", "inputAxis")
        a = graph._node("vectorProduct", "inputPin")
        for node, vector in ((u, shaft_axis), (a, pin_axis)):
            node.getPlug("operation").set(3)
            node.getPlug("normalizeOutput").set(True)
            node.getPlug("input1").set(vector)
            shaftMatrix.connectTo(node.getPlug("matrix"))
        offset = graph._node("plusMinusAverage", "outputOffset")
        offset.getPlug("operation").set(2)
        p.connectTo(offset.getPlug("input3D")[0])
        c.connectTo(offset.getPlug("input3D")[1])
        v = graph._node("vectorProduct", "outputAxis")
        v.getPlug("operation").set(0)
        v.getPlug("normalizeOutput").set(True)
        offset.getPlug("output3D").connectTo(v.getPlug("input1"))

        # β = angle(u, v)、cos β = u・v、pinTwist = a・(u × v)
        bend = graph._node("angleBetween", "bendAngle")
        u.getPlug("output").connectTo(bend.getPlug("vector1"))
        v.getPlug("output").connectTo(bend.getPlug("vector2"))
        bend.getPlug("angle").connectTo(owner.getPlug("bendAngle"))
        cosine = graph._node("vectorProduct", "cosBend")
        cosine.getPlug("operation").set(1)
        u.getPlug("output").connectTo(cosine.getPlug("input1"))
        v.getPlug("output").connectTo(cosine.getPlug("input2"))
        normal = graph._node("vectorProduct", "bendNormal")
        normal.getPlug("operation").set(2)
        u.getPlug("output").connectTo(normal.getPlug("input1"))
        v.getPlug("output").connectTo(normal.getPlug("input2"))
        twist = graph._node("vectorProduct", "pinTwist")
        twist.getPlug("operation").set(1)
        a.getPlug("output").connectTo(twist.getPlug("input1"))
        normal.getPlug("output").connectTo(twist.getPlug("input2"))
        twist.getPlug("outputX").connectTo(owner.getPlug("pinTwist"))

        # speedRatio = cos β / max(cos²β + pinTwist², 1e-9)
        squared = graph._node("multiplyDivide", "squared")
        cosine.getPlug("outputX").connectTo(squared.getPlug("input1X"))
        cosine.getPlug("outputX").connectTo(squared.getPlug("input2X"))
        twist.getPlug("outputX").connectTo(squared.getPlug("input1Y"))
        twist.getPlug("outputX").connectTo(squared.getPlug("input2Y"))
        denominator = graph._node("plusMinusAverage", "denominator")
        squared.getPlug("outputX").connectTo(denominator.getPlug("input1D")[0])
        squared.getPlug("outputY").connectTo(denominator.getPlug("input1D")[1])
        safe = graph._node("clamp", "safeDenominator")
        safe.getPlug("minR").set(_MIN_DENOMINATOR)
        safe.getPlug("maxR").set(1e9)
        denominator.getPlug("output1D").connectTo(safe.getPlug("inputR"))
        ratio = graph._node("multiplyDivide", "speedRatio")
        ratio.getPlug("operation").set(2)
        cosine.getPlug("outputX").connectTo(ratio.getPlug("input1X"))
        safe.getPlug("outputR").connectTo(ratio.getPlug("input2X"))
        ratio.getPlug("outputX").connectTo(owner.getPlug("speedRatio"))

        # 向き: axis を v へ向け(atTargetでは -axis を中心へ向け)、pinAxis を a へ揃える。
        origin = graph._node("composeMatrix", "origin")
        (p if atTarget else c).connectTo(origin.getPlug("inputTranslate"))
        aimAt = graph._node("composeMatrix", "aimAt")
        (c if atTarget else p).connectTo(aimAt.getPlug("inputTranslate"))
        frame = graph._node("aimMatrix", "frame")
        origin.getPlug("outputMatrix").connectTo(frame.getPlug("inputMatrix"))
        aimAt.getPlug("outputMatrix").connectTo(frame.getPlug("primaryTargetMatrix"))
        frame.getPlug("primaryMode").set(1)
        frame.getPlug("primaryInputAxis").set([-value for value in shaft_axis] if atTarget else shaft_axis)
        frame.getPlug("primaryTargetVector").set((0, 0, 0))
        frame.getPlug("secondaryMode").set(2)
        frame.getPlug("secondaryInputAxis").set(pin_axis)
        frame.getPlug("secondaryTargetVector").set(pin_axis)
        shaftMatrix.connectTo(frame.getPlug("secondaryTargetMatrix"))
        frame.getPlug("outputMatrix").connectTo(owner.getPlug("matrix"))

        owner.setAttrFlags(["bendAngle", "speedRatio", "pinTwist"], keyable=False, channelBox=True)
        return graph
