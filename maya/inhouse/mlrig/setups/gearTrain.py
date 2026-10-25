"""歯数の比で、かみ合う歯車・同じ軸の歯車を駆動側の回転に連動させる標準DGを構築する。"""

import math

import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

#: 歯車のつながり方。mesh: 前の歯車とかみ合う(逆向き・歯数の比)、shaft: 前の歯車と同じ軸(同じ回転)。
LINKS = ("mesh", "shaft")


class GearTrain(TwistDistribution):
    """駆動側の歯車の回転から、続く歯車の回転を歯数の比で求める標準DG(歯車列)。

    かみ合う歯車は ``前の比 * -(前の歯数 / この歯数)`` 、同じ軸に固定した歯車は ``前の比`` で回る。
    フレームごとのPython・エクスプレッションは使わず、比も歯数のアトリビュートから求めるので、
    歯数を変えるとすぐに連動の割合が変わる。
    """

    @classmethod
    def ratios(cls, teeth, links=None):
        """駆動側に対する各歯車の回転の比を計算する(DGと同じ式のPython版)。

        Args:
            teeth (Sequence[float]): 歯数。先頭が駆動側、続きが各歯車。
            links (Sequence[str] | None): 各歯車の前とのつながり方(``LINKS``)。Noneなら全てmesh。

        Returns:
            list[float]: 各歯車(駆動側を除く)の比。回転 = 比 * 駆動側の回転。
        """
        links = ["mesh"] * (len(teeth) - 1) if links is None else list(links)
        result, ratio = [], 1.0
        for index, link in enumerate(links):
            if link == "mesh":
                ratio = -ratio * teeth[index] / teeth[index + 1]
            result.append(ratio)
        return result

    @classmethod
    @undoTransaction("mlrig.GearTrain.create")
    def create(cls, driver, gears, teeth, name="gearTrain", axis="z", links=None, connect=True):
        """駆動側の歯車の回転に連動する、各歯車の回転を生成する。

        Args:
            driver (str | Node): 駆動側の歯車のtransform。ローカルの ``rotate<axis>`` を回す。
            gears (Sequence[str | Node]): 連動させる歯車のtransform(1個以上)。前から順につながる。
            teeth (Sequence[float]): 歯数(0より大きい)。先頭が駆動側、続きが gears の順。
            name (str): 一意なcontainer名。
            axis (str): 全ての歯車のローカルの回転軸 x/y/z。
            links (Sequence[str] | None): gears の各歯車の、1つ前(先頭はdriver)とのつながり方。
                ``"mesh"`` (かみ合う)または ``"shaft"`` (同じ軸に固定)。Noneなら全てmesh。
            connect (bool): Trueなら各歯車の ``rotate<axis>`` へ出力を接続する。

        Returns:
            GearTrain: rotate<i>・ratio<i> の所有者。containerに teeth<i>・phase<i> を持つ
                (teeth0 が駆動側、gears[i] は teeth<i+1>・ratio<i+1>・rotate<i+1>・phase<i+1>)。

        Raises:
            ValueError: 軸・つながり方・歯数・歯車の数が不正な場合、transformでない・重複する場合、
                またはnameが既に存在する場合。

        Note:
            ratio0 = 1、mesh なら ratio<i> = -ratio<i-1> * teeth<i-1> / teeth<i>、shaft なら ratio<i> = ratio<i-1>。
            rotate<i> = ratio<i> * (駆動側の rotate<axis> - 生成時の値) + 生成時の歯車の rotate<axis> + phase<i>。
            生成時は駆動側の変化が0なので、接続しても歯車は跳ねない。歯のかみ合わせの見た目は
            ``phase<i>`` で合わせる。半径の比で回したい場合は、半径を歯数に入れてもよい(比は同じ)。
        """
        axes = ("x", "y", "z")
        if axis not in axes:
            raise ValueError("axis must be x, y or z")
        gears = list(gears)
        teeth = [float(value) for value in teeth]
        if not gears:
            raise ValueError("Expected at least one driven gear")
        if len(teeth) != len(gears) + 1:
            raise ValueError("teeth must have one value for the driver and one for each gear")
        if any(not math.isfinite(value) or value <= 0.0 for value in teeth):
            raise ValueError("teeth must be finite values greater than 0")
        links = ["mesh"] * len(gears) if links is None else list(links)
        if len(links) != len(gears) or any(link not in LINKS for link in links):
            raise ValueError("links must have mesh or shaft for each gear")
        if mlib.ls(name):
            raise ValueError("GearTrain container already exists: " + name)
        driver = mlib.nodes.Node(driver)
        gears = [mlib.nodes.Node(gear) for gear in gears]
        nodes = [driver] + gears
        if any(not isinstance(node, mlib.nodes.Transform) for node in nodes):
            raise ValueError("Expected transforms for the driver and the gears")
        if len({node.getFullName() for node in nodes}) != len(nodes):
            raise ValueError("The driver and the gears must be different nodes")
        channel = "rotate" + axis.upper()
        if connect:
            for gear in gears:
                if gear.getPlug(channel).getSource() is not None:
                    raise ValueError("The rotation of the gear is already connected: " + gear.getFullName())

        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        scalar = ScalarGraph(owner)
        for index, value in enumerate(teeth):
            owner.addAttr(longName="teeth" + str(index), attributeType="double", defaultValue=value,
                          minValue=1e-4, keyable=True)

        # 駆動側の変化量(角度)。animBlendNodeAdditiveDA は角度のまま A*wA + B*wB を求める。
        delta = graph._node("animBlendNodeAdditiveDA", "driverDelta")
        driver.getPlug(channel).connectTo(delta.getPlug("inputA"))
        delta.getPlug("inputB").set(driver.getPlug(channel).get())
        delta.getPlug("weightA").set(1.0)
        delta.getPlug("weightB").set(-1.0)

        ratio = 1.0
        outputs = []
        for index, (gear, link) in enumerate(zip(gears, links), 1):
            suffix = str(index)
            owner.addAttr(longName="phase" + suffix, attributeType="doubleAngle", defaultValue=0.0, keyable=True)
            owner.addAttr(longName="ratio" + suffix, attributeType="double")
            owner.addAttr(longName="rotate" + suffix, attributeType="doubleAngle")
            outputs += ["ratio" + suffix, "rotate" + suffix]
            if link == "mesh":
                quotient = scalar.multiply("quotient" + suffix, owner.getPlug("teeth" + str(index - 1)),
                                           owner.getPlug("teeth" + suffix), operation=2)
                ratio = scalar.multiply("ratioRaw" + suffix, scalar.multiply(
                    "reverse" + suffix, ratio, -1.0), quotient)
            elif index == 1:
                ratio = scalar.sum("ratioRaw" + suffix, 1.0, 0.0)
            ratio.connectTo(owner.getPlug("ratio" + suffix))
            ratio = owner.getPlug("ratio" + suffix)

            # base = 生成時の回転 + phase、rotate = delta * ratio + base
            base = graph._node("animBlendNodeAdditiveDA", "base" + suffix)
            base.getPlug("inputA").set(gear.getPlug(channel).get())
            owner.getPlug("phase" + suffix).connectTo(base.getPlug("inputB"))
            base.getPlug("weightA").set(1.0)
            base.getPlug("weightB").set(1.0)
            spin = graph._node("animBlendNodeAdditiveDA", "rotate" + suffix)
            delta.getPlug("output").connectTo(spin.getPlug("inputA"))
            ratio.connectTo(spin.getPlug("weightA"))
            base.getPlug("output").connectTo(spin.getPlug("inputB"))
            spin.getPlug("weightB").set(1.0)
            spin.getPlug("output").connectTo(owner.getPlug("rotate" + suffix))
            if connect:
                owner.getPlug("rotate" + suffix).connectTo(gear.getPlug(channel))
        owner.setAttrFlags(outputs, keyable=False, channelBox=True)
        return graph
