"""2点の間に張ったケーブル・ホース・ロープの垂れを、長さから懸垂線の深さを近似して放物線で標準DGに構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.twistDistribution import TwistDistribution


def _position(matrix):
    """行列の平行移動をVectorで返す。"""
    return Vector(matrix[12], matrix[13], matrix[14])


class CableSag(TwistDistribution):
    """両端のtransformの間に垂れるケーブルの上の点の行列を出力する標準DG。

    両端の位置 A・B、弦 C = B - A、弦の長さ D、ケーブルの長さ L から、垂れの深さを
    懸垂線(catenary)の中央の深さの閉じた近似 h = sqrt(max((L - D)(2L + D)/8, 0)) とする(懸垂線との差は1/117未満)。
    形は中央の深さが h の放物線で近似する。
    垂れる向き n は重力の向き g から弦に沿った成分を除いて正規化した向き。
    u = i/(count-1) の点を P(u) = A + C·u + n·h·4u(1-u)、接線を P'(u) = C + n·h·4(1-2u) とし、
    X=接線、Z=X×(-g)、Y=Z×X の枠をワールド行列にする。両端を近づけると深く垂れ、L 以上に離すと一直線になる。
    フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def points(cls, start, end, length, count, gravity=(0.0, -1.0, 0.0)):
        """垂れたケーブルの上の点の位置を計算する(DGと同じ式のPython版)。

        Args:
            start (Sequence[float]): 始点の位置。
            end (Sequence[float]): 終点の位置。
            length (float): ケーブルの長さ。
            count (int): 点の数(両端を含む、2以上)。
            gravity (Sequence[float]): 重力の向き。

        Returns:
            list[Vector]: 始点から終点までの点の位置。
        """
        a = Vector(*start)
        chord = Vector(*end) - a
        span = chord.length()
        direction, depth = cls._sag(chord, span, length, gravity)
        result = []
        for index in range(count):
            u = index / float(count - 1)
            result.append(a + chord * u + direction * (depth * 4.0 * u * (1.0 - u)))
        return result

    @staticmethod
    def _sag(chord, span, length, gravity):
        """垂れる向き(単位ベクトル、弦と平行なら0)と深さを返す。"""
        g = Vector(*gravity).normal()
        if span > 1e-12:
            unit = chord / span
            direction = g - unit * (g * unit)
        else:
            direction = Vector(g[0], g[1], g[2])
        direction = direction.normal() if direction.length() > 1e-12 else Vector(0.0, 0.0, 0.0)
        depth = math.sqrt(max((length - span) * (2.0 * length + span) / 8.0, 0.0))
        return direction, depth

    @classmethod
    @undoTransaction("mlrig.CableSag.create")
    def create(cls, start, end, count=8, name="cableSag", length=None, gravity=(0.0, -1.0, 0.0)):
        """両端のtransformの間に垂れるケーブルの点の行列(matrix0〜)を生成する。

        Args:
            start (str | Node): 始点のtransform(ケーブルを留める位置)。
            end (str | Node): 終点のtransform。
            count (int): 出力する点の数(両端を含む、2以上)。
            name (str): 一意なcontainer名。
            length (float | None): ケーブルの長さ(cm)。None なら生成時の両端の距離の1.1倍。
            gravity (Sequence[float]): 重力の向き(ワールド)。

        Returns:
            CableSag: ``matrix<i>``・``sag``・``span`` の所有者。containerに ``length``(keyable)を持つ。

        Raises:
            ValueError: start・end がtransformでない場合、count が2未満の場合、length が負の場合、
                重力の向きが0の場合、両端が同じ位置の場合、またはnameが既に存在する場合。

        Note:
            出力はワールド行列なので、ワールド直下のtransformの ``offsetParentMatrix`` へ接続する。
            形は放物線の近似なので、出力の点を通る放物線の弧長は L より少し短い(長さが弦の1.1倍で約0.2%、
            1.2倍で約0.5%、1.4倍で約1.1%、2倍で約2.3%短い)。
            弦が重力と平行(真上・真下に並ぶ)の場合は垂れる向きと枠が決まらない。
        """
        if mlib.ls(name):
            raise ValueError("CableSag container already exists: " + name)
        nodes = []
        for label, value in (("start", start), ("end", end)):
            node = mlib.nodes.Node(value)
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected a transform for the " + label)
            nodes.append(node)
        start, end = nodes
        if isinstance(count, bool) or not isinstance(count, int) or count < 2:
            raise ValueError("count must be an integer of 2 or more")
        g = Vector(*[float(value) for value in gravity])
        if len(gravity) != 3 or not all(math.isfinite(value) for value in g) or g.length() < 1e-9:
            raise ValueError("gravity must be a finite non-zero 3D vector")
        g = g.normal()
        a = _position(Matrix(start.getPlug("worldMatrix")[0].get()))
        b = _position(Matrix(end.getPlug("worldMatrix")[0].get()))
        span = (b - a).length()
        if span < 1e-6:
            raise ValueError("The start and the end must not be at the same position")
        if length is None:
            length = span * 1.1
        length = float(length)
        if not math.isfinite(length) or length < 0.0:
            raise ValueError("length must be zero or positive")

        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        owner.addAttr(longName="length", attributeType="doubleLinear", defaultValue=length, minValue=0.0,
                      keyable=True)
        owner.addAttr(longName="sag", attributeType="doubleLinear")
        owner.addAttr(longName="span", attributeType="doubleLinear")
        for index in range(count):
            owner.addAttr(longName="matrix" + str(index), dataType="matrix")

        # 両端の位置は vectorProduct(点×行列)で単位なしのまま取り出す(mmでも自動の単位変換が入らない)。
        ends = []
        for label, node in (("start", start), ("end", end)):
            point = graph._node("vectorProduct", label + "Point")
            point.getPlug("operation").set(4)
            point.getPlug("input1").set((0.0, 0.0, 0.0))
            node.getPlug("worldMatrix")[0].connectTo(point.getPlug("matrix"))
            ends.append(point)
        chord = graph._node("plusMinusAverage", "chord")
        chord.getPlug("operation").set(2)
        ends[1].getPlug("output").connectTo(chord.getPlug("input3D")[0])
        ends[0].getPlug("output").connectTo(chord.getPlug("input3D")[1])

        # D = sqrt(dot(C, C))、垂れる向き n = normalize(g - (g·Ĉ)Ĉ)。
        squared = graph._node("vectorProduct", "chordSquared")
        squared.getPlug("operation").set(1)
        chord.getPlug("output3D").connectTo(squared.getPlug("input1"))
        chord.getPlug("output3D").connectTo(squared.getPlug("input2"))
        span_node = graph._node("multiplyDivide", "span")
        span_node.getPlug("operation").set(3)
        squared.getPlug("outputX").connectTo(span_node.getPlug("input1X"))
        span_node.getPlug("input2X").set(0.5)
        unit = graph._node("vectorProduct", "chordUnit")
        unit.getPlug("operation").set(0)
        unit.getPlug("normalizeOutput").set(True)
        chord.getPlug("output3D").connectTo(unit.getPlug("input1"))
        along = graph._node("vectorProduct", "gravityAlong")
        along.getPlug("operation").set(1)
        unit.getPlug("output").connectTo(along.getPlug("input1"))
        along.getPlug("input2").set(tuple(g))
        projected = graph._node("multiplyDivide", "gravityProjected")
        unit.getPlug("output").connectTo(projected.getPlug("input1"))
        for letter in "XYZ":
            along.getPlug("outputX").connectTo(projected.getPlug("input2" + letter))
        across = graph._node("plusMinusAverage", "gravityAcross")
        across.getPlug("operation").set(2)
        across.getPlug("input3D")[0].set(tuple(g))
        projected.getPlug("output").connectTo(across.getPlug("input3D")[1])
        direction = graph._node("vectorProduct", "sagDirection")
        direction.getPlug("operation").set(0)
        direction.getPlug("normalizeOutput").set(True)
        across.getPlug("output3D").connectTo(direction.getPlug("input1"))

        # h = sqrt(max((L - D)(2L + D)/8, 0))。長さは係数1の unitConversion で数値にする。
        plain = graph._node("unitConversion", "lengthNumber")
        plain.getPlug("conversionFactor").set(1.0)
        owner.getPlug("length").connectTo(plain.getPlug("input"))
        slack = graph._node("plusMinusAverage", "slack")
        slack.getPlug("operation").set(2)
        plain.getPlug("output").connectTo(slack.getPlug("input1D")[0])
        span_node.getPlug("outputX").connectTo(slack.getPlug("input1D")[1])
        reach = graph._node("plusMinusAverage", "reach")
        plain.getPlug("output").connectTo(reach.getPlug("input1D")[0])
        plain.getPlug("output").connectTo(reach.getPlug("input1D")[1])
        span_node.getPlug("outputX").connectTo(reach.getPlug("input1D")[2])
        product = graph._node("multiplyDivide", "slackProduct")
        slack.getPlug("output1D").connectTo(product.getPlug("input1X"))
        reach.getPlug("output1D").connectTo(product.getPlug("input2X"))
        scaled = graph._node("multiplyDivide", "slackScaled")
        product.getPlug("outputX").connectTo(scaled.getPlug("input1X"))
        scaled.getPlug("input2X").set(1.0 / 8.0)
        floor = graph._node("clamp", "slackFloor")
        floor.getPlug("maxR").set(1e30)
        scaled.getPlug("outputX").connectTo(floor.getPlug("inputR"))
        depth = graph._node("multiplyDivide", "depth")
        depth.getPlug("operation").set(3)
        floor.getPlug("outputR").connectTo(depth.getPlug("input1X"))
        depth.getPlug("input2X").set(0.5)
        for attribute, plug in (("sag", depth.getPlug("outputX")), ("span", span_node.getPlug("outputX"))):
            report = graph._node("unitConversion", attribute + "Length")
            report.getPlug("conversionFactor").set(1.0)
            plug.connectTo(report.getPlug("input"))
            report.getPlug("output").connectTo(owner.getPlug(attribute))
        offset = graph._node("multiplyDivide", "sagOffset")
        direction.getPlug("output").connectTo(offset.getPlug("input1"))
        for letter in "XYZ":
            depth.getPlug("outputX").connectTo(offset.getPlug("input2" + letter))

        # 各点: P = A + C·u + n·h·k、接線 T = C + n·h·4(1-2u)。枠は X=T、Z=X×(-g)、Y=Z×X。
        up = tuple(-value for value in g)
        for index in range(count):
            u = index / float(count - 1)
            prefix = "point" + str(index)
            moved = graph._node("multiplyDivide", prefix + "Chord")
            chord.getPlug("output3D").connectTo(moved.getPlug("input1"))
            moved.getPlug("input2").set((u, u, u))
            bowed = graph._node("multiplyDivide", prefix + "Sag")
            offset.getPlug("output").connectTo(bowed.getPlug("input1"))
            k = 4.0 * u * (1.0 - u)
            bowed.getPlug("input2").set((k, k, k))
            position = graph._node("plusMinusAverage", prefix + "Position")
            ends[0].getPlug("output").connectTo(position.getPlug("input3D")[0])
            moved.getPlug("output").connectTo(position.getPlug("input3D")[1])
            bowed.getPlug("output").connectTo(position.getPlug("input3D")[2])
            bend = graph._node("multiplyDivide", prefix + "Bend")
            offset.getPlug("output").connectTo(bend.getPlug("input1"))
            slope = 4.0 * (1.0 - 2.0 * u)
            bend.getPlug("input2").set((slope, slope, slope))
            tangent = graph._node("plusMinusAverage", prefix + "Tangent")
            chord.getPlug("output3D").connectTo(tangent.getPlug("input3D")[0])
            bend.getPlug("output").connectTo(tangent.getPlug("input3D")[1])
            axes = []
            for letter, operation in (("X", 0), ("Z", 2), ("Y", 2)):
                vector = graph._node("vectorProduct", prefix + "Axis" + letter)
                vector.getPlug("operation").set(operation)
                vector.getPlug("normalizeOutput").set(True)
                axes.append(vector)
            x_axis, z_axis, y_axis = axes
            tangent.getPlug("output3D").connectTo(x_axis.getPlug("input1"))
            x_axis.getPlug("output").connectTo(z_axis.getPlug("input1"))
            z_axis.getPlug("input2").set(up)
            z_axis.getPlug("output").connectTo(y_axis.getPlug("input1"))
            x_axis.getPlug("output").connectTo(y_axis.getPlug("input2"))
            frame = graph._node("fourByFourMatrix", prefix + "Matrix")
            rows = ((x_axis, ("outputX", "outputY", "outputZ")), (y_axis, ("outputX", "outputY", "outputZ")),
                    (z_axis, ("outputX", "outputY", "outputZ")),
                    (position, ("output3Dx", "output3Dy", "output3Dz")))
            for row, (source, children) in enumerate(rows):
                for column, child in enumerate(children):
                    source.getPlug(child).connectTo(frame.getPlug("in{}{}".format(row, column)))
            frame.getPlug("output").connectTo(owner.getPlug("matrix" + str(index)))
        owner.setAttrFlags(["sag", "span"] + ["matrix" + str(index) for index in range(count)], keyable=False)
        return graph
