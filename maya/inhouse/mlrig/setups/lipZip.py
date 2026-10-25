"""上唇と下唇の点を、口角から順に閉じ合わせる(リップジップ)標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution


class LipZip(TwistDistribution):
    """上唇・下唇の対になった点を、左右の口角から中央へ向かって順に閉じ合わせる標準DG。

    唇の点は口角から口角へ並べ、i番目の上唇の点と下唇の点を1組とする。
    各組には唇に沿う位置 position(0=右の口角、1=左の口角)があり、zipLeft・zipRight(0〜1)を上げると
    口角に近い組から閉じていく。閉じる途中の組は falloff の幅でなめらかに移る。
    閉じた組の上唇・下唇は、2点の間の meetHeight の位置(0=下唇、1=上唇)で合わさる。
    """

    @classmethod
    def response(cls, position, zipLeft, zipRight, falloff):
        """唇に沿う位置と左右のジップの量から、その組が閉じる割合を計算する。

        Args:
            position (float): 唇に沿う位置(0=右の口角、1=左の口角)。
            zipLeft (float): 左の口角から閉じる量(0〜1)。
            zipRight (float): 右の口角から閉じる量(0〜1)。
            falloff (float): 閉じる途中の幅(0より大きい)。

        Returns:
            float: 0〜1の割合。片側ごとに
            t = clamp((d - (1 - zip*(1+falloff))) / falloff, 0, 1) の t*t*(3-2t) を求め、
            左右の和を0〜1に制限する。dは左なら position、右なら 1-position。
        """

        def side(distance, amount):
            low = 1.0 - amount * (1.0 + falloff)
            t = min(max((distance - low) / falloff, 0.0), 1.0)
            return t * t * (3.0 - 2.0 * t)

        return min(side(position, zipLeft) + side(1.0 - position, zipRight), 1.0)

    @classmethod
    @undoTransaction("mlrig.LipZip.create")
    def create(cls, upper, lower, name="lipZip", positions=None, zipLeft=0.0, zipRight=0.0,
               falloff=0.3, meetHeight=0.5):
        """上唇・下唇の点のワールド行列から、閉じ合わせた行列を生成する。

        Args:
            upper (Sequence[str | Node]): 上唇の点のtransform。右の口角側から左の口角側へ並べる。
            lower (Sequence[str | Node]): 下唇の点のtransform。upperと同じ数・同じ順。
            name (str): 一意なcontainer名。
            positions (Sequence[float] | None): 各組の唇に沿う位置(0〜1、右の口角が0)。
                Noneなら (i+1)/(n+1) の等間隔(口角そのものは含まない)。
            zipLeft (float): 左の口角から閉じる量の初期値(0〜1)。
            zipRight (float): 右の口角から閉じる量の初期値(0〜1)。
            falloff (float): 閉じる途中の幅(0.01〜1)。小さいほど1組ずつはっきり閉じる。
            meetHeight (float): 閉じたときに合わさる高さ(0=下唇の位置、1=上唇の位置)。

        Returns:
            LipZip: upperMatrix<i>・lowerMatrix<i>・weight<i> の所有者。

        Raises:
            ValueError: 点が空、上下の数が違う、transformでない、値が範囲外、
                またはnameが既に存在する場合。

        Note:
            weight<i> = response(position<i>, zipLeft, zipRight, falloff)。
            meet<i> = blend(lower<i>, upper<i>, meetHeight)(blendMatrixで位置は線形、回転はslerp)。
            upperMatrix<i> = blend(upper<i>, meet<i>, weight<i>)、lowerMatrix<i> = blend(lower<i>, meet<i>, weight<i>)。
            出力はワールド行列。zipLeft・zipRightが0なら入力の点のワールド行列と同じなので、作成時に跳ねない。
            zipLeft・zipRight・falloff・meetHeight・position<i> は作成後も変更できる(keyable)。
        """
        upper, lower = list(upper), list(lower)
        if not upper:
            raise ValueError("Expected at least one upper and lower lip point")
        if len(upper) != len(lower):
            raise ValueError("Expected the same number of upper and lower lip points")
        count = len(upper)
        if positions is None:
            positions = [(index + 1.0) / (count + 1.0) for index in range(count)]
        positions = [float(value) for value in positions]
        if len(positions) != count:
            raise ValueError("Expected one position per lip point pair")
        values = [float(value) for value in (zipLeft, zipRight, falloff, meetHeight)]
        if not all(math.isfinite(value) for value in values + positions):
            raise ValueError("positions, zip, falloff and meetHeight must be finite")
        zipLeft, zipRight, falloff, meetHeight = values
        if not all(0.0 <= value <= 1.0 for value in positions + [zipLeft, zipRight, meetHeight]):
            raise ValueError("positions, zipLeft, zipRight and meetHeight must be between 0 and 1")
        if not 0.01 <= falloff <= 1.0:
            raise ValueError("falloff must be between 0.01 and 1")
        if mlib.ls(name):
            raise ValueError("LipZip container already exists: " + name)
        upper = [mlib.nodes.Node(node) for node in upper]
        lower = [mlib.nodes.Node(node) for node in lower]
        if any(not isinstance(node, mlib.nodes.Transform) for node in upper + lower):
            raise ValueError("Expected transforms for the lip points")

        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        for attr, value, bounds in (
            ("zipLeft", zipLeft, {"minValue": 0, "maxValue": 1}),
            ("zipRight", zipRight, {"minValue": 0, "maxValue": 1}),
            ("falloff", falloff, {"minValue": 0.01, "maxValue": 1}),
            ("meetHeight", meetHeight, {"minValue": 0, "maxValue": 1}),
        ):
            owner.addAttr(longName=attr, attributeType="double", defaultValue=value, keyable=True, **bounds)
        weights = []
        for index in range(count):
            owner.addAttr(longName="position" + str(index), attributeType="double",
                          defaultValue=positions[index], keyable=True, minValue=0, maxValue=1)
            owner.addAttr(longName="weight" + str(index), attributeType="double")
            weights.append("weight" + str(index))
            for attr in ("upperMatrix", "lowerMatrix"):
                owner.addAttr(longName=attr + str(index), dataType="matrix")

        # 左右で共通の閉じる前線: low = 1 - zip*(1+falloff)、high = low + falloff(Xが左、Yが右)。
        widened = graph._node("plusMinusAverage", "widened")
        owner.getPlug("falloff").connectTo(widened.getPlug("input1D")[0])
        widened.getPlug("input1D")[1].set(1)
        front = graph._node("multiplyDivide", "front")
        owner.getPlug("zipLeft").connectTo(front.getPlug("input1X"))
        owner.getPlug("zipRight").connectTo(front.getPlug("input1Y"))
        widened.getPlug("output1D").connectTo(front.getPlug("input2X"))
        widened.getPlug("output1D").connectTo(front.getPlug("input2Y"))
        low = graph._node("plusMinusAverage", "low")
        low.getPlug("operation").set(2)
        low.getPlug("input2D")[0].set([1, 1])
        front.getPlug("outputX").connectTo(low.getPlug("input2D")[1]["input2Dx"])
        front.getPlug("outputY").connectTo(low.getPlug("input2D")[1]["input2Dy"])
        high = graph._node("plusMinusAverage", "high")
        low.getPlug("output2D").connectTo(high.getPlug("input2D")[0])
        owner.getPlug("falloff").connectTo(high.getPlug("input2D")[1]["input2Dx"])
        owner.getPlug("falloff").connectTo(high.getPlug("input2D")[1]["input2Dy"])

        for index in range(count):
            prefix = "pair" + str(index) + "_"
            position = owner.getPlug("position" + str(index))
            # 左の口角からの距離はposition、右の口角からは1-position。
            mirrored = graph._node("reverse", prefix + "mirrored")
            position.connectTo(mirrored.getPlug("inputX"))
            # t = clamp((d - low) / falloff, 0, 1)
            ranged = graph._node("setRange", prefix + "range")
            position.connectTo(ranged.getPlug("valueX"))
            mirrored.getPlug("outputX").connectTo(ranged.getPlug("valueY"))
            for channel, component in (("output2Dx", "X"), ("output2Dy", "Y")):
                low.getPlug(channel).connectTo(ranged.getPlug("oldMin" + component))
                high.getPlug(channel).connectTo(ranged.getPlug("oldMax" + component))
                ranged.getPlug("max" + component).set(1)
            clamped = graph._node("clamp", prefix + "rangeClamp")
            ranged.getPlug("outValueX").connectTo(clamped.getPlug("inputR"))
            ranged.getPlug("outValueY").connectTo(clamped.getPlug("inputG"))
            clamped.getPlug("maxR").set(1)
            clamped.getPlug("maxG").set(1)
            # smoothstep t*t*(3-2t) を左右の2チャンネルで同時に求める。
            squared = graph._node("multiplyDivide", prefix + "squared")
            doubled = graph._node("multiplyDivide", prefix + "doubled")
            for source, component in (("outputR", "X"), ("outputG", "Y")):
                clamped.getPlug(source).connectTo(squared.getPlug("input1" + component))
                clamped.getPlug(source).connectTo(squared.getPlug("input2" + component))
                clamped.getPlug(source).connectTo(doubled.getPlug("input1" + component))
                doubled.getPlug("input2" + component).set(-2)
            falling = graph._node("plusMinusAverage", prefix + "falling")
            doubled.getPlug("output").connectTo(falling.getPlug("input3D")[0])
            falling.getPlug("input3D")[1].set([3, 3, 0])
            smooth = graph._node("multiplyDivide", prefix + "smooth")
            squared.getPlug("output").connectTo(smooth.getPlug("input1"))
            falling.getPlug("output3D").connectTo(smooth.getPlug("input2"))
            # 左右の和を0〜1に制限したものがその組の割合。
            total = graph._node("plusMinusAverage", prefix + "total")
            smooth.getPlug("outputX").connectTo(total.getPlug("input1D")[0])
            smooth.getPlug("outputY").connectTo(total.getPlug("input1D")[1])
            limited = graph._node("clamp", prefix + "weight")
            total.getPlug("output1D").connectTo(limited.getPlug("inputR"))
            limited.getPlug("maxR").set(1)
            limited.getPlug("outputR").connectTo(owner.getPlug("weight" + str(index)))

            # 合わさる行列: 下唇から上唇へ meetHeight の割合。
            meet = graph._node("blendMatrix", prefix + "meet")
            lower[index].getPlug("worldMatrix")[0].connectTo(meet.getPlug("inputMatrix"))
            upper[index].getPlug("worldMatrix")[0].connectTo(meet.getPlug("target")[0]["targetMatrix"])
            owner.getPlug("meetHeight").connectTo(meet.getPlug("target")[0]["weight"])
            for source, attr in ((upper[index], "upperMatrix"), (lower[index], "lowerMatrix")):
                blend = graph._node("blendMatrix", prefix + attr)
                source.getPlug("worldMatrix")[0].connectTo(blend.getPlug("inputMatrix"))
                meet.getPlug("outputMatrix").connectTo(blend.getPlug("target")[0]["targetMatrix"])
                owner.getPlug("weight" + str(index)).connectTo(blend.getPlug("target")[0]["weight"])
                blend.getPlug("outputMatrix").connectTo(owner.getPlug(attr + str(index)))
        owner.setAttrFlags(weights, keyable=False, channelBox=True)
        return graph
