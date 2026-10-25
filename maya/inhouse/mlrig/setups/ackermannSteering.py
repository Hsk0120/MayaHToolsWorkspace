"""車の前輪の左右の切れ角を、アッカーマンの幾何(内輪を外輪より大きく切る)で求める標準DGを構築する。"""

import math

import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution

#: 左右の名前(出力のアトリビュート名の先頭)と、正の切れ角のときの内輪側(+1)・外輪側(-1)。
SIDES = (("left", 1.0), ("right", -1.0))


class AckermannSteering(TwistDistribution):
    """1つの切れ角(後輪の軸の中央から見た、仮想の中央の前輪の角度)から、左右の前輪の角度を求める標準DG。

    旋回中心は後輪の軸の延長上にあり、前輪はそれぞれ旋回中心へ向く円の接線を向く。
    軸距 ``L``・輪距 ``T``・中央の切れ角 ``δ`` のとき、内輪の側を ``s=+1`` 、外輪の側を ``s=-1`` として
    ``tan(δ_s) = L*sinδ / (L*cosδ - s*(T/2)*sinδ)`` (= ``L / (R - s*T/2)`` 、 ``R = L/tanδ``)。
    ``ackermann`` (0〜1)で、全ての車輪を同じ角度にする平行の切れ方(0)と、アッカーマンの幾何(1)を混ぜる。
    フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def angles(cls, steer, wheelBase, trackWidth, ackermann=1.0):
        """左右の前輪の切れ角を計算する(DGと同じ式のPython版)。

        Args:
            steer (float): 中央の切れ角(度)。正なら左へ曲がる(左の車輪が内輪)。
            wheelBase (float): 軸距(前後の車軸の間の距離)。
            trackWidth (float): 輪距(左右の前輪の間の距離)。wheelBaseと同じ単位。
            ackermann (float): アッカーマンの割合。0で平行、1でアッカーマンの幾何。

        Returns:
            tuple[float, float]: (左の角度, 右の角度)(度)。
        """
        radian = math.radians(steer)
        result = []
        for _, side in SIDES:
            exact = math.degrees(math.atan2(wheelBase * math.sin(radian),
                                            wheelBase * math.cos(radian) - side * trackWidth * 0.5 * math.sin(radian)))
            result.append(steer + ackermann * (exact - steer))
        return tuple(result)

    @classmethod
    @undoTransaction("mlrig.AckermannSteering.create")
    def create(cls, left, right, wheelBase, trackWidth=None, name="ackermannSteering", axis="y", driver=None,
               driverRatio=1.0, ackermann=1.0, connect=True):
        """左右の前輪のtransformの回転を、1つの切れ角から駆動する。

        Args:
            left (str | Node): 左の前輪(正の切れ角で内輪になる側)のtransform。
            right (str | Node): 右の前輪のtransform。
            wheelBase (float): 軸距(前輪の軸と後輪の軸の距離、cm、0より大きい)。
            trackWidth (float | None): 輪距(cm、0より大きい)。Noneなら生成時の左右の車輪のワールド位置の距離(cm)。
                角度は ``trackWidth / wheelBase`` の比だけで決まるので、UI単位によらず2つは cm で渡す。
            name (str): 一意なcontainer名。
            axis (str): 車輪のローカルの切る軸 x/y/z。この軸の正の回転で車輪が左の車輪の側へ向くこと。
            driver (str | Plug | None): 切れ角を駆動する角度のplug(ハンドルの rotateZ など)。
                指定すると ``steer = (driver - 生成時の値) * driverRatio`` になる。
            driverRatio (float): driver に掛ける比(ハンドルの回転に対する切れ角の割合)。
            ackermann (float): アッカーマンの割合の初期値(0〜1)。
            connect (bool): Trueなら左右の車輪の ``rotate<axis>`` へ出力を接続する。

        Returns:
            AckermannSteering: leftAngle・rightAngle の所有者。containerに steer・wheelBase・trackWidth・
                ackermann(keyable、driverを渡した場合は steer は駆動される)・driverRatio を持つ。

        Raises:
            ValueError: 軸・距離・割合が不正な場合、車輪がtransformでない・同じ場合、輪距を測れない場合、
                driverが角度のplugでない場合、接続済みの回転がある場合、またはnameが既に存在する場合。

        Note:
            車輪の ``rotate<axis>`` = 生成時の値 + ``<side>Angle`` 。生成時の steer は0なので跳ねない。
            sin・cos は composeMatrix の回転と vectorProduct、atan2 は angleBetween の euler(符号付き)で求める。
            どれも単位を持たない値か角度のまま渡し、angleBetween の vector2 へは係数1の unitConversion を明示するので、
            UI単位を変えても自動の単位変換は入らない。
        """
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be x, y or z")
        values = [wheelBase, driverRatio, ackermann] + ([] if trackWidth is None else [trackWidth])
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError("wheelBase, trackWidth, driverRatio and ackermann must be finite")
        if wheelBase <= 0.0 or (trackWidth is not None and trackWidth <= 0.0):
            raise ValueError("wheelBase and trackWidth must be greater than 0")
        if not 0.0 <= ackermann <= 1.0:
            raise ValueError("ackermann must be between 0 and 1")
        if mlib.ls(name):
            raise ValueError("AckermannSteering container already exists: " + name)
        wheels = [mlib.nodes.Node(left), mlib.nodes.Node(right)]
        if any(not isinstance(wheel, mlib.nodes.Transform) for wheel in wheels):
            raise ValueError("Expected transforms for the wheels")
        if wheels[0].getFullName() == wheels[1].getFullName():
            raise ValueError("The left and right wheels must be different nodes")
        if trackWidth is None:
            points = [Matrix(wheel.getPlug("worldMatrix")[0].get()) for wheel in wheels]
            trackWidth = math.sqrt(sum((points[0][12 + i] - points[1][12 + i]) ** 2 for i in range(3)))
            if trackWidth < 1e-6:
                raise ValueError("Could not measure trackWidth: the wheels are at the same position")
        if driver is not None:
            driver = mlib.getPlug(str(driver))
            if driver.getDataType() != "doubleAngle":
                raise ValueError("driver must be an angle plug")
        channel = "rotate" + axis.upper()
        if connect:
            for wheel in wheels:
                if wheel.getPlug(channel).getSource() is not None:
                    raise ValueError("The rotation of the wheel is already connected: " + wheel.getFullName())

        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        scalar = ScalarGraph(owner)
        owner.addAttr(longName="steer", attributeType="doubleAngle", defaultValue=0.0, keyable=True)
        owner.addAttr(longName="wheelBase", attributeType="double", defaultValue=float(wheelBase), minValue=1e-6,
                      keyable=True)
        owner.addAttr(longName="trackWidth", attributeType="double", defaultValue=float(trackWidth), minValue=0.0,
                      keyable=True)
        owner.addAttr(longName="ackermann", attributeType="double", defaultValue=float(ackermann), minValue=0.0,
                      maxValue=1.0, keyable=True)
        owner.addAttr(longName="driverRatio", attributeType="double", defaultValue=float(driverRatio), keyable=True)
        for side, _ in SIDES:
            owner.addAttr(longName=side + "Angle", attributeType="doubleAngle")
        owner.setAttrFlags(["leftAngle", "rightAngle"], keyable=False, channelBox=True)
        steer = owner.getPlug("steer")

        if driver is not None:
            # steer = (driver - 生成時の値) * driverRatio(角度のまま足し引きし、単位変換ノードを入れない)。
            delta = graph._node("animBlendNodeAdditiveDA", "driverDelta")
            driver.connectTo(delta.getPlug("inputA"))
            delta.getPlug("inputB").set(driver.get())
            delta.getPlug("weightA").set(1.0)
            delta.getPlug("weightB").set(-1.0)
            scaled = graph._node("animBlendNodeAdditiveDA", "driverScale")
            delta.getPlug("output").connectTo(scaled.getPlug("inputA"))
            owner.getPlug("driverRatio").connectTo(scaled.getPlug("weightA"))
            scaled.getPlug("weightB").set(0.0)
            scaled.getPlug("output").connectTo(steer)

        # (cosδ, sinδ, 0) = (1, 0, 0) を Z 回りに δ 回した方向。
        rotation = graph._node("composeMatrix", "steerRotation")
        steer.connectTo(rotation.getPlug("inputRotateZ"))
        direction = graph._node("vectorProduct", "steerDirection")
        direction.getPlug("operation").set(3)
        direction.getPlug("input1").set((1.0, 0.0, 0.0))
        rotation.getPlug("outputMatrix").connectTo(direction.getPlug("matrix"))
        # (L*cosδ, L*sinδ, (T/2)*sinδ)
        half = scalar.multiply("halfTrack", owner.getPlug("trackWidth"), 0.5)
        terms = graph._node("multiplyDivide", "terms")
        direction.getPlug("outputX").connectTo(terms.getPlug("input1X"))
        direction.getPlug("outputY").connectTo(terms.getPlug("input1Y"))
        direction.getPlug("outputY").connectTo(terms.getPlug("input1Z"))
        owner.getPlug("wheelBase").connectTo(terms.getPlug("input2X"))
        owner.getPlug("wheelBase").connectTo(terms.getPlug("input2Y"))
        half.connectTo(terms.getPlug("input2Z"))
        # 平行の切れ方の重み = 1 - ackermann
        parallel = scalar.sum("parallelWeight", 1.0, owner.getPlug("ackermann"), subtract=True)

        for wheel, (side, sign) in zip(wheels, SIDES):
            # 車輪から旋回中心への方向に垂直な向き: (L*cosδ - s*(T/2)*sinδ, L*sinδ)。atan2 は angleBetween の符号付きeuler。
            vector = graph._node("plusMinusAverage", side + "Vector")
            vector.getPlug("operation").set(2 if sign > 0 else 1)
            terms.getPlug("outputX").connectTo(vector.getPlug("input3D[0].input3Dx"))
            terms.getPlug("outputY").connectTo(vector.getPlug("input3D[0].input3Dy"))
            terms.getPlug("outputZ").connectTo(vector.getPlug("input3D[1].input3Dx"))
            angle = graph._node("angleBetween", side + "Exact")
            angle.getPlug("vector1").set((1.0, 0.0, 0.0))
            # 版によって vector2 が長さの型で、mmでは自動の単位変換(×0.1)が入るので、係数1の変換を明示する。
            unit = graph._node("unitConversion", side + "VectorUnit")
            unit.getPlug("conversionFactor").set(1.0)
            vector.getPlug("output3D").connectTo(unit.getPlug("input"))
            unit.getPlug("output").connectTo(angle.getPlug("vector2"))
            # angle = ackermann * exact + (1 - ackermann) * steer
            blend = graph._node("animBlendNodeAdditiveDA", side + "Blend")
            angle.getPlug("eulerZ").connectTo(blend.getPlug("inputA"))
            owner.getPlug("ackermann").connectTo(blend.getPlug("weightA"))
            steer.connectTo(blend.getPlug("inputB"))
            parallel.connectTo(blend.getPlug("weightB"))
            blend.getPlug("output").connectTo(owner.getPlug(side + "Angle"))
            if connect:
                rotate = graph._node("animBlendNodeAdditiveDA", side + "Rotate")
                owner.getPlug(side + "Angle").connectTo(rotate.getPlug("inputA"))
                rotate.getPlug("inputB").set(wheel.getPlug(channel).get())
                rotate.getPlug("weightA").set(1.0)
                rotate.getPlug("weightB").set(1.0)
                rotate.getPlug("output").connectTo(wheel.getPlug(channel))
        return graph
