"""両端の間にコイルばねのらせんを張り、伸縮で巻きの間隔だけを変える標準DGを構築する。"""

import math

import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.twistDistribution import TwistDistribution


class CoilSpring(TwistDistribution):
    """サスペンション・ばね仕掛けのように、両端の距離に合わせて巻きの間隔(ピッチ)だけが変わるらせん。

    巻きの半径と線の太さは変えないので、拡大縮小で線まで潰れる見た目にならない。
    縮めても巻き同士が接する長さ(密着長 solidLength = turns * wireDiameter)より短くはならず、
    足りない分を ``coilBind`` として出力する。
    """

    @classmethod
    def coilLayout(cls, count, length, turns, radius, wireDiameter):
        """らせん上の各点の配置を計算する(DGと同じ式のPython版)。

        Args:
            count (int): らせん上の点の数。2以上。
            length (float): 両端の距離(cm)。
            turns (float): 巻き数。0より大きい。
            radius (float): 巻きの半径(cm)。
            wireDiameter (float): 線の太さ(cm)。

        Returns:
            dict: solidLength・effectiveLength・pitch・gap・coilBind(cm)と、
            各点の(軸方向の距離cm, 軸まわりの角度 度, 半径cm)のlist ``points``。
        """
        solid = turns * wireDiameter
        effective = max(length, solid)
        pitch = effective / turns
        points = []
        for index in range(count):
            ratio = index / (count - 1)
            points.append((effective * ratio, 360.0 * turns * ratio, radius))
        return {
            "solidLength": solid,
            "effectiveLength": effective,
            "pitch": pitch,
            "gap": pitch - wireDiameter,
            "coilBind": effective - length,
            "points": points,
        }

    @classmethod
    @undoTransaction("mlrig.CoilSpring.create")
    def create(cls, base, tip, name="coilSpring", count=13, turns=4.0, radius=1.0, wireDiameter=0.2,
               aimAxis="x", upAxis="y"):
        """baseからtipへ伸びるらせん上の各点のワールド行列を生成する。

        Args:
            base (str | Node): ばねの根元のtransform。
            tip (str | Node): ばねの先端のtransform。
            name (str): 一意なcontainer名。
            count (int): らせん上の点(出力行列)の数。2〜1000。
            turns (float): 巻き数。0.5以上。
            radius (float): 巻きの半径(cm)。0より大きい。
            wireDiameter (float): 線の太さ(cm)。0以上。
            aimAxis (str): baseのローカルでばねの軸になる軸x/y/z。生成時にtipの方向を向いていなくてもよい。
            upAxis (str): baseのローカルで巻き始め(角度0)の向きになる軸x/y/z。aimAxisと異なる。

        Returns:
            CoilSpring: matrix0〜matrixN-1・length・solidLength・effectiveLength・pitch・gap・coilBindの所有者。

        Raises:
            ValueError: 軸・数・値が不正な場合、両端が同じ位置にある場合、またはnameが既に存在する場合。

        Note:
            ばねの座標系は標準の ``aimMatrix`` で、baseの位置からaimAxisをtipへ向け、
            upAxisをbaseの現在のupAxisの向きへ揃えたもの(baseを軸まわりに回すとばねもねじれる)。
            L = 両端の距離、solidLength = turns * wireDiameter、
            effectiveLength = max(L, solidLength)、coilBind = effectiveLength - L、
            pitch = effectiveLength / turns、gap = pitch - wireDiameter(cm)。
            点i(t = i/(N-1))の行列 = 平行移動(upAxis * radius) * 回転(aimAxisまわり 360*turns*t 度)
            * 平行移動(aimAxis * effectiveLength * t) * ばねの座標系(行ベクトル規約)。
            各点のupAxisは軸から外向き、aimAxisはばねの軸の向き(らせんの接線の傾きは含めない)。
            密着より縮めると先端側の点はtipへ届かず、その距離がcoilBind。
            radius・turns・wireDiameterはcontainerのkeyableなアトリビュートで後から変えられる。
            両端を結ぶ線がupAxisと平行になると向きが不定、負・非一様scaleは対象外。
        """
        axes = ("x", "y", "z")
        if aimAxis not in axes or upAxis not in axes or aimAxis == upAxis:
            raise ValueError("aimAxis and upAxis must be two different axes of x, y and z")
        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError("count must be an int")
        if not 2 <= count <= 1000:
            raise ValueError("count must be between 2 and 1000")
        for value in (turns, radius, wireDiameter):
            if not math.isfinite(value):
                raise ValueError("turns, radius and wireDiameter must be finite")
        if turns < 0.5:
            raise ValueError("turns must be at least 0.5")
        if radius <= 0 or wireDiameter < 0:
            raise ValueError("radius must be positive and wireDiameter must not be negative")
        if mlib.objExists(name):
            raise ValueError("CoilSpring container already exists: " + name)
        base, tip = mlib.nodes.Node(base), mlib.nodes.Node(tip)
        if base == tip or any(
            not isinstance(node, mlib.nodes.Transform) for node in (base, tip)
        ):
            raise ValueError("Expected two different transforms for the base and the tip")
        base_world = Matrix(base.getPlug("worldMatrix")[0].get())
        tip_world = Matrix(tip.getPlug("worldMatrix")[0].get())
        if (Vector(tip_world.translate) - Vector(base_world.translate)).length() < 1e-6:
            raise ValueError("The base and the tip must be at different positions")
        aim_axis = [float(axis == aimAxis) for axis in axes]
        up_axis = [float(axis == upAxis) for axis in axes]

        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        scalar = ScalarGraph(owner)
        owner.addAttr(longName="turns", attributeType="double", defaultValue=turns, minValue=0.5, keyable=True)
        owner.addAttr(longName="radius", attributeType="double", defaultValue=radius, minValue=1e-4,
                      keyable=True)
        owner.addAttr(longName="wireDiameter", attributeType="double", defaultValue=wireDiameter, minValue=0,
                      keyable=True)
        outputs = ("length", "solidLength", "effectiveLength", "pitch", "gap", "coilBind")
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        for index in range(count):
            owner.addAttr(longName="matrix" + str(index), dataType="matrix")

        # ばねの座標系: baseの位置からaimAxisをtipへ向け、upAxisをbaseの現在のupAxisへ揃える。
        frame = graph._node("aimMatrix", "frame")
        base.getPlug("worldMatrix")[0].connectTo(frame.getPlug("inputMatrix"))
        tip.getPlug("worldMatrix")[0].connectTo(frame.getPlug("primaryTargetMatrix"))
        frame.getPlug("primaryMode").set(1)
        frame.getPlug("primaryInputAxis").set(aim_axis)
        frame.getPlug("primaryTargetVector").set((0, 0, 0))
        frame.getPlug("secondaryMode").set(2)
        frame.getPlug("secondaryInputAxis").set(up_axis)
        frame.getPlug("secondaryTargetVector").set(up_axis)
        base.getPlug("worldMatrix")[0].connectTo(frame.getPlug("secondaryTargetMatrix"))

        # 両端の距離(cm)。UIの長さ単位によらずcmで出力する。
        distance = graph._node("distanceBetween", "distance")
        base.getPlug("worldMatrix")[0].connectTo(distance.getPlug("inMatrix1"))
        tip.getPlug("worldMatrix")[0].connectTo(distance.getPlug("inMatrix2"))
        centimeters = graph._node("unitConversion", "lengthCentimeters")
        conversions.add(centimeters.getUuid())
        distance.getPlug("distance").connectTo(centimeters.getPlug("input"))
        centimeters.getPlug("conversionFactor").set(1.0)
        centimeters.getPlug("output").connectTo(owner.getPlug("length"))

        length = owner.getPlug("length")
        scalar.multiply("solidLengthRaw", owner.getPlug("turns"), owner.getPlug("wireDiameter")).connectTo(
            owner.getPlug("solidLength")
        )
        solid = owner.getPlug("solidLength")
        scalar.condition("effectiveLengthRaw", length, solid, length, solid).connectTo(
            owner.getPlug("effectiveLength")
        )
        effective = owner.getPlug("effectiveLength")
        scalar.sum("coilBindRaw", effective, length, subtract=True).connectTo(owner.getPlug("coilBind"))
        scalar.multiply("pitchRaw", effective, owner.getPlug("turns"), operation=2).connectTo(
            owner.getPlug("pitch")
        )
        scalar.sum("gapRaw", owner.getPlug("pitch"), owner.getPlug("wireDiameter"), subtract=True).connectTo(
            owner.getPlug("gap")
        )

        # 半径方向のずれ(upAxis * radius)は全点で共通。
        offset = graph._node("composeMatrix", "radiusOffset")
        owner.getPlug("radius").connectTo(offset.getPlug("inputTranslate" + upAxis.upper()))
        for index in range(count):
            role = "point" + str(index)
            ratio = index / (count - 1)
            # 角度 360*turns*t 度をラジアンにして、aimAxisまわりの回転にする。
            angle = scalar.multiply(role + "Angle", owner.getPlug("turns"), 360.0 * ratio)
            radians = graph._node("unitConversion", role + "AngleRadians")
            conversions.add(radians.getUuid())
            angle.connectTo(radians.getPlug("input"))
            radians.getPlug("conversionFactor").set(math.pi / 180)
            local = graph._node("composeMatrix", role + "Local")
            radians.getPlug("output").connectTo(local.getPlug("inputRotate" + aimAxis.upper()))
            scalar.multiply(role + "Axial", effective, ratio).connectTo(
                local.getPlug("inputTranslate" + aimAxis.upper())
            )
            world = graph._node("multMatrix", role + "World")
            offset.getPlug("outputMatrix").connectTo(world.getPlug("matrixIn")[0])
            local.getPlug("outputMatrix").connectTo(world.getPlug("matrixIn")[1])
            frame.getPlug("outputMatrix").connectTo(world.getPlug("matrixIn")[2])
            world.getPlug("matrixSum").connectTo(owner.getPlug("matrix" + str(index)))
        owner.setAttrFlags(list(outputs), keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph
