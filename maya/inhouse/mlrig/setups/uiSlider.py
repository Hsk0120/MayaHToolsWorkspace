"""枠の中だけを動くスライダーのコントロール(フェイシャルのUIなど)から、方向ごとの0〜1の値を出す標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

#: 出力のアトリビュート名(container)。x・yは正規化した位置、ほかは0〜1の重み。
OUTPUTS = ("x", "y", "right", "left", "up", "down", "upRight", "upLeft", "downRight", "downLeft")


class UiSlider(TwistDistribution):
    """コントロールの移動を枠(``size`` の正方形)の中に制限し、正規化した位置と方向ごとの重みを出力する仕組み。

    生成時のコントロールの位置を中心とし、``x = (translateX - 生成時) / size`` 、``y`` も同様に求め、
    ``rangeX`` ・ ``rangeY`` の範囲へclampする。方向の重みは ``right = clamp(x, 0, 1)`` 、
    ``left = clamp(-x, 0, 1)`` 、``up`` ・ ``down`` も同様で、角の重みは ``upRight = up * right`` のような積
    (双一次補間の角の重み)にする。コントロール自体の移動は Maya の transformLimits(``minTransXLimit`` 等)で
    同じ範囲に止める。出力は数値だけで、補正シェイプやドリブンキーの入力に繋ぐ。
    """

    @staticmethod
    def weights(x, y):
        """正規化した位置から方向ごとの重みを求める(DGと同じ式のPython版)。

        Args:
            x (float): 正規化した横の位置(-1〜1)。
            y (float): 正規化した縦の位置(-1〜1)。

        Returns:
            dict[str, float]: :data:`OUTPUTS` の名前と値。
        """
        right, left = min(max(x, 0.0), 1.0), min(max(-x, 0.0), 1.0)
        up, down = min(max(y, 0.0), 1.0), min(max(-y, 0.0), 1.0)
        return {"x": x, "y": y, "right": right, "left": left, "up": up, "down": down,
                "upRight": up * right, "upLeft": up * left, "downRight": down * right, "downLeft": down * left}

    @classmethod
    @undoTransaction("mlrig.UiSlider.create")
    def create(cls, control, name="uiSlider", size=1.0, rangeX=(-1.0, 1.0), rangeY=(-1.0, 1.0),
               limit=True, lockChannels=True):
        """スライダーのコントロールから方向ごとの重みを出すDGを生成する。

        Args:
            control (str | Transform): スライダーとして動かすtransform。生成時の位置を中心(0, 0)とする。
            name (str): 一意なcontainer名。
            size (float): 正規化の1に当たる移動量(内部の単位cm、0より大きい)。
            rangeX (Sequence[float]): 横の範囲 ``(min, max)`` 。minは-1〜0、maxは0〜1。 ``(0, 0)`` で横に動かさない。
            rangeY (Sequence[float]): 縦の範囲。rangeXと同じ形。
            limit (bool): Trueならコントロールの移動を transformLimits で範囲内に止める(Zは生成時の位置に固定)。
            lockChannels (bool): Trueならコントロールの使わないチャンネル(translateZ・回転・スケール、
                範囲が0の軸)をkeyableから外す。

        Returns:
            UiSlider: 出力の所有者。container に size・rangeX・rangeY(読み取り用の定数)と、
                出力 x・y・right・left・up・down・upRight・upLeft・downRight・downLeft を持つ。

        Raises:
            ValueError: controlがtransformでない場合、sizeや範囲が不正な場合、またはnameが既に存在する場合。

        Note:
            移動量はコントロールの親の空間の ``translate`` で読み、係数1の unitConversion で内部の単位(cm)のまま
            扱う(UIの単位がmmでも正規化の値は変わらない)。transformLimits を切っても出力は範囲へclampする。
        """
        size = float(size)
        if not math.isfinite(size) or size <= 0.0:
            raise ValueError("size must be a positive finite value")
        ranges = []
        for label, values in (("rangeX", rangeX), ("rangeY", rangeY)):
            values = tuple(float(value) for value in values)
            if (len(values) != 2 or not all(math.isfinite(value) for value in values)
                    or not -1.0 <= values[0] <= 0.0 <= values[1] <= 1.0):
                raise ValueError(label + " must be (min, max) with -1 <= min <= 0 <= max <= 1")
            ranges.append(values)
        if ranges[0] == (0.0, 0.0) and ranges[1] == (0.0, 0.0):
            raise ValueError("At least one of rangeX and rangeY must allow movement")
        if mlib.ls(name):
            raise ValueError("UiSlider container already exists: " + name)
        control = mlib.nodes.Node(control)
        if not isinstance(control, mlib.nodes.Transform):
            raise ValueError("Expected a transform for the control: " + str(control))
        rest = tuple(control.getPlug("translate").get())

        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        owner.addAttr(longName="size", attributeType="double", defaultValue=size)
        for label, values in zip(("rangeX", "rangeY"), ranges):
            owner.addAttr(longName=label, attributeType="double2")
            owner.getPlug(label).set(values)
        for attribute in OUTPUTS:
            owner.addAttr(longName=attribute, attributeType="double")

        # offset = (translate - 生成時) を内部の単位(cm)のまま求める。
        offset = graph._node("plusMinusAverage", "offset")
        offset.getPlug("operation").set(2)
        for axis in "XY":
            centimeters = graph._node("unitConversion", "translate" + axis)
            control.getPlug("translate" + axis).connectTo(centimeters.getPlug("input"))
            centimeters.getPlug("conversionFactor").set(1.0)
            centimeters.getPlug("output").connectTo(mlib.getPlug("{}.input3D[0].input3D{}".format(offset, axis.lower())))
        offset.getPlug("input3D")[1].set((rest[0], rest[1], 0.0))
        # position = clamp(offset / size, range)
        scaled = graph._node("multiplyDivide", "normalize")
        scaled.getPlug("operation").set(2)
        offset.getPlug("output3D").connectTo(scaled.getPlug("input1"))
        for axis in "XYZ":
            owner.getPlug("size").connectTo(scaled.getPlug("input2" + axis))
        position = graph._node("clamp", "position")
        scaled.getPlug("output").connectTo(position.getPlug("input"))
        position.getPlug("min").set((ranges[0][0], ranges[1][0], 0.0))
        position.getPlug("max").set((ranges[0][1], ranges[1][1], 0.0))
        position.getPlug("outputR").connectTo(owner.getPlug("x"))
        position.getPlug("outputG").connectTo(owner.getPlug("y"))

        # 方向の重み: 正の向きはそのまま、負の向きは符号を反転してから 0〜1 へclampする。
        negative = graph._node("multiplyDivide", "negative")
        position.getPlug("output").connectTo(negative.getPlug("input1"))
        negative.getPlug("input2").set((-1.0, -1.0, -1.0))
        sides = graph._node("clamp", "sides")
        position.getPlug("outputR").connectTo(sides.getPlug("inputR"))
        negative.getPlug("outputX").connectTo(sides.getPlug("inputG"))
        position.getPlug("outputG").connectTo(sides.getPlug("inputB"))
        sides.getPlug("max").set((1.0, 1.0, 1.0))
        bottom = graph._node("clamp", "bottom")
        negative.getPlug("outputY").connectTo(bottom.getPlug("inputR"))
        bottom.getPlug("max").set((1.0, 1.0, 1.0))
        directions = {"right": sides.getPlug("outputR"), "left": sides.getPlug("outputG"),
                      "up": sides.getPlug("outputB"), "down": bottom.getPlug("outputR")}
        for attribute, plug in directions.items():
            plug.connectTo(owner.getPlug(attribute))

        # 角の重み = 縦の重み * 横の重み
        for vertical in ("up", "down"):
            corner = graph._node("multiplyDivide", vertical + "Corners")
            for axis, horizontal in zip("XY", ("Right", "Left")):
                owner.getPlug(vertical).connectTo(corner.getPlug("input1" + axis))
                owner.getPlug(horizontal.lower()).connectTo(corner.getPlug("input2" + axis))
                corner.getPlug("output" + axis).connectTo(owner.getPlug(vertical + horizontal))

        if limit:
            for axis, (low, high), center in zip("XYZ", ranges + [(0.0, 0.0)], rest):
                control.getPlug("minTrans" + axis + "Limit").set(center + low * size)
                control.getPlug("maxTrans" + axis + "Limit").set(center + high * size)
                control.getPlug("minTrans" + axis + "LimitEnable").set(True)
                control.getPlug("maxTrans" + axis + "LimitEnable").set(True)
        if lockChannels:
            unused = ["translateZ"] + [role + axis for role in ("rotate", "scale") for axis in "XYZ"]
            unused += ["translate" + axis for axis, values in zip("XY", ranges) if values == (0.0, 0.0)]
            for attribute in unused:
                control.getPlug(attribute).setKeyable(False)
        return graph
