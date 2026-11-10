"""入れ子の筒が順番に、または均等に伸びる多段テレスコピックシリンダーの標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix, Vector

from mlrig.setups.twistDistribution import TwistDistribution

_AXES = ("x", "y", "z")


class TelescopicCylinder(TwistDistribution):
    """取り付け位置から先端へ向き、両端の距離に合わせて入れ子の各段を伸ばす標準DG。

    ダンプトラックの荷台やクレーンのブームの多段シリンダーのように、外側の筒(バレル)の中に
    小さい筒(段)が入れ子になっている。両端の距離から閉じた長さを引いた伸びを各段へ分ける。
    分け方は ``sequence`` で、1なら単動式のように外側の大きい段から順に伸び切り、
    0なら同期式のように全段が行程の比で同時に伸びる。中間は両者の線形補間。
    向きはTripodJointと同じく、取り付けの回転に軸から先端への最短の回転を掛けたもの。
    """

    @classmethod
    def extensionsOf(cls, extension, strokes, sequence=1.0):
        """全体の伸びを各段の伸びへ分ける(DGと同じ式)。

        Args:
            extension (float): 全体の伸び D - closedLength(cm、制限前)。
            strokes (Sequence[float]): 外側から順の各段の行程(cm)。
            sequence (float): 1で外側から順、0で行程の比で均等。

        Returns:
            list[float]: 外側から順の各段の伸び(cm)。合計は clamp(extension, 0, Σstrokes)。
        """
        strokes = [float(value) for value in strokes]
        total = min(max(float(extension), 0.0), sum(strokes))
        ratio = total / max(sum(strokes), 1e-6)
        result = []
        used = 0.0
        for stroke in strokes:
            ordered = min(max(total - used, 0.0), stroke)
            result.append(ratio * stroke + (ordered - ratio * stroke) * sequence)
            used += stroke
        return result

    @classmethod
    @undoTransaction("mlrig.TelescopicCylinder.create")
    def create(cls, base, tip, name="telescopicCylinder", stages=3, axis="x", closedLength=None, stroke=None,
               sequence=1.0):
        """baseからtipへ向くバレルと、伸びを分けた各段の行列を生成する。

        Args:
            base (str | Node): 取り付け位置のtransform。axis を閉じた筒の向きにする。
            tip (str | Node): 先端(ロッドの端)の位置を表すtransform(位置だけを使う)。
            name (str): 一意なcontainer名。
            stages (int): 伸びる段の数(1〜16)。バレルは含まない。
            axis (str): 筒の軸の向き x/y/z。
            closedLength (float | None): 全段が縮んだときのbaseからtipまでの距離(cm)。
                Noneなら生成時の距離(つまり生成時は全段が縮んだ状態)。
            stroke (float | Sequence[float] | None): 各段の行程(cm)。数値なら全段同じ、列なら外側から順。
                Noneなら 0.9 × closedLength。
            sequence (float): 0〜1。1で外側の段から順、0で全段が均等に伸びる。

        Returns:
            TelescopicCylinder: matrix[]・tipMatrix・stageExtension[]・length・extension・overExtension・
            bendAngleの所有者。

        Raises:
            ValueError: 軸・段数・長さ・行程・sequenceが不正な場合、base・tipがtransformでない場合、
                同じノードの場合、またはnameが既に存在する場合。

        Note:
            H = baseのワールド位置、R = baseのワールド行列の回転(scale・shear・平行移動を除く)、
            u = R で回した axis、W = tipのワールド位置、v = normalize(W - H)、D = |W - H|。
            E = D - closedLength、total = clamp(E, 0, Σs)、overExtension = E - total。
            順番の伸び o_k = clamp(total - Σ_{j<k} s_j, 0, s_k)、均等の伸び g_k = total × s_k / Σs、
            stageExtension[k] = g_k + sequence × (o_k - g_k)。
            matrix[0](バレル)は位置 H、matrix[k](k=1..stages)は位置 H + v × Σ_{j<k} stageExtension[j]、
            tipMatrix は位置 H + v × (closedLength + total)。向きはいずれも R × Q(u→v)、scaleは1。
            各段の位置は閉じたときにbaseへ重なる基準点で、段のモデルはその点を原点に作る。
            長さはcm(UIの長さ単位によらない)。縮むときの順番の違い(小さい段から戻る)は扱わない。
        """
        if axis not in _AXES:
            raise ValueError("axis must be one of x, y and z")
        if isinstance(stages, bool) or not isinstance(stages, int) or not 1 <= stages <= 16:
            raise ValueError("stages must be an integer from 1 to 16")
        sequence = float(sequence)
        if not 0.0 <= sequence <= 1.0:
            raise ValueError("sequence must be between 0 and 1")
        if mlib.objExists(name):
            raise ValueError("TelescopicCylinder container already exists: " + name)
        base = mlib.Node(base)
        tip = mlib.Node(tip)
        for node in (base, tip):
            if not isinstance(node, mlib.Transform):
                raise ValueError("Expected transforms for the base and the tip")
        if base.getFullName() == tip.getFullName():
            raise ValueError("base and tip must be different nodes")
        if closedLength is None:
            start = Vector(Matrix(base.getPlug("worldMatrix")[0].get()).translate)
            end = Vector(Matrix(tip.getPlug("worldMatrix")[0].get()).translate)
            closedLength = (end - start).length()
        closedLength = float(closedLength)
        if not math.isfinite(closedLength) or closedLength < 1e-6:
            raise ValueError("closedLength must be a finite positive distance")
        if stroke is None:
            stroke = 0.9 * closedLength
        strokes = [float(stroke)] * stages if isinstance(stroke, (int, float)) else [float(value) for value in stroke]
        if len(strokes) != stages:
            raise ValueError("stroke must be a number or a sequence with one value per stage")
        if any(not math.isfinite(value) or value < 1e-6 for value in strokes):
            raise ValueError("Each stroke must be a finite positive distance")
        cylinder_axis = [float(item == axis) for item in _AXES]
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="closedLength", attributeType="double", defaultValue=closedLength, minValue=0,
                      keyable=True)
        owner.addAttr(longName="sequence", attributeType="double", defaultValue=sequence, minValue=0, maxValue=1,
                      keyable=True)
        owner.addAttr(longName="stageStroke", attributeType="double", multi=True)
        for index, value in enumerate(strokes):
            owner.getPlug("stageStroke")[index].set(value)
        outputs = ("length", "extension", "overExtension")
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        owner.addAttr(longName="bendAngle", attributeType="doubleAngle")
        owner.addAttr(longName="stageExtension", attributeType="double", multi=True)
        owner.addAttr(longName="matrix", dataType="matrix", multi=True)
        owner.addAttr(longName="tipMatrix", dataType="matrix")

        # 取り付けの位置 H・回転 R・軸 u と、先端の位置 W
        baseMatrix = base.getPlug("worldMatrix")[0]
        origin = graph._node("decomposeMatrix", "basePosition")
        baseMatrix.connectTo(origin.getPlug("inputMatrix"))
        target = graph._node("decomposeMatrix", "tipPosition")
        tip.getPlug("worldMatrix")[0].connectTo(target.getPlug("inputMatrix"))
        h = origin.getPlug("outputTranslate")
        rotation = graph._node("pickMatrix", "baseRotation")
        for flag in ("useTranslate", "useScale", "useShear"):
            rotation.getPlug(flag).set(False)
        baseMatrix.connectTo(rotation.getPlug("inputMatrix"))
        u = graph._node("vectorProduct", "baseAxis")
        u.getPlug("operation").set(3)
        u.getPlug("normalizeOutput").set(True)
        u.getPlug("input1").set(cylinder_axis)
        baseMatrix.connectTo(u.getPlug("matrix"))

        # d = W - H、D = |d|、v = normalize(d)
        offset = graph._node("plusMinusAverage", "tipOffset")
        offset.getPlug("operation").set(2)
        target.getPlug("outputTranslate").connectTo(offset.getPlug("input3D")[0])
        h.connectTo(offset.getPlug("input3D")[1])
        squared = graph._node("vectorProduct", "offsetSquared")
        squared.getPlug("operation").set(1)
        offset.getPlug("output3D").connectTo(squared.getPlug("input1"))
        offset.getPlug("output3D").connectTo(squared.getPlug("input2"))
        root = graph._node("multiplyDivide", "lengthRoot")
        root.getPlug("operation").set(3)
        root.getPlug("input2X").set(0.5)
        squared.getPlug("outputX").connectTo(root.getPlug("input1X"))
        root.getPlug("outputX").connectTo(owner.getPlug("length"))
        v = graph._node("vectorProduct", "aim")
        v.getPlug("operation").set(0)
        v.getPlug("normalizeOutput").set(True)
        offset.getPlug("output3D").connectTo(v.getPlug("input1"))

        # E = D - closedLength、total = clamp(E, 0, Σs)、overExtension = E - total
        raw = graph._node("plusMinusAverage", "rawExtension")
        raw.getPlug("operation").set(2)
        owner.getPlug("length").connectTo(raw.getPlug("input1D")[0])
        owner.getPlug("closedLength").connectTo(raw.getPlug("input1D")[1])
        strokeSum = graph._node("plusMinusAverage", "strokeSum")
        for index in range(stages):
            owner.getPlug("stageStroke")[index].connectTo(strokeSum.getPlug("input1D")[index])
        limit = graph._node("clamp", "extensionLimit")
        strokeSum.getPlug("output1D").connectTo(limit.getPlug("maxR"))
        raw.getPlug("output1D").connectTo(limit.getPlug("inputR"))
        total = limit.getPlug("outputR")
        total.connectTo(owner.getPlug("extension"))
        over = graph._node("plusMinusAverage", "overExtensionRaw")
        over.getPlug("operation").set(2)
        raw.getPlug("output1D").connectTo(over.getPlug("input1D")[0])
        total.connectTo(over.getPlug("input1D")[1])
        over.getPlug("output1D").connectTo(owner.getPlug("overExtension"))

        # 均等の割合 total / max(Σs, 1e-6)
        safe = graph._node("clamp", "strokeSumSafe")
        safe.getPlug("minR").set(1e-6)
        safe.getPlug("maxR").set(1e12)
        strokeSum.getPlug("output1D").connectTo(safe.getPlug("inputR"))
        ratio = graph._node("multiplyDivide", "uniformRatio")
        ratio.getPlug("operation").set(2)
        total.connectTo(ratio.getPlug("input1X"))
        safe.getPlug("outputR").connectTo(ratio.getPlug("input2X"))

        # 向き R × Q(u→v)
        arc = graph._node("angleBetween", "aimArc")
        u.getPlug("output").connectTo(arc.getPlug("vector1"))
        v.getPlug("output").connectTo(arc.getPlug("vector2"))
        arc.getPlug("angle").connectTo(owner.getPlug("bendAngle"))

        def frame(label, distance, output):
            """軸上で distance(cm)だけ進んだ位置と R × Q(u→v) の向きの行列を output へ出力する。"""
            slide = graph._node("multiplyDivide", label + "Slide")
            v.getPlug("output").connectTo(slide.getPlug("input1"))
            for component in "XYZ":
                distance.connectTo(slide.getPlug("input2" + component))
            position = graph._node("plusMinusAverage", label + "Position")
            h.connectTo(position.getPlug("input3D")[0])
            slide.getPlug("output").connectTo(position.getPlug("input3D")[1])
            turn = graph._node("composeMatrix", label + "Turn")
            arc.getPlug("euler").connectTo(turn.getPlug("inputRotate"))
            position.getPlug("output3D").connectTo(turn.getPlug("inputTranslate"))
            world = graph._node("multMatrix", label + "Frame")
            rotation.getPlug("outputMatrix").connectTo(world.getPlug("matrixIn")[0])
            turn.getPlug("outputMatrix").connectTo(world.getPlug("matrixIn")[1])
            world.getPlug("matrixSum").connectTo(output)

        # バレルは取り付け位置のまま。
        barrel = graph._node("composeMatrix", "barrelTurn")
        arc.getPlug("euler").connectTo(barrel.getPlug("inputRotate"))
        h.connectTo(barrel.getPlug("inputTranslate"))
        barrelWorld = graph._node("multMatrix", "barrelFrame")
        rotation.getPlug("outputMatrix").connectTo(barrelWorld.getPlug("matrixIn")[0])
        barrel.getPlug("outputMatrix").connectTo(barrelWorld.getPlug("matrixIn")[1])
        barrelWorld.getPlug("matrixSum").connectTo(owner.getPlug("matrix")[0])

        cumulative = None
        for index in range(stages):
            label = "stage{}".format(index + 1)
            stageStroke = owner.getPlug("stageStroke")[index]
            # 均等 g_k = ratio × s_k
            uniform = graph._node("multiplyDivide", label + "Uniform")
            ratio.getPlug("outputX").connectTo(uniform.getPlug("input1X"))
            stageStroke.connectTo(uniform.getPlug("input2X"))
            # 順番 o_k = clamp(total - Σ_{j<k} s_j, 0, s_k)
            remain = graph._node("plusMinusAverage", label + "Remain")
            remain.getPlug("operation").set(2)
            total.connectTo(remain.getPlug("input1D")[0])
            for previous in range(index):
                owner.getPlug("stageStroke")[previous].connectTo(remain.getPlug("input1D")[previous + 1])
            ordered = graph._node("clamp", label + "Ordered")
            stageStroke.connectTo(ordered.getPlug("maxR"))
            remain.getPlug("output1D").connectTo(ordered.getPlug("inputR"))
            # e_k = g_k + sequence × (o_k - g_k)
            blend = graph._node("blendTwoAttr", label + "Blend")
            owner.getPlug("sequence").connectTo(blend.getPlug("attributesBlender"))
            uniform.getPlug("outputX").connectTo(blend.getPlug("input")[0])
            ordered.getPlug("outputR").connectTo(blend.getPlug("input")[1])
            extension = owner.getPlug("stageExtension")[index]
            blend.getPlug("output").connectTo(extension)
            # 段 k+1 の位置は Σ_{j<=k} e_j。
            if cumulative is None:
                cumulative = extension
            else:
                running = graph._node("plusMinusAverage", label + "Cumulative")
                cumulative.connectTo(running.getPlug("input1D")[0])
                extension.connectTo(running.getPlug("input1D")[1])
                cumulative = running.getPlug("output1D")
            frame(label, cumulative, owner.getPlug("matrix")[index + 1])

        reach = graph._node("plusMinusAverage", "tipReach")
        owner.getPlug("closedLength").connectTo(reach.getPlug("input1D")[0])
        total.connectTo(reach.getPlug("input1D")[1])
        frame("tip", reach.getPlug("output1D"), owner.getPlug("tipMatrix"))

        owner.setAttrFlags(list(outputs) + ["bendAngle"], keyable=False, channelBox=True)
        # 位置の値はすべて内部単位(cm)のまま計算するので、UIの長さ単位で挿入された変換は係数1にする。
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        for node in added:
            node.getPlug("conversionFactor").set(1.0)
        if added:
            owner.addMembers(*added)
        return graph
