"""対象の位置が平面より下へ沈まないよう、平面の法線の向きへ柔らかく押し出す標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

# softnessがこれ以下なら、指数の分母を避けて硬い押し出し(max(d, 0))にする。
_HARD_SOFTNESS = 1e-4


class PlaneCollision(TwistDistribution):
    """平面からの符号付き距離 d を、softness の帯の中で指数関数的に 0 へ漸近させて押し出す標準DG。

    d >= softness なら入力のまま、d < softness なら d' = softness * exp((d - softness) / softness)。
    d' は常に正で、d = softness で値と傾きが連続する(Soft IKと同じ考え方の柔らかい上限・下限)。
    出力の行列は入力のワールド行列を、平面の法線の向きへ (d' - d) だけ平行移動したもの。回転は変えない。
    """

    @classmethod
    def response(cls, distance, softness):
        """平面からの距離に対する、押し出した後の距離を計算する。

        Args:
            distance (float): radiusを引いた平面からの符号付き距離(cm)。
            softness (float): 柔らかく押し出し始める距離(cm)。0以下なら硬い押し出し。

        Returns:
            float: 押し出した後の距離(cm)。
        """
        if softness <= _HARD_SOFTNESS:
            return max(distance, 0.0)
        if distance >= softness:
            return distance
        return softness * math.exp((distance - softness) / softness)

    @classmethod
    def _pushGraph(cls, graph, d, s):
        """距離 d と softness s から、押し出し量 response(d, s) - d を出力する標準ノードを作る。

        Args:
            graph (TwistDistribution): ノードを所有するグラフ。
            d (Plug): radiusを引いた符号付き距離(cm)。
            s (Plug): softness(cm)。

        Returns:
            Node: output1D が押し出し量の plusMinusAverage。
        """
        # 分母が0にならないよう、硬い場合だけ1へ置き換える(その場合の結果は使わない)。
        safe = graph._node("condition", "safeSoftness")
        safe.getPlug("operation").set(2)
        s.connectTo(safe.getPlug("firstTerm"))
        safe.getPlug("secondTerm").set(_HARD_SOFTNESS)
        s.connectTo(safe.getPlug("colorIfTrueR"))
        safe.getPlug("colorIfFalseR").set(1.0)
        # soft = s * e^((d - s) / s)
        excess = graph._node("plusMinusAverage", "excess")
        excess.getPlug("operation").set(2)
        d.connectTo(excess.getPlug("input1D")[0])
        s.connectTo(excess.getPlug("input1D")[1])
        exponent = graph._node("multiplyDivide", "exponent")
        exponent.getPlug("operation").set(2)
        excess.getPlug("output1D").connectTo(exponent.getPlug("input1X"))
        safe.getPlug("outColorR").connectTo(exponent.getPlug("input2X"))
        power = graph._node("multiplyDivide", "power")
        power.getPlug("operation").set(3)
        power.getPlug("input1X").set(math.e)
        exponent.getPlug("outputX").connectTo(power.getPlug("input2X"))
        soft = graph._node("multiplyDivide", "soft")
        power.getPlug("outputX").connectTo(soft.getPlug("input1X"))
        s.connectTo(soft.getPlug("input2X"))
        # 帯の外は入力のまま、硬い場合は max(d, 0)
        limited = graph._node("condition", "limited")
        limited.getPlug("operation").set(3)
        d.connectTo(limited.getPlug("firstTerm"))
        s.connectTo(limited.getPlug("secondTerm"))
        d.connectTo(limited.getPlug("colorIfTrueR"))
        soft.getPlug("outputX").connectTo(limited.getPlug("colorIfFalseR"))
        hard = graph._node("condition", "hard")
        hard.getPlug("operation").set(3)
        d.connectTo(hard.getPlug("firstTerm"))
        hard.getPlug("secondTerm").set(0.0)
        d.connectTo(hard.getPlug("colorIfTrueR"))
        hard.getPlug("colorIfFalseR").set(0.0)
        result = graph._node("condition", "result")
        result.getPlug("operation").set(2)
        s.connectTo(result.getPlug("firstTerm"))
        result.getPlug("secondTerm").set(_HARD_SOFTNESS)
        limited.getPlug("outColorR").connectTo(result.getPlug("colorIfTrueR"))
        hard.getPlug("outColorR").connectTo(result.getPlug("colorIfFalseR"))
        # push = d' - d
        push = graph._node("plusMinusAverage", "push")
        push.getPlug("operation").set(2)
        result.getPlug("outColorR").connectTo(push.getPlug("input1D")[0])
        d.connectTo(push.getPlug("input1D")[1])
        return push

    @classmethod
    @undoTransaction("mlrig.PlaneCollision.create")
    def create(cls, target, plane, name="planeCollision", axis="y", softness=1.0, radius=0.0):
        """targetのワールド位置を、planeの面より下へ沈まないよう押し出した行列を生成する。

        Args:
            target (str | Node): 押し出す対象のtransform(コントロールなど)。
            plane (str | Node): 面を表すtransform。原点を通り、ローカルのaxisを法線とする無限平面。
            name (str): 一意なcontainer名。
            axis (str): planeのローカルで法線を表す軸 x/y/z(正の向きが面の上)。
            softness (float): 柔らかく押し出し始める距離の初期値(cm、0以上)。0なら硬く止める。
            radius (float): 面から浮かせる距離の初期値(cm)。対象の半径や靴底の厚み。

        Returns:
            PlaneCollision: matrix・distance・pushの所有者。containerに softness・radius を持つ。

        Raises:
            ValueError: 軸・値が不正な場合、target・planeがtransformでない場合、同じノードの場合、
                またはnameが既に存在する場合。

        Note:
            n = planeの法線(ワールド、正規化)、o = planeの原点、p = targetの位置として
            distance = dot(p - o, n) - radius、push = response(distance, softness) - distance、
            matrix = targetのworldMatrix · T(n * push)。
            生成時に対象が面から radius + softness 以上離れていれば push = 0 で入力と一致する(跳ねない)。
            planeのscaleは法線の正規化で無視するので、距離は常にワールドのcmで測る。
        """
        axes = ("x", "y", "z")
        if axis not in axes:
            raise ValueError("axis must be x, y or z")
        softness, radius = float(softness), float(radius)
        if not (math.isfinite(softness) and math.isfinite(radius)):
            raise ValueError("softness and radius must be finite")
        if softness < 0.0:
            raise ValueError("softness must not be negative")
        if mlib.objExists(name):
            raise ValueError("PlaneCollision container already exists: " + name)
        target = mlib.nodes.Node(target)
        plane = mlib.nodes.Node(plane)
        for node in (target, plane):
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected transforms for the target and the plane")
        if target.getFullName() == plane.getFullName():
            raise ValueError("target and plane must be different nodes")

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="softness", attributeType="double", defaultValue=softness, keyable=True,
                      minValue=0)
        owner.addAttr(longName="radius", attributeType="double", defaultValue=radius, keyable=True)
        owner.addAttr(longName="distance", attributeType="double")
        owner.addAttr(longName="push", attributeType="double")
        owner.addAttr(longName="matrix", dataType="matrix")

        # 法線 n(ワールド、正規化)と原点 o
        normal = graph._node("vectorProduct", "normal")
        normal.getPlug("operation").set(3)
        normal.getPlug("normalizeOutput").set(True)
        for item in axes:
            normal.getPlug("input1" + item.upper()).set(1.0 if item == axis else 0.0)
        plane.getPlug("worldMatrix")[0].connectTo(normal.getPlug("matrix"))
        origin = graph._node("decomposeMatrix", "origin")
        plane.getPlug("worldMatrix")[0].connectTo(origin.getPlug("inputMatrix"))
        position = graph._node("decomposeMatrix", "position")
        target.getPlug("worldMatrix")[0].connectTo(position.getPlug("inputMatrix"))

        # d = dot(p - o, n) - radius
        offset = graph._node("plusMinusAverage", "offset")
        offset.getPlug("operation").set(2)
        position.getPlug("outputTranslate").connectTo(offset.getPlug("input3D")[0])
        origin.getPlug("outputTranslate").connectTo(offset.getPlug("input3D")[1])
        height = graph._node("vectorProduct", "height")
        height.getPlug("operation").set(1)
        offset.getPlug("output3D").connectTo(height.getPlug("input1"))
        normal.getPlug("output").connectTo(height.getPlug("input2"))
        distance = graph._node("plusMinusAverage", "distance")
        distance.getPlug("operation").set(2)
        height.getPlug("outputX").connectTo(distance.getPlug("input1D")[0])
        owner.getPlug("radius").connectTo(distance.getPlug("input1D")[1])
        d = distance.getPlug("output1D")
        d.connectTo(owner.getPlug("distance"))
        s = owner.getPlug("softness")

        push = cls._pushGraph(graph, d, s)
        push.getPlug("output1D").connectTo(owner.getPlug("push"))

        # matrix = targetのworldMatrix · T(n * push)
        move = graph._node("multiplyDivide", "move")
        normal.getPlug("output").connectTo(move.getPlug("input1"))
        for item in axes:
            push.getPlug("output1D").connectTo(move.getPlug("input2" + item.upper()))
        translate = graph._node("composeMatrix", "translate")
        move.getPlug("output").connectTo(translate.getPlug("inputTranslate"))
        world = graph._node("multMatrix", "world")
        target.getPlug("worldMatrix")[0].connectTo(world.getPlug("matrixIn")[0])
        translate.getPlug("outputMatrix").connectTo(world.getPlug("matrixIn")[1])
        world.getPlug("matrixSum").connectTo(owner.getPlug("matrix"))
        return graph
