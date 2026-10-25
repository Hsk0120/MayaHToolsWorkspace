"""2関節の腕・脚の長さを、合計を保ったまま上下へ振り分ける slide と、中間の関節を極ベクトルの操作子へ留める pin を標準DGで作る。"""

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

_AXES = ("x", "y", "z")


class LimbPin(TwistDistribution):
    """2関節の長さ(付け根→中間、中間→先端)を slide と pin で書き換える標準DG。

    IKの解き方には手を入れず、中間と先端のjointの骨の向きの translate だけを駆動するので、
    Maya標準の ikRPsolver と poleVectorConstraint の腕・脚へそのまま足せる。
    slide は合計の長さを保ったまま上腕と前腕(太ももとすね)の比を変え、pin=1 では
    上の長さ=付け根から極ベクトルの操作子まで、下の長さ=極ベクトルの操作子からIKの目標までになるので、
    同じ操作子を極ベクトルにしたIKでは肘・膝がちょうど操作子の位置へ来る(肘を机に、膝を床に留める)。
    """

    @classmethod
    @undoTransaction("mlrig.LimbPin.create")
    def create(cls, start, mid, end, pole, target, name="limbPin", axis="x", slide=0.0, pin=0.0):
        """付け根・中間・先端のjointと、極ベクトルの操作子・IKの目標から長さの網を作る。

        Args:
            start (str | Node): 付け根のjoint(肩・股)。scale 1 を前提とする。
            mid (str | Node): 中間のjoint(肘・膝)。``start`` の子で、``axis`` の向きに離れている。scale 1 を前提とする。
            end (str | Node): 先端のjoint(手首・足首)。``mid`` の子で、``axis`` の向きに離れている。
            pole (str | Node): pin の留め先にするtransform(極ベクトルの操作子)。
            target (str | Node): IKの目標にするtransform(IKハンドルの親の操作子など)。
            name (str): 一意なcontainer名。
            axis (str): 骨の向きのtranslateの軸(``"x"``・``"y"``・``"z"``)。作成時の値の符号を保つ。
            slide (float): slide の初期値(-1〜1)。正で上が長く、1で下の長さが0。負で下が長く、-1で上の長さが0。
            pin (float): pin の初期値(0〜1)。

        Returns:
            LimbPin: slide・pin(keyable)、restUpper・restLower(作成時の長さ、cm)、
            upperLength・lowerLength(出力の長さ)の所有者。

        Raises:
            ValueError: 引数が不正な場合、親子の関係が違う場合、作成時の長さが0の場合、
                またはnameが既に存在する場合。

        Note:
            付け根の親の空間(``start`` の parentInverseMatrix)で、付け根の位置 R(``start`` の translate)、
            操作子の位置 P、目標の位置 T を求め、d1=|P-R|、d2=|T-P| とする。作成時の長さを U0・L0 として、
            slide s で δ = s·L0 (s≥0)、s·U0 (s<0)、U' = U0+δ、L' = L0-δ(U'+L' = U0+L0)。
            pin w で U = U'+w(d1-U')、L = L'+w(d2-L')。中間・先端のjointの translate の ``axis`` へ、
            作成時の符号を掛けた U・L を入れる。付け根の回転には依存しない(IKとの循環が無い)。
            UI単位がmmでも自動の単位変換が入らないよう、長さの受け渡しは係数1の unitConversion で行う。
        """
        if mlib.ls(name):
            raise ValueError("LimbPin container already exists: " + name)
        if axis not in _AXES:
            raise ValueError("Expected 'x', 'y' or 'z' for the axis")
        slide, pin = float(slide), float(pin)
        if not -1.0 <= slide <= 1.0 or not 0.0 <= pin <= 1.0:
            raise ValueError("Expected -1 to 1 for the slide and 0 to 1 for the pin")
        joints = []
        for node in (start, mid, end):
            joint = mlib.nodes.Node(node)
            if not isinstance(joint, mlib.nodes.Joint):
                raise ValueError("Expected joints for the start, the mid and the end")
            joints.append(joint)
        start, mid, end = joints
        if len({joint.getUuid() for joint in joints}) != 3:
            raise ValueError("The start, the mid and the end must be different joints")
        for child, parent in ((mid, start), (end, mid)):
            above = child.getParent()
            if above is None or above.getUuid() != parent.getUuid():
                raise ValueError("Expected the chain start > mid > end: " + child.getName())
        controls = []
        for node in (pole, target):
            control = mlib.nodes.Node(node)
            if not isinstance(control, mlib.nodes.Transform):
                raise ValueError("Expected transforms for the pole and the target")
            if control.getUuid() in {joint.getUuid() for joint in joints}:
                raise ValueError("The pole and the target must not be joints of the chain")
            controls.append(control)
        pole, target = controls
        index = _AXES.index(axis)
        rest = [joint.getPlug("translate").get()[index] for joint in (mid, end)]
        if any(abs(value) < 1e-9 for value in rest):
            raise ValueError("The mid and the end must be apart from their parents along the axis")
        signs = [1.0 if value > 0.0 else -1.0 for value in rest]

        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        owner.addAttr(longName="slide", attributeType="double", minValue=-1.0, maxValue=1.0,
                      defaultValue=slide, keyable=True)
        owner.addAttr(longName="pin", attributeType="double", minValue=0.0, maxValue=1.0,
                      defaultValue=pin, keyable=True)
        for attribute, value in (("restUpper", abs(rest[0])), ("restLower", abs(rest[1]))):
            owner.addAttr(longName=attribute, attributeType="doubleLinear", minValue=0.0,
                          defaultValue=value, keyable=True)
        for attribute in ("upperLength", "lowerLength"):
            owner.addAttr(longName=attribute, attributeType="doubleLinear")

        def number(plug, label):
            """長さのplugを係数1の unitConversion で単位なしの数にする。"""
            plain = graph._node("unitConversion", label)
            plain.getPlug("conversionFactor").set(1.0)
            plug.connectTo(plain.getPlug("input"))
            return plain.getPlug("output")

        # R: 付け根の translate(付け根の親の空間)。回転・worldMatrixを経由しないのでIKと循環しない。
        root = graph._node("plusMinusAverage", "rootPoint")
        for letter_index, letter in enumerate("XYZ"):
            value = number(start.getPlug("translate" + letter), "root" + letter)
            value.connectTo(root.getPlug("input3D")[0].getChildren()[letter_index])
        # P・T: ワールド行列 × 付け根の parentInverseMatrix の原点(vectorProductで単位なしのまま)。
        points = []
        for label, control in (("pole", pole), ("target", target)):
            local = graph._node("multMatrix", label + "Local")
            control.getPlug("worldMatrix")[0].connectTo(local.getPlug("matrixIn")[0])
            start.getPlug("parentInverseMatrix")[0].connectTo(local.getPlug("matrixIn")[1])
            point = graph._node("vectorProduct", label + "Point")
            point.getPlug("operation").set(4)
            point.getPlug("input1").set((0.0, 0.0, 0.0))
            local.getPlug("matrixSum").connectTo(point.getPlug("matrix"))
            points.append(point.getPlug("output"))
        reach = []
        for label, first, second in (("upperReach", points[0], root.getPlug("output3D")),
                                     ("lowerReach", points[1], points[0])):
            delta = graph._node("plusMinusAverage", label + "Delta")
            delta.getPlug("operation").set(2)
            first.connectTo(delta.getPlug("input3D")[0])
            second.connectTo(delta.getPlug("input3D")[1])
            squared = graph._node("vectorProduct", label + "Squared")
            squared.getPlug("operation").set(1)
            delta.getPlug("output3D").connectTo(squared.getPlug("input1"))
            delta.getPlug("output3D").connectTo(squared.getPlug("input2"))
            length = graph._node("multiplyDivide", label)
            length.getPlug("operation").set(3)
            squared.getPlug("outputX").connectTo(length.getPlug("input1X"))
            length.getPlug("input2X").set(0.5)
            reach.append(length.getPlug("outputX"))

        # slide: δ = s·L0 (s≥0) / s·U0 (s<0)、U' = U0+δ、L' = L0-δ。
        upper0 = number(owner.getPlug("restUpper"), "restUpperNumber")
        lower0 = number(owner.getPlug("restLower"), "restLowerNumber")
        scaled = graph._node("multiplyDivide", "slideScaled")
        owner.getPlug("slide").connectTo(scaled.getPlug("input1X"))
        lower0.connectTo(scaled.getPlug("input2X"))
        owner.getPlug("slide").connectTo(scaled.getPlug("input1Y"))
        upper0.connectTo(scaled.getPlug("input2Y"))
        shift = graph._node("condition", "slideShift")
        shift.getPlug("operation").set(3)
        owner.getPlug("slide").connectTo(shift.getPlug("firstTerm"))
        shift.getPlug("secondTerm").set(0.0)
        scaled.getPlug("outputX").connectTo(shift.getPlug("colorIfTrueR"))
        scaled.getPlug("outputY").connectTo(shift.getPlug("colorIfFalseR"))
        slid = []
        for label, base, operation in (("upperSlid", upper0, 1), ("lowerSlid", lower0, 2)):
            total = graph._node("plusMinusAverage", label)
            total.getPlug("operation").set(operation)
            base.connectTo(total.getPlug("input1D")[0])
            shift.getPlug("outColorR").connectTo(total.getPlug("input1D")[1])
            slid.append(total.getPlug("output1D"))

        # pin: U = U'+w(d1-U')、L = L'+w(d2-L')。blendColors は color1·w + color2·(1-w)。
        blend = graph._node("blendColors", "pinBlend")
        owner.getPlug("pin").connectTo(blend.getPlug("blender"))
        reach[0].connectTo(blend.getPlug("color1R"))
        slid[0].connectTo(blend.getPlug("color2R"))
        reach[1].connectTo(blend.getPlug("color1G"))
        slid[1].connectTo(blend.getPlug("color2G"))
        signed = graph._node("multiplyDivide", "signed")
        blend.getPlug("outputR").connectTo(signed.getPlug("input1X"))
        blend.getPlug("outputG").connectTo(signed.getPlug("input1Y"))
        signed.getPlug("input2X").set(signs[0])
        signed.getPlug("input2Y").set(signs[1])
        for label, value, joint, report in (
                ("upper", signed.getPlug("outputX"), mid, blend.getPlug("outputR")),
                ("lower", signed.getPlug("outputY"), end, blend.getPlug("outputG"))):
            drive = graph._node("unitConversion", label + "Drive")
            drive.getPlug("conversionFactor").set(1.0)
            value.connectTo(drive.getPlug("input"))
            drive.getPlug("output").connectTo(joint.getPlug("translate" + axis.upper()))
            out = graph._node("unitConversion", label + "Report")
            out.getPlug("conversionFactor").set(1.0)
            report.connectTo(out.getPlug("input"))
            out.getPlug("output").connectTo(owner.getPlug(label + "Length"))
        return graph
