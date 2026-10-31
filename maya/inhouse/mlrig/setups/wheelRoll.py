"""車体の前進距離から、滑らずに転がる車輪の回転を標準DGで構築する。"""

import math

import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution


class WheelRoll(TwistDistribution):
    """車体の移動量を前進方向へ投影し、半径で割った角度だけ車輪を自転させる標準DG。

    回転角 = 前進距離 / 半径(ラジアン)なので、接地点が地面に対して滑らない。
    フレームごとのPythonや履歴(前のフレームの値)は使わず、現在の位置だけから求める。
    """

    @classmethod
    def spinAngle(cls, travel, radius, direction=1, offset=0.0):
        """前進距離から車輪の回転角を計算する(DGと同じ式のPython版)。

        Args:
            travel (float): 前進距離(cm)。
            radius (float): 車輪の半径(cm)。0より大きい。
            direction (int): 回転の向きの符号。1または-1。
            offset (float): 足す角度(度)。

        Returns:
            float: 回転角(度)。
        """
        return direction * math.degrees(travel / radius) + offset

    @classmethod
    @undoTransaction("mlrig.WheelRoll.create")
    def create(cls, vehicle, wheel, radius, name="wheelRoll", forwardAxis="z", spinAxis="x", direction=1):
        """車輪の親空間行列を生成する。

        Args:
            vehicle (str | Node): 動かす車体(またはその移動用コントローラー)のtransform。
            wheel (str | Node): 車輪のtransform。回転中心を車軸に置く。
            radius (float): 車輪の半径。cm、0より大きい。
            name (str): 一意なcontainer名。
            forwardAxis (str): vehicleの親空間での前進方向の軸x/y/z。
            spinAxis (str): wheelのローカルでの車軸(自転軸)x/y/z。
            direction (int): 前進したときの自転の向きの符号。1または-1。
                上がY・前がZ・車軸がXなら、+X回転で前側が下がるので1。

        Returns:
            WheelRoll: matrix・travel・spin・revolutionsの所有者。

        Raises:
            ValueError: 軸・半径・符号が不正な場合、またはnameが既に存在する場合。

        Note:
            基準は生成時の姿勢。vehicleのローカル行列(matrix * offsetParentMatrix)の位置Tと生成時の位置T0から、
            travel = (T - T0)・forwardAxis(親空間、cm)、
            spin = direction * travel/radius(ラジアンを度へ) + offset、revolutions = spin/360。
            出力 matrix = R_spinAxis(spin) * (wheelの matrix * offsetParentMatrix)(行ベクトル規約)。
            前進方向は親空間の固定の軸で、曲がりながらの移動(経路の長さ)は扱わない。
            負・非一様scaleは対象外。
        """
        axes = ("x", "y", "z")
        if forwardAxis not in axes or spinAxis not in axes:
            raise ValueError("forwardAxis and spinAxis must be x, y or z")
        if direction not in (1, -1):
            raise ValueError("direction must be 1 or -1")
        if not math.isfinite(radius) or radius <= 0:
            raise ValueError("radius must be a finite value greater than 0")
        if mlib.objExists(name):
            raise ValueError("WheelRoll container already exists: " + name)
        vehicle, wheel = mlib.nodes.Node(vehicle), mlib.nodes.Node(wheel)
        if vehicle == wheel or any(
            not isinstance(node, mlib.nodes.Transform) for node in (vehicle, wheel)
        ):
            raise ValueError("Expected two different transforms for the vehicle and the wheel")
        rest = Matrix(vehicle.getPlug("matrix").get()) * Matrix(vehicle.getPlug("offsetParentMatrix").get())
        rest_position = [rest[12], rest[13], rest[14]]
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        scalar = ScalarGraph(owner)
        owner.addAttr(longName="radius", attributeType="double", defaultValue=radius, minValue=1e-4, keyable=True)
        owner.addAttr(longName="offset", attributeType="double", defaultValue=0.0, keyable=True)
        outputs = ("travel", "spin", "revolutions")
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        owner.addAttr(longName="matrix", dataType="matrix")

        # 車体のローカル位置(cm)。vectorProductで原点を変換し、長さの単位変換を挟まずに取り出す。
        local = graph._node("multMatrix", "vehicleLocal")
        vehicle.getPlug("matrix").connectTo(local.getPlug("matrixIn")[0])
        vehicle.getPlug("offsetParentMatrix").connectTo(local.getPlug("matrixIn")[1])
        position = graph._node("vectorProduct", "vehiclePosition")
        position.getPlug("operation").set(4)
        position.getPlug("input1").set((0, 0, 0))
        local.getPlug("matrixSum").connectTo(position.getPlug("matrix"))
        moved = graph._node("plusMinusAverage", "moved")
        moved.getPlug("operation").set(2)
        position.getPlug("output").connectTo(moved.getPlug("input3D")[0])
        moved.getPlug("input3D")[1].set(rest_position)
        travel = graph._node("vectorProduct", "travelRaw")
        travel.getPlug("operation").set(1)
        travel.getPlug("normalizeOutput").set(False)
        moved.getPlug("output3D").connectTo(travel.getPlug("input1"))
        travel.getPlug("input2").set([float(axis == forwardAxis) for axis in axes])
        travel.getPlug("outputX").connectTo(owner.getPlug("travel"))

        # spin = direction * travel/radius * 180/pi + offset(度)。
        ratio = scalar.multiply("ratio", owner.getPlug("travel"), owner.getPlug("radius"), operation=2)
        degrees = scalar.multiply("spinDegrees", ratio, direction * 180.0 / math.pi)
        scalar.sum("spinRaw", degrees, owner.getPlug("offset")).connectTo(owner.getPlug("spin"))
        scalar.multiply("revolutionsRaw", owner.getPlug("spin"), 360.0, operation=2).connectTo(
            owner.getPlug("revolutions")
        )

        # 車輪のローカル行列の前に、車軸まわりの自転を掛ける。
        spin = graph._node("composeMatrix", "spinRotation")
        radians = graph._node("unitConversion", "spinRadians")
        owner.getPlug("spin").connectTo(radians.getPlug("input"))
        radians.getPlug("conversionFactor").set(math.pi / 180)
        radians.getPlug("output").connectTo(spin.getPlug("inputRotate" + spinAxis.upper()))
        result = graph._node("multMatrix", "result")
        spin.getPlug("outputMatrix").connectTo(result.getPlug("matrixIn")[0])
        wheel.getPlug("matrix").connectTo(result.getPlug("matrixIn")[1])
        wheel.getPlug("offsetParentMatrix").connectTo(result.getPlug("matrixIn")[2])
        result.getPlug("matrixSum").connectTo(owner.getPlug("matrix"))
        owner.setAttrFlags(list(outputs), keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            owner.addMembers(*added)
        return graph
