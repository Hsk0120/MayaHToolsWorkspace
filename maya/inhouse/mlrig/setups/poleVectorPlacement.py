"""3関節の曲がる平面上で、中間関節の外側へポールベクターの位置を求める標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution


class PoleVectorPlacement(TwistDistribution):
    """付け根・中間・先端の位置から、曲がる向きの延長上にポールの位置を出力する標準DG。

    FKからIKへの切り替えでポールベクターを合わせる、膝・肘の向きを表示する、などに使う。
    位置は付け根と先端を結ぶ線に垂直な向きへ置くので、ポールを置いてもIKの曲がる平面は変わらない。
    """

    #: 曲がりの大きさ(cm)がこれ未満なら一直線とみなし、ポールを中間関節に置く。
    STRAIGHT_THRESHOLD = 1e-4

    @classmethod
    def polePosition(cls, start, mid, end, distance):
        """ポールの位置を計算する(DGと同じ式のPython版)。

        Args:
            start (Sequence[float]): 付け根の位置(cm)。
            mid (Sequence[float]): 中間関節の位置(cm)。
            end (Sequence[float]): 先端の位置(cm)。
            distance (float): 中間関節からポールまでの距離(cm)。

        Returns:
            tuple[float, float, float]: ポールの位置(cm)。一直線で向きが決まらない場合は中間関節の位置。
        """
        se = [e - s for s, e in zip(start, end)]
        sm = [m - s for s, m in zip(start, mid)]
        length = sum(v * v for v in se)
        t = sum(a * b for a, b in zip(sm, se)) / length if length > 0 else 0.0
        direction = [a - t * b for a, b in zip(sm, se)]
        norm = math.sqrt(sum(v * v for v in direction))
        if norm < cls.STRAIGHT_THRESHOLD:
            return tuple(mid)
        return tuple(m + distance * v / norm for m, v in zip(mid, direction))

    @classmethod
    @undoTransaction("mlrig.PoleVectorPlacement.create")
    def create(cls, start, mid, end, name="poleVectorPlacement", distance=None):
        """ポールの位置とワールド行列を生成する。

        Args:
            start (str | Node): 付け根(肩・股関節)のtransform。
            mid (str | Node): 中間(肘・膝)のtransform。
            end (str | Node): 先端(手首・足首)のtransform。
            name (str): 一意なcontainer名。
            distance (float | None): 中間関節からポールまでの距離(cm、0以上)。
                Noneなら生成時の付け根→中間→先端の長さの合計の0.5倍。

        Returns:
            PoleVectorPlacement: matrix・position・bendDistanceの所有者。

        Raises:
            ValueError: transformの指定・distanceが不正な場合、またはnameが既に存在する場合。

        Note:
            各位置はワールド(cm)。s=付け根、m=中間、e=先端として、
            t = ((m-s)・(e-s)) / |e-s|^2、p = s + t(e-s)(中間関節を付け根-先端の線へ下ろした点)、
            d = m - p、pole = m + distance * d/|d|。bendDistance = |d|(曲がりの大きさ)。
            matrixは回転なし・位置poleのワールド行列(offsetParentMatrixへ接続するには、
            ワールド直下のtransformへ接続する)。
            一直線(|d|<0.0001cm)では向きが決まらないため、poleは中間関節の位置になる
            (ほぼ一直線の付近では、曲がる向きのわずかな変化でpoleが大きく動く)。
        """
        if mlib.ls(name):
            raise ValueError("PoleVectorPlacement container already exists: " + name)
        nodes = [mlib.nodes.Node(node) for node in (start, mid, end)]
        if len({node.getUuid() for node in nodes}) != 3 or any(
            not isinstance(node, mlib.nodes.Transform) for node in nodes
        ):
            raise ValueError("Expected three different transforms for start, mid and end")
        positions = []
        for node in nodes:
            world = node.getPlug("worldMatrix")[0].get()
            positions.append((world[12], world[13], world[14]))
        if distance is None:
            distance = 0.5 * sum(
                math.sqrt(sum((b - a) ** 2 for a, b in zip(positions[i], positions[i + 1]))) for i in range(2)
            )
        distance = float(distance)
        if not math.isfinite(distance) or distance < 0:
            raise ValueError("distance must be a finite value of 0 or more")
        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        owner.addAttr(longName="distance", attributeType="double", defaultValue=distance, minValue=0, keyable=True)
        owner.addAttr(longName="position", attributeType="double3")
        owner.addAttr(longName="bendDistance", attributeType="double")
        owner.addAttr(longName="matrix", dataType="matrix")

        # 各位置(ワールド、cm)。vectorProductで原点を変換し、長さの単位変換を挟まずに取り出す。
        points = []
        for role, node in zip(("start", "mid", "end"), nodes):
            point = graph._node("vectorProduct", role + "Position")
            point.getPlug("operation").set(4)
            point.getPlug("input1").set((0, 0, 0))
            node.getPlug("worldMatrix")[0].connectTo(point.getPlug("matrix"))
            points.append(point.getPlug("output"))

        def difference(role, left, right):
            """left - right の3成分。"""
            node = graph._node("plusMinusAverage", role)
            node.getPlug("operation").set(2)
            left.connectTo(node.getPlug("input3D")[0])
            right.connectTo(node.getPlug("input3D")[1])
            return node.getPlug("output3D")

        def dot(role, left, right):
            """内積(正規化しない)。"""
            node = graph._node("vectorProduct", role)
            node.getPlug("operation").set(1)
            node.getPlug("normalizeOutput").set(False)
            left.connectTo(node.getPlug("input1"))
            right.connectTo(node.getPlug("input2"))
            return node.getPlug("outputX")

        se = difference("startToEnd", points[2], points[0])
        sm = difference("startToMid", points[1], points[0])
        ratio = graph._node("multiplyDivide", "projectionRatio")
        ratio.getPlug("operation").set(2)
        dot("projectionDot", sm, se).connectTo(ratio.getPlug("input1X"))
        dot("lengthSquared", se, se).connectTo(ratio.getPlug("input2X"))
        along = graph._node("multiplyDivide", "alongLine")
        se.connectTo(along.getPlug("input1"))
        for component in "XYZ":
            ratio.getPlug("outputX").connectTo(along.getPlug("input2" + component))
        bend = difference("bendDirection", sm, along.getPlug("output"))
        length = graph._node("distanceBetween", "bendLength")
        bend.connectTo(length.getPlug("point2"))
        # distanceBetweenの出力は長さの単位なので、係数1のunitConversionでcmの数値として受け取る。
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        centimeters = graph._node("unitConversion", "bendCentimeters")
        conversions.add(centimeters.getUuid())
        length.getPlug("distance").connectTo(centimeters.getPlug("input"))
        centimeters.getPlug("conversionFactor").set(1.0)
        centimeters.getPlug("output").connectTo(owner.getPlug("bendDistance"))
        unit = graph._node("vectorProduct", "bendUnit")
        unit.getPlug("operation").set(0)
        unit.getPlug("normalizeOutput").set(True)
        bend.connectTo(unit.getPlug("input1"))
        # 一直線とみなす場合は距離を0にして、向きの決まらない単位ベクトルを使わない。
        effective = graph._node("condition", "effectiveDistance")
        effective.getPlug("operation").set(2)
        owner.getPlug("bendDistance").connectTo(effective.getPlug("firstTerm"))
        effective.getPlug("secondTerm").set(cls.STRAIGHT_THRESHOLD)
        owner.getPlug("distance").connectTo(effective.getPlug("colorIfTrueR"))
        effective.getPlug("colorIfFalseR").set(0.0)
        offset = graph._node("multiplyDivide", "poleOffset")
        unit.getPlug("output").connectTo(offset.getPlug("input1"))
        for component in "XYZ":
            effective.getPlug("outColorR").connectTo(offset.getPlug("input2" + component))
        pole = graph._node("plusMinusAverage", "pole")
        points[1].connectTo(pole.getPlug("input3D")[0])
        offset.getPlug("output").connectTo(pole.getPlug("input3D")[1])
        pole.getPlug("output3D").connectTo(owner.getPlug("position"))
        matrix = graph._node("fourByFourMatrix", "poleMatrix")
        for component, attr in zip("XYZ", ("in30", "in31", "in32")):
            owner.getPlug("position" + component).connectTo(matrix.getPlug(attr))
        matrix.getPlug("output").connectTo(owner.getPlug("matrix"))
        owner.setAttrFlags(["bendDistance"], keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph
