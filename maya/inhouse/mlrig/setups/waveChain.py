"""joint列の各関節へ位相をずらした正弦波の回転を重ね、尻尾・触手のうねりを標準DGで構築する。"""

import math

import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution


class WaveChain(TwistDistribution):
    """位相phaseを進めると、根元から先端へ進む波として各関節が軸まわりに揺れる標準DG。

    正弦はcomposeMatrixで角度を回転行列にし、vectorProductで(1,0,0)を回したY成分として求める。
    フレームごとのPythonやエクスプレッションは使わず、phaseを時間へ接続すれば自動で動く。
    """

    @classmethod
    def waveAngles(cls, count, phase, amplitude, wavelength, rootWeight=1.0, tipWeight=1.0):
        """各関節の回転角を計算する(DGと同じ式のPython版)。

        Args:
            count (int): 関節の数。
            phase (float): 位相(度)。
            amplitude (float): 振幅(度)。
            wavelength (float): 1周期あたりの関節数。0より大きい。
            rootWeight (float): 根元の関節の振幅の倍率。
            tipWeight (float): 先端の関節の振幅の倍率。

        Returns:
            list[float]: 各関節の回転角(度)。
        """
        angles = []
        for index in range(count):
            ratio = index / (count - 1) if count > 1 else 0.0
            weight = rootWeight + (tipWeight - rootWeight) * ratio
            angles.append(amplitude * weight * math.sin(math.radians(phase - 360.0 * index / wavelength)))
        return angles

    @classmethod
    @undoTransaction("mlrig.WaveChain.create")
    def create(cls, joints, name="waveChain", axis="z", amplitude=0.0, wavelength=4.0, rootWeight=0.3,
               tipWeight=1.0):
        """各関節の親空間行列を生成する。

        Args:
            joints (list[str | Node]): 根元から先端へ、親子に並んだ2つ以上のtransform。
            name (str): 一意なcontainer名。
            axis (str): 各関節のローカルで揺らす回転軸x/y/z。
            amplitude (float): 振幅。度、-180〜180。既定の0では生成時に姿勢が変わらない。
            wavelength (float): 1周期あたりの関節数。0.1以上。
            rootWeight (float): 根元の関節の振幅の倍率。0〜1。
            tipWeight (float): 先端の関節の振幅の倍率。0〜1。

        Returns:
            WaveChain: matrix0〜matrixN-1・angle0〜angleN-1の所有者。containerのphaseで波が進む。

        Raises:
            ValueError: 関節の並び・軸・値が不正な場合、またはnameが既に存在する場合。

        Note:
            関節iの重み w_i = rootWeight + (tipWeight-rootWeight)*i/(N-1)、
            角度 θ_i = amplitude * w_i * sin(phase - 360*i/wavelength)(度)。
            出力 matrix_i は、関節iの現在のローカル行列(matrix * offsetParentMatrix)の前に、
            ローカルのaxisまわりのθ_iの回転を掛けた行列(行ベクトル規約)。位置は入力のまま。
            出力の関節も入力と同じ親子に並べ、各出力をoffsetParentMatrixへ接続する。
            負・非一様scaleは対象外。
        """
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be x, y or z")
        for value in (amplitude, wavelength, rootWeight, tipWeight):
            if not math.isfinite(value):
                raise ValueError("amplitude, wavelength and weights must be finite")
        if not -180 <= amplitude <= 180:
            raise ValueError("amplitude must be between -180 and 180 degrees")
        if wavelength < 0.1:
            raise ValueError("wavelength must be at least 0.1 joints")
        if not (0 <= rootWeight <= 1 and 0 <= tipWeight <= 1):
            raise ValueError("rootWeight and tipWeight must be between 0 and 1")
        if mlib.objExists(name):
            raise ValueError("WaveChain container already exists: " + name)
        joints = [mlib.nodes.Node(joint) for joint in joints]
        if len(joints) < 2 or any(not isinstance(joint, mlib.nodes.Transform) for joint in joints):
            raise ValueError("Expected two or more transforms")
        for parent, child in zip(joints, joints[1:]):
            actual = child.getParent()
            if actual is None or actual != parent:
                raise ValueError("Each joint must be the direct child of the previous one")
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        scalar = ScalarGraph(owner)
        owner.addAttr(longName="phase", attributeType="double", defaultValue=0.0, keyable=True)
        owner.addAttr(longName="amplitude", attributeType="double", defaultValue=amplitude,
                      minValue=-180, maxValue=180, keyable=True)
        owner.addAttr(longName="wavelength", attributeType="double", defaultValue=wavelength,
                      minValue=0.1, keyable=True)
        for attr, value in (("rootWeight", rootWeight), ("tipWeight", tipWeight)):
            owner.addAttr(longName=attr, attributeType="double", defaultValue=value,
                          minValue=0, maxValue=1, keyable=True)
        count = len(joints)
        for index in range(count):
            owner.addAttr(longName="angle" + str(index), attributeType="double")
            owner.addAttr(longName="matrix" + str(index), dataType="matrix")
        weight_range = scalar.sum("weightRange", owner.getPlug("tipWeight"), owner.getPlug("rootWeight"),
                                  subtract=True)
        rotate = "inputRotate" + axis.upper()
        for index, joint in enumerate(joints):
            role = "joint" + str(index)
            # 位相の遅れ 360*i/wavelength を引いた角度の正弦を、回転行列のY成分として求める。
            delay = scalar.multiply(role + "Delay", 360.0 * index, owner.getPlug("wavelength"), operation=2)
            argument = scalar.sum(role + "Argument", owner.getPlug("phase"), delay, subtract=True)
            radians = graph._node("unitConversion", role + "ArgumentRadians")
            argument.connectTo(radians.getPlug("input"))
            radians.getPlug("conversionFactor").set(math.pi / 180)
            circle = graph._node("composeMatrix", role + "Circle")
            radians.getPlug("output").connectTo(circle.getPlug("inputRotateZ"))
            sine = graph._node("vectorProduct", role + "Sine")
            sine.getPlug("operation").set(3)
            sine.getPlug("input1").set((1, 0, 0))
            circle.getPlug("outputMatrix").connectTo(sine.getPlug("matrix"))
            ratio = index / (count - 1)
            weight = scalar.sum(role + "Weight", owner.getPlug("rootWeight"),
                                scalar.multiply(role + "WeightOffset", weight_range, ratio))
            scaled = scalar.multiply(role + "Scaled", owner.getPlug("amplitude"), weight)
            scalar.multiply(role + "AngleRaw", scaled, sine.getPlug("outputY")).connectTo(
                owner.getPlug("angle" + str(index))
            )
            # 関節のローカル行列の前に、ローカルのaxisまわりの回転を掛ける。
            wave = graph._node("composeMatrix", role + "Wave")
            angle_radians = graph._node("unitConversion", role + "AngleRadians")
            owner.getPlug("angle" + str(index)).connectTo(angle_radians.getPlug("input"))
            angle_radians.getPlug("conversionFactor").set(math.pi / 180)
            angle_radians.getPlug("output").connectTo(wave.getPlug(rotate))
            local = graph._node("multMatrix", role + "Local")
            wave.getPlug("outputMatrix").connectTo(local.getPlug("matrixIn")[0])
            joint.getPlug("matrix").connectTo(local.getPlug("matrixIn")[1])
            joint.getPlug("offsetParentMatrix").connectTo(local.getPlug("matrixIn")[2])
            local.getPlug("matrixSum").connectTo(owner.getPlug("matrix" + str(index)))
        owner.setAttrFlags(["angle" + str(index) for index in range(count)], keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph
