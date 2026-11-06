"""曲がった2本の軸の間で回転を等速に伝える等速ジョイント(ボール式のCVジョイント)の標準DGを構築する。"""

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

_AXES = ("x", "y", "z")


class ConstantVelocityJoint(TwistDistribution):
    """入力軸の回転を等速で出力軸へ伝え、出力軸とケージ(等速面)の行列・曲げ角を出力する標準DG。

    入力軸の向きを u、継手の中心から outputTarget への向きを v とする。ボール式の等速ジョイントは、ケージが
    ボールを両軸の二等分の面(等速面。h = normalize(u + v) に垂直な面)に保つことで、どの曲げ角でも入力と
    同じ角度だけ出力軸を回す。出力軸の向きは、u を v へ最短で回す回転(軸 u × v、角 β)を入力軸の向きに
    掛けたものになる。ケージの向きはその半分(u を h へ回す回転)を掛けたもの。UniversalJointと違い、
    1回転のうちの揺れ(角速度比の変化)は無い。
    """

    @classmethod
    @undoTransaction("mlrig.ConstantVelocityJoint.create")
    def create(cls, inputShaft, outputTarget, name="constantVelocityJoint", axis="x", atTarget=False):
        """inputShaftの回転を等速で伝えた出力軸の行列を生成する。

        Args:
            inputShaft (str | Node): 継手の中心に置いた入力軸のtransform。axis が軸。
            outputTarget (str | Node): 出力軸の先の点を表すtransform(位置だけを使う)。
            name (str): 一意なcontainer名。
            axis (str): 入力・出力の軸の向き x/y/z。
            atTarget (bool): Trueなら出力の行列の位置を outputTarget に置く(出力軸の先端)。
                Falseなら継手の中心(inputShaftの位置)。ケージの行列は常に継手の中心。

        Returns:
            ConstantVelocityJoint: matrix・cageMatrix・bendAngleの所有者。

        Raises:
            ValueError: 軸が不正な場合、inputShaft・outputTargetがtransformでない場合、同じノードの場合、
                またはnameが既に存在する場合。

        Note:
            c = inputShaftのワールド位置、R = inputShaftのワールド行列の回転(scale・shear・平行移動を除く)、
            u = R で回した axis、v = normalize(outputTargetの位置 - c)、h = normalize(u + v)。
            matrix = R × Q(u→v) に位置 c(atTargetでは outputTarget の位置)、cageMatrix = R × Q(u→h) に位置 c。
            Q(p→q) は標準の ``angleBetween`` の euler(p を q へ回す最短の回転)。scaleは1。
            bendAngle = β = u と v のなす角。matrix の axis は v、cageMatrix の axis は h を向き、
            ケージの残りの2軸がボールの並ぶ等速面を張る。入力軸を axis まわりに θ 回すと matrix も v まわりに θ 回る。
            β = 180 度(折り返し)では最短の回転の軸が決まらないため対象外(実物の可動域はおよそ45度まで)。
        """
        if axis not in _AXES:
            raise ValueError("axis must be one of x, y and z")
        if mlib.objExists(name):
            raise ValueError("ConstantVelocityJoint container already exists: " + name)
        inputShaft = mlib.Node(inputShaft)
        outputTarget = mlib.Node(outputTarget)
        for node in (inputShaft, outputTarget):
            if not isinstance(node, mlib.Transform):
                raise ValueError("Expected transforms for the input shaft and the output target")
        if inputShaft.getFullName() == outputTarget.getFullName():
            raise ValueError("inputShaft and outputTarget must be different nodes")
        shaft_axis = [float(item == axis) for item in _AXES]

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="bendAngle", attributeType="doubleAngle")
        for longName in ("matrix", "cageMatrix"):
            owner.addAttr(longName=longName, dataType="matrix")

        # 中心 c と出力軸の先の点 p、入力軸の回転 R
        shaftMatrix = inputShaft.getPlug("worldMatrix")[0]
        center = graph._node("decomposeMatrix", "center")
        shaftMatrix.connectTo(center.getPlug("inputMatrix"))
        target = graph._node("decomposeMatrix", "target")
        outputTarget.getPlug("worldMatrix")[0].connectTo(target.getPlug("inputMatrix"))
        c = center.getPlug("outputTranslate")
        p = target.getPlug("outputTranslate")
        rotation = graph._node("pickMatrix", "inputRotation")
        for flag in ("useTranslate", "useScale", "useShear"):
            rotation.getPlug(flag).set(False)
        shaftMatrix.connectTo(rotation.getPlug("inputMatrix"))

        # 入力軸 u(ワールド、長さ1)、出力軸 v = normalize(p - c)、二等分 h = normalize(u + v)
        u = graph._node("vectorProduct", "inputAxis")
        u.getPlug("operation").set(3)
        u.getPlug("normalizeOutput").set(True)
        u.getPlug("input1").set(shaft_axis)
        shaftMatrix.connectTo(u.getPlug("matrix"))
        offset = graph._node("plusMinusAverage", "outputOffset")
        offset.getPlug("operation").set(2)
        p.connectTo(offset.getPlug("input3D")[0])
        c.connectTo(offset.getPlug("input3D")[1])
        v = graph._node("vectorProduct", "outputAxis")
        v.getPlug("operation").set(0)
        v.getPlug("normalizeOutput").set(True)
        offset.getPlug("output3D").connectTo(v.getPlug("input1"))
        halfSum = graph._node("plusMinusAverage", "bisectorSum")
        u.getPlug("output").connectTo(halfSum.getPlug("input3D")[0])
        v.getPlug("output").connectTo(halfSum.getPlug("input3D")[1])
        h = graph._node("vectorProduct", "bisector")
        h.getPlug("operation").set(0)
        h.getPlug("normalizeOutput").set(True)
        halfSum.getPlug("output3D").connectTo(h.getPlug("input1"))

        # 最短の回転 Q(u→v)・Q(u→h) を入力の回転 R に掛ける(行ベクトルなので R × Q)。
        for direction, origin, label, output in ((v, p if atTarget else c, "output", "matrix"),
                                                 (h, c, "cage", "cageMatrix")):
            arc = graph._node("angleBetween", label + "Arc")
            u.getPlug("output").connectTo(arc.getPlug("vector1"))
            direction.getPlug("output").connectTo(arc.getPlug("vector2"))
            turn = graph._node("composeMatrix", label + "Turn")
            arc.getPlug("euler").connectTo(turn.getPlug("inputRotate"))
            origin.connectTo(turn.getPlug("inputTranslate"))
            frame = graph._node("multMatrix", label + "Frame")
            rotation.getPlug("outputMatrix").connectTo(frame.getPlug("matrixIn")[0])
            turn.getPlug("outputMatrix").connectTo(frame.getPlug("matrixIn")[1])
            frame.getPlug("matrixSum").connectTo(owner.getPlug(output))
            if label == "output":
                arc.getPlug("angle").connectTo(owner.getPlug("bendAngle"))

        owner.setAttrFlags(["bendAngle"], keyable=False, channelBox=True)
        return graph
