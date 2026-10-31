"""既存の補助骨の動きを、1つの値で後から増幅する(パンプアップ)標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution


class PumpUp(TwistDistribution):
    """補助骨(筋肉の膨らみなど)の生成時からの移動・スケールの変化を、``pump`` の値に応じて増やす加算の仕組み。

    既存の補助骨の階層・仕組みは変えずに、補助骨ごとの現在の行列(``matrix · offsetParentMatrix``)を読み、
    ``位置 = 現在 + (現在 - 生成時) * gain * pump + translateOffset * pump``、
    ``スケール = 現在 + (現在 - 生成時) * gain * pump + scaleOffset * pump`` 、回転は現在のままの行列を出力する。
    ``pump`` を0にすると出力は補助骨と一致する。アニメーターは ``pump`` (またはそれを駆動するコントロールの値)だけを
    キーにすればよく、増える量・形は補助骨ごとの gain・offset に定数として持たせる。
    """

    @staticmethod
    def amplify(current, rest, pump, gain=1.0, offset=(0.0, 0.0, 0.0)):
        """1つの補助骨の位置またはスケールを増幅する(DGと同じ式のPython版)。

        Args:
            current (Sequence[float]): 現在の値(XYZ)。
            rest (Sequence[float]): 生成時の値(XYZ)。
            pump (float): 増幅の度合い。
            gain (float): 生成時からの変化に掛ける割合。
            offset (Sequence[float]): pumpに比例して足す量(XYZ)。

        Returns:
            tuple[float, float, float]: ``current + (current - rest) * gain * pump + offset * pump`` 。
        """
        return tuple(c + (c - r) * gain * pump + o * pump for c, r, o in zip(current, rest, offset))

    @classmethod
    @undoTransaction("mlrig.PumpUp.create")
    def create(cls, helpers, name="pumpUp", driver=None, gains=None, translateOffsets=None, scaleOffsets=None):
        """補助骨ごとに、pump の値で増幅した行列を生成する。

        Args:
            helpers (Sequence[str | Node]): 増幅する補助骨のtransform(1個以上)。既存の仕組みで動いているもの。
            name (str): 一意なcontainer名。
            driver (str | Plug | None): ``pump`` を駆動する数値のplug(コントロールの ``translateY`` など)。
                Noneなら container の ``pump`` を直接キーにする。
            gains (Sequence[float] | None): 補助骨ごとの、生成時からの変化に掛ける割合。Noneなら全て1。
            translateOffsets (Sequence[Sequence[float]] | None): 補助骨ごとの、pump=1で足す移動量
                (補助骨の親の空間、内部の単位cm)。Noneなら全て0。
            scaleOffsets (Sequence[Sequence[float]] | None): 補助骨ごとの、pump=1で足すスケール。Noneなら全て0。

        Returns:
            PumpUp: 出力の所有者。container に pump・gain<i>・translateOffset<i>・scaleOffset<i>(keyable)、
                出力 translate<i>・scale<i>・matrix<i>(補助骨の親の空間)・worldMatrix<i> を持つ。

        Raises:
            ValueError: 補助骨・値の数や形が不正な場合、driverが数値のplugでない場合、
                またはnameが既に存在する場合。

        Note:
            入力は ``helper.matrix · helper.offsetParentMatrix`` を decomposeMatrix で分けた位置・回転(Quaternion)・
            スケールで、生成時の位置・スケールを定数として持つ。出力は composeMatrix(Quaternionの回転)で組み、
            ``worldMatrix<i> = matrix<i> · 補助骨の親のworldMatrix`` (生成時の親に接続する)。剪断は扱わない(出力では0)。
            出力は補助骨そのものへは接続しない(循環になるため)。同じ親の下の別のjointの offsetParentMatrix などへ繋ぐ。
        """
        helpers = list(helpers)
        if not helpers:
            raise ValueError("Expected at least one helper transform")
        count = len(helpers)
        gains = [1.0] * count if gains is None else [float(value) for value in gains]
        if len(gains) != count or not all(math.isfinite(value) for value in gains):
            raise ValueError("gains must have one finite value for each helper")
        offsets = {}
        for role, values in (("translateOffset", translateOffsets), ("scaleOffset", scaleOffsets)):
            values = [(0.0, 0.0, 0.0)] * count if values is None else [tuple(float(v) for v in value) for value in values]
            if len(values) != count or any(len(value) != 3 or not all(math.isfinite(v) for v in value)
                                           for value in values):
                raise ValueError(role + "s must have three finite values for each helper")
            offsets[role] = values
        if mlib.objExists(name):
            raise ValueError("PumpUp container already exists: " + name)
        helpers = [mlib.nodes.Node(helper) for helper in helpers]
        if any(not isinstance(helper, mlib.nodes.Transform) for helper in helpers):
            raise ValueError("Expected transforms for the helpers")
        if len({helper.getUuid() for helper in helpers}) != count:
            raise ValueError("The helpers must be different nodes")
        if driver is not None:
            driver = mlib.getPlug(str(driver))
            try:
                float(driver.get())
            except (TypeError, ValueError):
                raise ValueError("driver must be a numeric plug: " + str(driver))

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        owner.addAttr(longName="pump", attributeType="double", defaultValue=0.0, keyable=True)
        if driver is not None:
            driver.connectTo(owner.getPlug("pump"))
        for index in range(count):
            suffix = str(index)
            owner.addAttr(longName="gain" + suffix, attributeType="double", defaultValue=gains[index], keyable=True)
            for role in ("translateOffset", "scaleOffset", "translate", "scale"):
                owner.addAttr(longName=role + suffix, attributeType="double3")
                if role.endswith("Offset"):
                    owner.setAttrFlags([role + suffix + axis for axis in "XYZ"], keyable=True)
            for role in ("translateOffset", "scaleOffset"):
                owner.getPlug(role + suffix).set(offsets[role][index])
            for role in ("matrix", "worldMatrix"):
                owner.addAttr(longName=role + suffix, dataType="matrix")

        for index, helper in enumerate(helpers):
            suffix = str(index)
            local = graph._node("multMatrix", "helper{}Local".format(index))
            helper.getPlug("matrix").connectTo(local.getPlug("matrixIn")[0])
            helper.getPlug("offsetParentMatrix").connectTo(local.getPlug("matrixIn")[1])
            parts = graph._node("decomposeMatrix", "helper{}Parts".format(index))
            local.getPlug("matrixSum").connectTo(parts.getPlug("inputMatrix"))
            rest = Matrix(helper.getPlug("matrix").get()) * Matrix(helper.getPlug("offsetParentMatrix").get())
            restValues = {"translate": tuple(rest.translate), "scale": tuple(rest.scale)}

            # factor = gain * pump
            factor = graph._node("multiplyDivide", "helper{}Factor".format(index))
            owner.getPlug("gain" + suffix).connectTo(factor.getPlug("input1X"))
            owner.getPlug("pump").connectTo(factor.getPlug("input2X"))
            compose = graph._node("composeMatrix", "helper{}Compose".format(index))
            compose.getPlug("useEulerRotation").set(False)
            parts.getPlug("outputQuat").connectTo(compose.getPlug("inputQuat"))
            for role, source, destination in (
                ("translate", "outputTranslate", "inputTranslate"), ("scale", "outputScale", "inputScale"),
            ):
                label = "helper{}{}".format(index, role.capitalize())
                # change = 現在 - 生成時
                current = parts.getPlug(source)
                if role == "translate":
                    # 長さを単位のない値として内部の単位(cm)のまま渡す。自動の単位変換はUIの単位で倍率が変わるため使わない。
                    centimeters = graph._node("unitConversion", label + "Centimeters")
                    current.connectTo(centimeters.getPlug("input"))
                    centimeters.getPlug("conversionFactor").set(1.0)
                    current = centimeters.getPlug("output")
                change = graph._node("plusMinusAverage", label + "Change")
                change.getPlug("operation").set(2)
                current.connectTo(change.getPlug("input3D")[0])
                change.getPlug("input3D")[1].set(restValues[role])
                grown = graph._node("multiplyDivide", label + "Grown")
                change.getPlug("output3D").connectTo(grown.getPlug("input1"))
                for axis in "XYZ":
                    factor.getPlug("outputX").connectTo(grown.getPlug("input2" + axis))
                added = graph._node("multiplyDivide", label + "Added")
                owner.getPlug(role + "Offset" + suffix).connectTo(added.getPlug("input1"))
                for axis in "XYZ":
                    owner.getPlug("pump").connectTo(added.getPlug("input2" + axis))
                total = graph._node("plusMinusAverage", label + "Total")
                current.connectTo(total.getPlug("input3D")[0])
                grown.getPlug("output").connectTo(total.getPlug("input3D")[1])
                added.getPlug("output").connectTo(total.getPlug("input3D")[2])
                total.getPlug("output3D").connectTo(owner.getPlug(role + suffix))
                if role == "translate":
                    back = graph._node("unitConversion", label + "Distance")
                    owner.getPlug(role + suffix).connectTo(back.getPlug("input"))
                    back.getPlug("conversionFactor").set(1.0)
                    back.getPlug("output").connectTo(compose.getPlug(destination))
                else:
                    owner.getPlug(role + suffix).connectTo(compose.getPlug(destination))
            compose.getPlug("outputMatrix").connectTo(owner.getPlug("matrix" + suffix))
            world = graph._node("multMatrix", "helper{}World".format(index))
            owner.getPlug("matrix" + suffix).connectTo(world.getPlug("matrixIn")[0])
            # jointの parentMatrix は offsetParentMatrix を含むことがあるため、親のworldMatrixを直接使う。
            above = helper.getParent()
            if above is not None:
                above.getPlug("worldMatrix")[0].connectTo(world.getPlug("matrixIn")[1])
            world.getPlug("matrixSum").connectTo(owner.getPlug("worldMatrix" + suffix))
        # driverが長さ・角度のplugのときにMayaが挟む単位変換もcontainerに含める。
        members = {node.getUuid() for node in owner.getMembers()}
        added = [node for node in mlib.ls(type="unitConversion")
                 if node.getUuid() not in conversions and node.getUuid() not in members]
        if added:
            owner.addMembers(*added)
        return graph
