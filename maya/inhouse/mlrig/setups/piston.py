"""シリンダーとロッドを互いへ向け、伸縮量とストローク超過を出力するピストンの標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.twistDistribution import TwistDistribution


class Piston(TwistDistribution):
    """油圧シリンダー・サスペンションのように、両端の部品が互いを向き続ける標準DG。

    両端の向きは標準の ``aimMatrix`` で求め、生成時の姿勢との差を保つため跳ねない。
    上方向は両端で共通の基準ベクトルに揃えるので、シリンダーとロッドがねじれずに同じ平面に乗る。
    """

    @classmethod
    def overStroke(cls, length, minimum, maximum):
        """両端の距離がストロークの範囲を超えた量を計算する。

        Args:
            length (float): 両端の現在の距離(cm)。
            minimum (float): 最も縮んだときの距離(cm)。
            maximum (float): 最も伸びたときの距離(cm)。

        Returns:
            float: 範囲内なら0、伸びすぎなら正、縮みすぎなら負の超過量(cm)。
        """
        return max(length - maximum, 0.0) - max(minimum - length, 0.0)

    @classmethod
    @undoTransaction("mlrig.Piston.create")
    def create(cls, base, tip, name="piston", aimAxis="x", upAxis="y", minimum=None, maximum=None):
        """シリンダー(base)とロッド(tip)の親空間行列を生成する。

        Args:
            base (str | Node): シリンダー側のtransform。回転中心を取り付け位置に置く。
            tip (str | Node): ロッド側のtransform。回転中心を取り付け位置に置く。
            name (str): 一意なcontainer名。
            aimAxis (str): 向きを求める基準の軸x/y/z。生成時の向きとの差だけを使うので、
                実際の部品の軸と一致していなくてもよい。
            upAxis (str): 上方向を揃える軸x/y/z。aimAxisと異なる。
            minimum (float | None): 最も縮んだときの両端の距離(cm)。Noneなら生成時の距離の0.5倍。
            maximum (float | None): 最も伸びたときの両端の距離(cm)。Noneなら生成時の距離の1.5倍。

        Returns:
            Piston: baseMatrix・tipMatrix・length・restLength・extension・overStrokeの所有者。

        Raises:
            ValueError: 軸・距離が不正な場合、両端が同じ位置にある場合、またはnameが既に存在する場合。

        Note:
            基準は生成時の姿勢。aimMatrixは、各端の現在のワールド行列を入力に、aimAxisを相手の位置へ向け、
            upAxisを共通の上方向(生成時のbaseのupAxisをbaseの親空間へ固定したもの)へ揃えた回転を返す。
            出力のワールド行列 = (生成時のワールド行列 * 生成時のaimMatrix出力^-1) * 現在のaimMatrix出力 を
            各端の親の空間へ戻したもの。位置は入力の現在位置のまま。
            length = 両端の距離、extension = length - restLength、
            overStroke = max(length-maximum, 0) - max(minimum-length, 0)(cm)。
            ストロークの範囲は出力の値だけで、両端の位置は制限しない。
            両端を結ぶ線が上方向と平行になると向きが不定、負・非一様scaleは対象外。
        """
        axes = ("x", "y", "z")
        if aimAxis not in axes or upAxis not in axes or aimAxis == upAxis:
            raise ValueError("aimAxis and upAxis must be two different axes of x, y and z")
        if mlib.objExists(name):
            raise ValueError("Piston container already exists: " + name)
        base, tip = mlib.nodes.Node(base), mlib.nodes.Node(tip)
        if base == tip or any(
            not isinstance(node, mlib.nodes.Transform) for node in (base, tip)
        ):
            raise ValueError("Expected two different transforms for the base and the tip")
        base_world = Matrix(base.getPlug("worldMatrix")[0].get())
        tip_world = Matrix(tip.getPlug("worldMatrix")[0].get())
        rest_length = (Vector(tip_world.translate) - Vector(base_world.translate)).length()
        if rest_length < 1e-6:
            raise ValueError("The base and the tip must be at different positions")
        minimum = rest_length * 0.5 if minimum is None else float(minimum)
        maximum = rest_length * 1.5 if maximum is None else float(maximum)
        if not (math.isfinite(minimum) and math.isfinite(maximum)) or not 0 <= minimum < maximum:
            raise ValueError("minimum and maximum must be finite and 0 <= minimum < maximum")
        # 共通の上方向: 生成時のbaseのupAxisを、baseの親空間(OPMを含む)のベクトルとして固定する。
        unit = Vector(*[float(axis == upAxis) for axis in axes])
        base_local = Matrix(base.getPlug("matrix").get())
        up = Vector(unit * base_local.quaternion.asMatrix())
        aim_axis = [float(axis == aimAxis) for axis in axes]
        up_axis = [float(axis == upAxis) for axis in axes]

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="restLength", attributeType="double", defaultValue=rest_length)
        owner.addAttr(longName="minimum", attributeType="double", defaultValue=minimum, minValue=0, keyable=True)
        owner.addAttr(longName="maximum", attributeType="double", defaultValue=maximum, minValue=0, keyable=True)
        outputs = ("length", "extension", "overStroke")
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        for attr in ("baseMatrix", "tipMatrix"):
            owner.addAttr(longName=attr, dataType="matrix")

        def aimFrame(role, node, target):
            """nodeの位置からtargetへaimAxisを向け、upAxisを共通の上方向へ揃えたワールド行列。"""
            aim = graph._node("aimMatrix", role + "Aim")
            node.getPlug("worldMatrix")[0].connectTo(aim.getPlug("inputMatrix"))
            target.getPlug("worldMatrix")[0].connectTo(aim.getPlug("primaryTargetMatrix"))
            aim.getPlug("primaryMode").set(1)
            aim.getPlug("primaryInputAxis").set(aim_axis)
            aim.getPlug("primaryTargetVector").set((0, 0, 0))
            aim.getPlug("secondaryMode").set(2)
            aim.getPlug("secondaryInputAxis").set(up_axis)
            aim.getPlug("secondaryTargetVector").set(up)
            base.getPlug("parentMatrix")[0].connectTo(aim.getPlug("secondaryTargetMatrix"))
            return aim.getPlug("outputMatrix")

        for role, node, target, rest_world, output in (
            ("base", base, tip, base_world, "baseMatrix"),
            ("tip", tip, base, tip_world, "tipMatrix"),
        ):
            frame = aimFrame(role, node, target)
            # 生成時の姿勢でのaimMatrix出力との差を定数で保ち、作成時に姿勢が跳ねないようにする。
            offset = rest_world * Matrix(frame.get()).inverse()
            world = graph._node("multMatrix", role + "World")
            world.getPlug("matrixIn")[0].set(offset)
            frame.connectTo(world.getPlug("matrixIn")[1])
            parent = node.getParent()
            if parent is not None:
                parent.getPlug("worldInverseMatrix")[0].connectTo(world.getPlug("matrixIn")[2])
            world.getPlug("matrixSum").connectTo(owner.getPlug(output))

        # 両端の距離(cm)。UIの長さ単位によらずcmで出力する。
        distance = graph._node("distanceBetween", "distance")
        base.getPlug("worldMatrix")[0].connectTo(distance.getPlug("inMatrix1"))
        tip.getPlug("worldMatrix")[0].connectTo(distance.getPlug("inMatrix2"))
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        centimeters = graph._node("unitConversion", "lengthCentimeters")
        conversions.add(centimeters.getUuid())
        distance.getPlug("distance").connectTo(centimeters.getPlug("input"))
        centimeters.getPlug("conversionFactor").set(1.0)
        centimeters.getPlug("output").connectTo(owner.getPlug("length"))
        delta = graph._node("plusMinusAverage", "extensionRaw")
        delta.getPlug("operation").set(2)
        owner.getPlug("length").connectTo(delta.getPlug("input1D")[0])
        owner.getPlug("restLength").connectTo(delta.getPlug("input1D")[1])
        delta.getPlug("output1D").connectTo(owner.getPlug("extension"))
        # overStroke = max(length - maximum, 0) - max(minimum - length, 0)
        over = graph._node("plusMinusAverage", "overRaw")
        over.getPlug("operation").set(2)
        owner.getPlug("length").connectTo(over.getPlug("input1D")[0])
        owner.getPlug("maximum").connectTo(over.getPlug("input1D")[1])
        under = graph._node("plusMinusAverage", "underRaw")
        under.getPlug("operation").set(2)
        owner.getPlug("minimum").connectTo(under.getPlug("input1D")[0])
        owner.getPlug("length").connectTo(under.getPlug("input1D")[1])
        positive = graph._node("clamp", "positiveParts")
        positive.getPlug("maxR").set(1e12)
        positive.getPlug("maxG").set(1e12)
        over.getPlug("output1D").connectTo(positive.getPlug("inputR"))
        under.getPlug("output1D").connectTo(positive.getPlug("inputG"))
        stroke = graph._node("plusMinusAverage", "overStrokeRaw")
        stroke.getPlug("operation").set(2)
        positive.getPlug("outputR").connectTo(stroke.getPlug("input1D")[0])
        positive.getPlug("outputG").connectTo(stroke.getPlug("input1D")[1])
        stroke.getPlug("output1D").connectTo(owner.getPlug("overStroke"))
        owner.setAttrFlags(list(outputs), keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph
