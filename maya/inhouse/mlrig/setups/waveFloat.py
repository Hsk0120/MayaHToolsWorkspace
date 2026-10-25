"""水面に浮かぶ物体(船・浮き・浮き輪)を、時間で進むトロコイド波(ゲルストナー波)の面に乗せる標準DGを構築する。"""

import math

import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution

#: 接続時にMayaが自動で挟む単位変換のノード型(containerへ所有させる)。
_CONVERSIONS = ["unitConversion", "timeToUnitConversion"]


class WaveFloat(TwistDistribution):
    """コントロールの位置の水面の上下・前後の揺れと面の傾きを、複数の波の和として求める標準DG。

    シミュレーションを使わず、波の面を位置と時刻の式で決める一般的な方法(トロコイド波の和)で、
    物体を波の面へ乗せる。前のフレームの結果は使わない(時間の積分をしない)ので、どのフレームから
    再生・スクラブしても同じ姿勢になる。sin・cosは ``composeMatrix`` で角度を回転行列にし、
    ``vectorProduct`` で(1,0,0)を回して求める。
    """

    @classmethod
    def surface(cls, x, z, time, waves, drift=1.0):
        """位置(x, z)・時刻timeの、波による変位と面の2本の接線を計算する(DGと同じ式のPython版)。

        Args:
            x (float): ワールドのX。
            z (float): ワールドのZ。
            time (float): 時刻(``time`` アトリビュートと同じ値)。
            waves (Sequence[tuple[float, float, float, float, float]]):
                各波の (amplitude, wavelength, direction(度), steepness, speed)。
            drift (float): 水平方向の揺れの割合。

        Returns:
            tuple[tuple, tuple, tuple]: (変位(dx, dy, dz), X方向の接線, Z方向の接線)。
        """
        offset = [0.0, 0.0, 0.0]
        tangent_x = [1.0, 0.0, 0.0]
        tangent_z = [0.0, 0.0, 1.0]
        for amplitude, wavelength, direction, steepness, speed in waves:
            dx, dz = math.cos(math.radians(direction)), -math.sin(math.radians(direction))
            k = 2.0 * math.pi / wavelength
            theta = k * (dx * x + dz * z - speed * time)
            sine, cosine = math.sin(theta), math.cos(theta)
            q = steepness * drift * amplitude
            offset[0] += q * dx * cosine
            offset[1] += amplitude * sine
            offset[2] += q * dz * cosine
            u, v = q * k * sine, amplitude * k * cosine
            for tangent, d in ((tangent_x, dx), (tangent_z, dz)):
                tangent[0] += -u * dx * d
                tangent[1] += v * d
                tangent[2] += -u * dz * d
        return tuple(offset), tuple(tangent_x), tuple(tangent_z)

    @classmethod
    @undoTransaction("mlrig.WaveFloat.create")
    def create(cls, control, name="waveFloat", count=2, tilt=1.0, drift=1.0, connectTime=False):
        """コントロールの入力から、波の面に乗せたワールド行列を生成する。

        Args:
            control (str | Node): 浮かせる物体の入力のtransform。アニメーターが動かすコントロールなど。
                そのワールド位置の高さを静かな水面とする。出力はこのtransform自身ではなく、
                別の受け側(船のjointなど)へ接続する。
            name (str): 一意なcontainer名。
            count (int): 重ねる波の数(1〜8)。
            tilt (float): 波の面の傾きを物体へ加える割合(0〜1)。
            drift (float): 波による水平方向(前後)の揺れの割合(0〜1)。
            connectTime (bool): Trueなら ``time1.outTime`` を ``time`` へ接続する。

        Returns:
            WaveFloat: matrix・heave・normal の所有者。各波は amplitude<i>・wavelength<i>・
            direction<i>・steepness<i>・speed<i> で調整する(既定の振幅0では生成時に姿勢が変わらない)。

        Raises:
            ValueError: controlがtransformでない場合、countが範囲外の場合、割合が範囲外・有限でない場合、
                またはnameが既に存在する場合。

        Note:
            コントロールのワールド位置を p = (px, py, pz) とする。波iの向き D_i = (cos d_i, 0, -sin d_i)
            (+XをY軸まわりに direction 度回した水平の向き)、k_i = 2π / wavelength_i、
            θ_i = k_i * (D_i・p - speed_i * time)(ラジアン)、q_i = steepness_i * drift * amplitude_i。
            変位 = Σ (q_i D_i.x cos θ_i, amplitude_i sin θ_i, q_i D_i.z cos θ_i)。
            面の接線はpx・pzでの変位の偏微分に単位の向きを足した Tx・Tz(式は :meth:`surface`)で、
            法線 N = normalize(Tz × Tx)。面の回転 R は行が (normalize(Tx), N, normalize(Tx) × N) の行列、
            Rt = slerp(単位行列, R, tilt)(``blendMatrix``)。
            matrix = コントロールの現在のワールド行列を、その位置を中心にRtで回し、変位だけ動かしたもの。
            heave は上下の変位(確認用)、normal はNの成分。steepness を大きくすると波の山が尖る
            (steepness*amplitude*k の和が1を超えると面が裏返るので、1未満に抑える)。
        """
        values = [float(value) for value in (tilt, drift)]
        if not all(math.isfinite(value) and 0 <= value <= 1 for value in values):
            raise ValueError("tilt and drift must be between 0 and 1")
        tilt, drift = values
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 8:
            raise ValueError("count must be an integer between 1 and 8")
        if mlib.ls(name):
            raise ValueError("WaveFloat container already exists: " + name)
        control = mlib.nodes.Node(control)
        if not isinstance(control, mlib.nodes.Transform):
            raise ValueError("Expected a transform")

        conversions = {node.getUuid() for node in mlib.ls(type=_CONVERSIONS)}
        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        scalar = ScalarGraph(owner)
        owner.addAttr(longName="time", attributeType="double", defaultValue=0.0, keyable=True)
        owner.addAttr(longName="tilt", attributeType="double", defaultValue=tilt, minValue=0, maxValue=1,
                      keyable=True)
        owner.addAttr(longName="drift", attributeType="double", defaultValue=drift, minValue=0, maxValue=1,
                      keyable=True)
        for index in range(count):
            suffix = str(index)
            owner.addAttr(longName="amplitude" + suffix, attributeType="double", defaultValue=0.0, keyable=True)
            owner.addAttr(longName="wavelength" + suffix, attributeType="double", defaultValue=10.0 + 4.0 * index,
                          minValue=0.01, keyable=True)
            owner.addAttr(longName="direction" + suffix, attributeType="doubleAngle",
                          defaultValue=math.radians(35.0 * index), keyable=True)
            owner.addAttr(longName="steepness" + suffix, attributeType="double", defaultValue=0.5,
                          minValue=0, maxValue=1, keyable=True)
            owner.addAttr(longName="speed" + suffix, attributeType="double", defaultValue=0.1, keyable=True)
        owner.addAttr(longName="heave", attributeType="double")
        owner.addAttr(longName="normal", attributeType="double3")
        owner.addAttr(longName="matrix", dataType="matrix")

        position = graph._node("decomposeMatrix", "position")
        control.getPlug("worldMatrix")[0].connectTo(position.getPlug("inputMatrix"))
        offsets = graph._node("plusMinusAverage", "offset")
        tangents = {}
        for role, base in (("tangentX", (1.0, 0.0, 0.0)), ("tangentZ", (0.0, 0.0, 1.0))):
            total = graph._node("plusMinusAverage", role)
            total.getPlug("input3D")[0].set(base)
            tangents[role] = total
        for index in range(count):
            suffix = str(index)
            role = "wave" + suffix
            # 波の水平の向き D = (+X を direction だけY軸まわりに回した向き)。
            heading = graph._node("composeMatrix", role + "Heading")
            owner.getPlug("direction" + suffix).connectTo(heading.getPlug("inputRotateY"))
            direction = graph._node("vectorProduct", role + "Direction")
            direction.getPlug("operation").set(3)
            direction.getPlug("input1").set((1.0, 0.0, 0.0))
            heading.getPlug("outputMatrix").connectTo(direction.getPlug("matrix"))
            # 進む距離 = D・p - speed * time、位相(度) = 360 * 距離 / wavelength。
            along = graph._node("vectorProduct", role + "Along")
            along.getPlug("operation").set(1)
            direction.getPlug("output").connectTo(along.getPlug("input1"))
            position.getPlug("outputTranslate").connectTo(along.getPlug("input2"))
            travel = scalar.multiply(role + "Travel", owner.getPlug("speed" + suffix), owner.getPlug("time"))
            distance = scalar.sum(role + "Distance", along.getPlug("outputX"), travel, subtract=True)
            cycles = scalar.multiply(role + "Cycles", distance, owner.getPlug("wavelength" + suffix), operation=2)
            degrees = scalar.multiply(role + "PhaseDegrees", cycles, 360.0)
            radians = graph._node("unitConversion", role + "PhaseRadians")
            degrees.connectTo(radians.getPlug("input"))
            radians.getPlug("conversionFactor").set(math.pi / 180.0)
            circle = graph._node("composeMatrix", role + "Circle")
            radians.getPlug("output").connectTo(circle.getPlug("inputRotateZ"))
            # (cos θ, sin θ, 0)
            trig = graph._node("vectorProduct", role + "Trig")
            trig.getPlug("operation").set(3)
            trig.getPlug("input1").set((1.0, 0.0, 0.0))
            circle.getPlug("outputMatrix").connectTo(trig.getPlug("matrix"))
            amplitude = owner.getPlug("amplitude" + suffix)
            number = scalar.multiply(role + "WaveNumber", 2.0 * math.pi, owner.getPlug("wavelength" + suffix),
                                     operation=2)
            steep = scalar.multiply(role + "SteepDrift", owner.getPlug("steepness" + suffix), owner.getPlug("drift"))
            horizontal = scalar.multiply(role + "Horizontal", steep, amplitude)
            horizontal_cos = scalar.multiply(role + "HorizontalCos", horizontal, trig.getPlug("outputX"))
            # 変位 = (Dx * qC, A * S, Dz * qC)
            offset = graph._node("multiplyDivide", role + "Offset")
            direction.getPlug("outputX").connectTo(offset.getPlug("input1X"))
            trig.getPlug("outputY").connectTo(offset.getPlug("input1Y"))
            direction.getPlug("outputZ").connectTo(offset.getPlug("input1Z"))
            horizontal_cos.connectTo(offset.getPlug("input2X"))
            amplitude.connectTo(offset.getPlug("input2Y"))
            horizontal_cos.connectTo(offset.getPlug("input2Z"))
            offset.getPlug("output").connectTo(offsets.getPlug("input3D")[index])
            # W = (-u Dx, v, -u Dz)、u = q k S、v = A k C。接線への寄与は W * Dx と W * Dz。
            u = scalar.multiply(role + "U", scalar.multiply(role + "QK", horizontal, number),
                                trig.getPlug("outputY"))
            negative_u = scalar.multiply(role + "NegativeU", u, -1.0)
            v = scalar.multiply(role + "V", scalar.multiply(role + "AK", amplitude, number),
                                trig.getPlug("outputX"))
            slope = graph._node("multiplyDivide", role + "Slope")
            direction.getPlug("outputX").connectTo(slope.getPlug("input1X"))
            direction.getPlug("outputZ").connectTo(slope.getPlug("input1Z"))
            slope.getPlug("input1Y").set(1.0)
            negative_u.connectTo(slope.getPlug("input2X"))
            v.connectTo(slope.getPlug("input2Y"))
            negative_u.connectTo(slope.getPlug("input2Z"))
            for tangent_role, component in (("tangentX", "outputX"), ("tangentZ", "outputZ")):
                part = graph._node("multiplyDivide", role + tangent_role[0].upper() + tangent_role[1:])
                slope.getPlug("output").connectTo(part.getPlug("input1"))
                for axis in "XYZ":
                    direction.getPlug(component).connectTo(part.getPlug("input2" + axis))
                part.getPlug("output").connectTo(tangents[tangent_role].getPlug("input3D")[index + 1])
        offsets.getPlug("output3Dy").connectTo(owner.getPlug("heave"))

        # 面の回転: 行 = (X' = normalize(Tx), N = normalize(Tz × Tx), Z' = X' × N)。
        normal = graph._node("vectorProduct", "normal")
        normal.getPlug("operation").set(2)
        normal.getPlug("normalizeOutput").set(True)
        tangents["tangentZ"].getPlug("output3D").connectTo(normal.getPlug("input1"))
        tangents["tangentX"].getPlug("output3D").connectTo(normal.getPlug("input2"))
        normal.getPlug("output").connectTo(owner.getPlug("normal"))
        side = graph._node("vectorProduct", "side")
        side.getPlug("operation").set(0)
        side.getPlug("normalizeOutput").set(True)
        tangents["tangentX"].getPlug("output3D").connectTo(side.getPlug("input1"))
        front = graph._node("vectorProduct", "front")
        front.getPlug("operation").set(2)
        front.getPlug("normalizeOutput").set(True)
        side.getPlug("output").connectTo(front.getPlug("input1"))
        normal.getPlug("output").connectTo(front.getPlug("input2"))
        frame = graph._node("fourByFourMatrix", "surfaceFrame")
        for row, source in enumerate((side, normal, front)):
            for column, axis in enumerate("XYZ"):
                source.getPlug("output" + axis).connectTo(frame.getPlug("in{}{}".format(row, column)))
        blend = graph._node("blendMatrix", "tiltBlend")
        blend.getPlug("inputMatrix").set(Matrix())
        frame.getPlug("output").connectTo(blend.getPlug("target")[0]["targetMatrix"])
        owner.getPlug("tilt").connectTo(blend.getPlug("target")[0]["weight"])

        # コントロールの位置を中心に回し、変位を足す: W * T(-p) * Rt * T(p + 変位)
        negative = graph._node("multiplyDivide", "positionNegative")
        position.getPlug("outputTranslate").connectTo(negative.getPlug("input1"))
        negative.getPlug("input2").set((-1, -1, -1))
        to_origin = graph._node("composeMatrix", "toOrigin")
        negative.getPlug("output").connectTo(to_origin.getPlug("inputTranslate"))
        moved = graph._node("plusMinusAverage", "movedPosition")
        position.getPlug("outputTranslate").connectTo(moved.getPlug("input3D")[0])
        offsets.getPlug("output3D").connectTo(moved.getPlug("input3D")[1])
        from_origin = graph._node("composeMatrix", "fromOrigin")
        moved.getPlug("output3D").connectTo(from_origin.getPlug("inputTranslate"))
        result = graph._node("multMatrix", "result")
        control.getPlug("worldMatrix")[0].connectTo(result.getPlug("matrixIn")[0])
        to_origin.getPlug("outputMatrix").connectTo(result.getPlug("matrixIn")[1])
        blend.getPlug("outputMatrix").connectTo(result.getPlug("matrixIn")[2])
        from_origin.getPlug("outputMatrix").connectTo(result.getPlug("matrixIn")[3])
        result.getPlug("matrixSum").connectTo(owner.getPlug("matrix"))
        owner.setAttrFlags(["heave", "normal"], keyable=False, channelBox=True)
        if connectTime:
            mlib.nodes.Node("time1").getPlug("outTime").connectTo(owner.getPlug("time"))
        added = [node for node in mlib.ls(type=_CONVERSIONS) if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph
