"""閉じた曲線に沿って、キャタピラ・ベルトの板を等間隔で巡回させる標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

#: motionPath の frontAxis・upAxis に渡す軸の番号。
AXES = {"x": 0, "y": 1, "z": 2}


class TreadBelt(TwistDistribution):
    """閉じた曲線の上を、送り量に合わせて板(履帯・ベルトの駒)が一周し続ける標準DG。

    i番目の板の位置は弧長の割合 ``f_i = frac(i / count + phase + distance / length)`` (length は曲線の
    ワールドでの長さ)。``frac`` は 0→0・1→1 の直線キーを前後とも cycle で繰り返す animCurveUU で求め、
    motionPath(fractionMode)が曲線上の位置と向きを出す。上方向は曲線のtransformの回転に付いて回る
    ``normal`` なので、駆動輪の周りを回っても板が裏返らない。フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def fractions(cls, count, distance, length, phase=0.0):
        """各板の弧長の割合を計算する(DGと同じ式のPython版)。

        Args:
            count (int): 板の数。
            distance (float): 送り量(曲線と同じ長さの単位)。
            length (float): 曲線の長さ。
            phase (float): 一周を1とした、全体のずらし量。

        Returns:
            list[float]: 各板の、曲線の始点からの弧長の割合(0以上1未満)。
        """
        return [(index / float(count) + phase + distance / length) % 1.0 for index in range(count)]

    @classmethod
    @undoTransaction("mlrig.TreadBelt.create")
    def create(cls, curve, count, name="treadBelt", normal=(0.0, 0.0, 1.0), frontAxis="x", upAxis="z",
               driver=None):
        """閉じた曲線に沿って巡回する count 枚の板のワールド行列を生成する。

        Args:
            curve (str | Node): 閉じた(closed/periodic)NURBS曲線のtransform、またはnurbsCurveシェイプ。
            count (int): 板の数(1以上)。一周に等間隔(弧長)で並ぶ。
            name (str): 一意なcontainer名。
            normal (Sequence[float]): 曲線のローカル空間での、ベルトの面の法線(板の upAxis が向く向き)。
            frontAxis (str): 板のローカルで、進む向き(曲線の接線)へ向ける軸 x/y/z。
            upAxis (str): 板のローカルで、normal へ向ける軸 x/y/z(frontAxisと別の軸)。
            driver (str | Plug | None): 送り量を駆動する長さのplug(車体の translateX など)。
                指定すると ``distance = driver - 生成時の値`` になり、生成時は板が動かない。

        Returns:
            TreadBelt: matrix<i>・fraction<i>・length の所有者。containerに distance(長さ)・phase を持つ。

        Raises:
            ValueError: 曲線が無い・開いている場合、count・軸・normalが不正な場合、
                driverが長さの数値plugでない場合、またはnameが既に存在する場合。

        Note:
            distance が正なら曲線の向き(パラメーターの増える向き)へ送る。曲線の長さは curveInfo で毎回求めるので、
            曲線を変形させても間隔は弧長で等しいまま。出力はワールド行列なので、ワールド直下のtransformの
            offsetParentMatrixへ接続する。motionPath の uValue は長さの型なので、割合は係数1の unitConversion で
            渡し、UI単位がmmでも値が変わらないようにする。駆動輪の回転は WheelRoll と同じ distance で駆動できる。
        """
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("count must be an integer of 1 or more")
        if frontAxis not in AXES or upAxis not in AXES or frontAxis == upAxis:
            raise ValueError("frontAxis and upAxis must be different axes of x, y or z")
        normal = [float(value) for value in normal]
        if len(normal) != 3 or not all(math.isfinite(value) for value in normal) or \
                math.sqrt(sum(value * value for value in normal)) < 1e-8:
            raise ValueError("normal must be a finite non-zero 3D vector")
        if mlib.ls(name):
            raise ValueError("TreadBelt container already exists: " + name)
        shape = mlib.nodes.Node(curve)
        if shape.getType() != "nurbsCurve":
            shapes = [s for s in (shape.getShapes() if isinstance(shape, mlib.nodes.Transform) else [])
                      if s.getType() == "nurbsCurve"]
            if not shapes:
                raise ValueError("Expected a NURBS curve transform or shape")
            shape = shapes[0]
        if shape.getPlug("form").get() == 0:
            raise ValueError("The curve must be closed or periodic: " + shape.getFullName())
        if driver is not None:
            driver = mlib.getPlug(str(driver))
            if driver.getDataType() != "doubleLinear":
                raise ValueError("driver must be a linear (distance) plug")

        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        owner.addAttr(longName="distance", attributeType="doubleLinear", defaultValue=0.0, keyable=True)
        owner.addAttr(longName="phase", attributeType="double", defaultValue=0.0, keyable=True)
        owner.addAttr(longName="length", attributeType="doubleLinear")
        outputs = ["length"]

        if driver is not None:
            # distance = driver - 生成時の値(長さのまま足し引きし、単位変換ノードを入れない)。
            delta = graph._node("animBlendNodeAdditiveDL", "driverDelta")
            driver.connectTo(delta.getPlug("inputA"))
            delta.getPlug("inputB").set(driver.get())
            delta.getPlug("weightA").set(1.0)
            delta.getPlug("weightB").set(-1.0)
            delta.getPlug("output").connectTo(owner.getPlug("distance"))

        info = graph._node("curveInfo", "curveInfo")
        shape.getPlug("worldSpace")[0].connectTo(info.getPlug("inputCurve"))
        info.getPlug("arcLength").connectTo(owner.getPlug("length"))

        # 送りの割合 = distance / length。長さの値は係数1の unitConversion で cm のまま数値として読む。
        numbers = []
        for label in ("distance", "length"):
            plain = graph._node("unitConversion", label + "Number")
            plain.getPlug("conversionFactor").set(1.0)
            owner.getPlug(label).connectTo(plain.getPlug("input"))
            numbers.append(plain.getPlug("output"))
        feed = graph._node("multiplyDivide", "feed")
        feed.getPlug("operation").set(2)
        numbers[0].connectTo(feed.getPlug("input1X"))
        numbers[1].connectTo(feed.getPlug("input2X"))

        up_matrix = shape.getPlug("worldMatrix")[0]
        for index in range(count):
            suffix = str(index)
            owner.addAttr(longName="fraction" + suffix, attributeType="double")
            owner.addAttr(longName="matrix" + suffix, dataType="matrix")
            outputs += ["fraction" + suffix, "matrix" + suffix]

            total = graph._node("plusMinusAverage", "offset" + suffix)
            total.getPlug("input1D")[0].set(index / float(count))
            owner.getPlug("phase").connectTo(total.getPlug("input1D")[1])
            feed.getPlug("outputX").connectTo(total.getPlug("input1D")[2])

            # frac(x): 0→0・1→1 の直線を前後に cycle で繰り返す。
            wrap = graph._node("animCurveUU", "wrap" + suffix)
            wrap.setKey(0.0, 0.0)
            wrap.setKey(1.0, 1.0)
            wrap.setInfinity(pre="cycle", post="cycle")
            total.getPlug("output1D").connectTo(wrap.getPlug("input"))
            wrap.getPlug("output").connectTo(owner.getPlug("fraction" + suffix))

            plain = graph._node("unitConversion", "fractionValue" + suffix)
            plain.getPlug("conversionFactor").set(1.0)
            owner.getPlug("fraction" + suffix).connectTo(plain.getPlug("input"))

            path = graph._node("motionPath", "path" + suffix)
            shape.getPlug("worldSpace")[0].connectTo(path.getPlug("geometryPath"))
            path.getPlug("fractionMode").set(True)
            path.getPlug("follow").set(True)
            path.getPlug("frontAxis").set(AXES[frontAxis])
            path.getPlug("upAxis").set(AXES[upAxis])
            path.getPlug("worldUpType").set(2)  # objectRotation: 曲線のtransformの回転に付いて回る
            path.getPlug("worldUpVector").set(normal)
            up_matrix.connectTo(path.getPlug("worldUpMatrix"))
            plain.getPlug("output").connectTo(path.getPlug("uValue"))

            compose = graph._node("composeMatrix", "matrix" + suffix)
            path.getPlug("allCoordinates").connectTo(compose.getPlug("inputTranslate"))
            path.getPlug("rotate").connectTo(compose.getPlug("inputRotate"))
            path.getPlug("rotateOrder").connectTo(compose.getPlug("inputRotateOrder"))
            compose.getPlug("outputMatrix").connectTo(owner.getPlug("matrix" + suffix))
        owner.setAttrFlags(outputs, keyable=False)
        return graph
