"""上腕のSwingの一部を鎖骨へ分配し、上腕の向きを保ったまま肩を動かす。"""

import math

import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.swingTwist import SwingTwist


class AutoClavicle(SwingTwist):
    """上腕の曲げ角が開始角を超えた分の一部を鎖骨の回転へ移す標準DG。

    鎖骨は上腕のSwingと同じ向きの軸まわりに回り、上腕は鎖骨が回った分だけSwingを戻す。
    そのため上腕のワールドでの向きは入力のまま、肩の位置だけが鎖骨と一緒に動く。
    """

    @classmethod
    def clavicleAngle(cls, angle, start, weight, maximum):
        """上腕の曲げ角から鎖骨へ分配する角度を計算する。

        Args:
            angle (float): 上腕の基準姿勢からの曲げ角(度)。
            start (float): 鎖骨が動き始める曲げ角(度)。
            weight (float): 開始角を超えた分のうち鎖骨へ移す割合。0〜1。
            maximum (float): 鎖骨の回転角の上限(度)。0より大きい。

        Returns:
            float: 鎖骨の回転角(度)。0以上でmaximum未満。
        """
        shared = weight * max(angle - start, 0.0)
        return maximum * (1 - math.exp(-shared / maximum))

    @classmethod
    @undoTransaction("mlrig.AutoClavicle.create")
    def create(cls, clavicle, upperarm, name="autoClavicle", axis="x", start=30.0, weight=1.0 / 3.0,
               maximum=35.0):
        """鎖骨と上腕の親空間行列を生成する。

        Args:
            clavicle (str | Node): 上腕の直接の親joint。
            upperarm (str | Node): 鎖骨の子joint。
            name (str): 一意なcontainer名。
            axis (str): 基準姿勢での上腕の長手(Twist)軸x/y/z。
            start (float): 鎖骨が動き始める上腕の曲げ角。度、0以上179以下。
            weight (float): 開始角を超えた分のうち鎖骨へ移す割合。0〜1。
            maximum (float): 鎖骨の回転角の上限。度、0より大きく90以下。

        Returns:
            AutoClavicle: clavicleMatrix・clavicleRotation・matrix・swingAngle・clavicleAngle・
            upperarmAngle・ratioの所有者。

        Raises:
            ValueError: jointの親子関係・軸・角度・weightが不正な場合。

        Note:
            基準は生成時の姿勢。θは基準の長手軸と現在の長手軸のなす角(SwingLimitと同じ)。
            鎖骨の角度 c = maximum*(1-exp(-weight*max(θ-start,0)/maximum))、比率 k = c/θ。
            上腕の基準回転U0、SwingをSとして、鎖骨の追加回転 E = U0^-1 * S^k * U0(鎖骨の空間)。
            clavicleMatrix = E * 鎖骨の現在のローカル行列、matrix = twist * S^(1-k) * U0 と上腕の現在位置。
            上腕のワールド回転は入力と一致する(twist*S^(1-k)*U0*E = twist*S*U0)。
            曲げる向きによらず同じ式で分配する。下げる・後ろへ引く動きでも鎖骨は動く。
            180度付近の曲げはSwingの向きが不定、負・非一様scaleは対象外。
        """
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be x, y or z")
        for value in (start, weight, maximum):
            if not math.isfinite(value):
                raise ValueError("start, weight and maximum must be finite")
        if not 0 <= start <= 179:
            raise ValueError("start must be between 0 and 179 degrees")
        if not 0 <= weight <= 1:
            raise ValueError("weight must be between 0 and 1")
        if not 0 < maximum <= 90:
            raise ValueError("maximum must be greater than 0 and at most 90 degrees")
        clavicle = mlib.nodes.Node(clavicle)
        upperarm = mlib.nodes.Node(upperarm)
        parent = upperarm.getParent() if upperarm.getType() == "joint" else None
        if clavicle.getType() != "joint" or parent is None or parent.getFullName() != clavicle.getFullName():
            raise ValueError("Expected a clavicle joint that is the direct parent of the upperarm joint")
        rest = Matrix(upperarm.getPlug("matrix").get()) * Matrix(upperarm.getPlug("offsetParentMatrix").get())
        rest_rotation = rest.quaternion.asMatrix()
        conversions = {node.getUuid() for node in mlib.ls(type="unitConversion")}
        base = SwingTwist.create(upperarm, name=name, axis=axis)
        graph = cls(base.container)
        owner = graph.container
        scalar = ScalarGraph(owner)
        owner.addAttr(longName="start", attributeType="double", defaultValue=start,
                      minValue=0, maxValue=179, keyable=True)
        owner.addAttr(longName="weight", attributeType="double", defaultValue=weight,
                      minValue=0, maxValue=1, keyable=True)
        owner.addAttr(longName="maximum", attributeType="double", defaultValue=maximum,
                      minValue=0.001, maxValue=90, keyable=True)
        outputs = ("swingAngle", "clavicleAngle", "upperarmAngle", "ratio")
        for attr in outputs:
            owner.addAttr(longName=attr, attributeType="double")
        for attr in ("matrix", "clavicleMatrix", "clavicleRotation"):
            owner.addAttr(longName=attr, dataType="matrix")

        # 基準の長手軸をSwingで回し、曲げ角θ(度)を求める。
        unit = [float(name_ == axis) for name_ in "xyz"]
        tip = graph._node("vectorProduct", "tipDirection")
        tip.getPlug("operation").set(3)
        tip.getPlug("normalizeOutput").set(True)
        tip.getPlug("input1").set(unit)
        owner.getPlug("swingMatrix").connectTo(tip.getPlug("matrix"))
        bend = graph._node("angleBetween", "bendAngle")
        bend.getPlug("vector1").set(unit)
        tip.getPlug("output").connectTo(bend.getPlug("vector2"))
        degrees = graph._node("unitConversion", "bendDegrees")
        bend.getPlug("angle").connectTo(degrees.getPlug("input"))
        degrees.getPlug("conversionFactor").set(180 / math.pi)
        angle = degrees.getPlug("output")
        angle.connectTo(owner.getPlug("swingAngle"))

        # 開始角を超えた分×weightを、maximumへ指数関数で漸近させる。
        excess = scalar.sum("excess", angle, owner.getPlug("start"), subtract=True)
        positive = scalar.condition("positiveExcess", excess, 0, excess, 0)
        shared = scalar.multiply("shared", positive, owner.getPlug("weight"))
        exponent = scalar.multiply("exponent", shared, owner.getPlug("maximum"), operation=2)
        decay = scalar.multiply("decay", math.exp(-1), exponent, operation=3)
        falloff = scalar.sum("falloff", 1, decay, subtract=True)
        clavicle_angle = scalar.multiply("clavicleAngleRaw", owner.getPlug("maximum"), falloff)
        clavicle_angle.connectTo(owner.getPlug("clavicleAngle"))
        scalar.sum("upperarmAngleRaw", angle, clavicle_angle, subtract=True).connectTo(
            owner.getPlug("upperarmAngle")
        )

        # 曲げ角がほぼ0なら比率を0に固定し、0除算を避ける。
        safe_angle = scalar.condition("safeAngle", angle, 1e-4, angle, 1)
        safe_clavicle = scalar.condition("safeClavicle", angle, 1e-4, clavicle_angle, 0)
        ratio = scalar.multiply("ratioRaw", safe_clavicle, safe_angle, operation=2)
        ratio.connectTo(owner.getPlug("ratio"))
        remainder = scalar.sum("remainder", 1, ratio, subtract=True)

        def partialSwing(role, weight_plug):
            """単位行列からSwingまでを、回転だけweight_plugの割合で補間する。"""
            blend = graph._node("blendMatrix", role)
            owner.getPlug("swingMatrix").connectTo(blend.getPlug("target")[0]["targetMatrix"])
            weight_plug.connectTo(blend.getPlug("target")[0]["weight"])
            # Maya 2022はbool、2025以降は連続ウェイトで成分を選択する。
            attrs = (
                ("translateWeight", "scaleWeight", "shearWeight")
                if blend.hasAttr("target[0].translateWeight")
                else ("useTranslate", "useScale", "useShear")
            )
            for attr in attrs:
                blend.getPlug("target")[0][attr].set(0)
            return blend.getPlug("outputMatrix")

        # 鎖骨の空間へ移した追加回転 E = U0^-1 * S^k * U0。
        extra = graph._node("multMatrix", "clavicleRotation")
        extra.getPlug("matrixIn")[0].set(rest_rotation.inverse())
        partialSwing("clavicleSwing", ratio).connectTo(extra.getPlug("matrixIn")[1])
        extra.getPlug("matrixIn")[2].set(rest_rotation)
        extra.getPlug("matrixSum").connectTo(owner.getPlug("clavicleRotation"))
        clavicle_out = graph._node("multMatrix", "clavicleResult")
        extra.getPlug("matrixSum").connectTo(clavicle_out.getPlug("matrixIn")[0])
        clavicle.getPlug("matrix").connectTo(clavicle_out.getPlug("matrixIn")[1])
        clavicle.getPlug("offsetParentMatrix").connectTo(clavicle_out.getPlug("matrixIn")[2])
        clavicle_out.getPlug("matrixSum").connectTo(owner.getPlug("clavicleMatrix"))

        # 行ベクトル規約: twist * S^(1-k) * 基準回転 = 鎖骨の空間での上腕の回転。
        orient = graph._node("multMatrix", "upperarmRotation")
        owner.getPlug("twistMatrix").connectTo(orient.getPlug("matrixIn")[0])
        partialSwing("upperarmSwing", remainder).connectTo(orient.getPlug("matrixIn")[1])
        orient.getPlug("matrixIn")[2].set(rest_rotation)
        relative = graph._node("multMatrix", "sourceLocal")
        upperarm.getPlug("matrix").connectTo(relative.getPlug("matrixIn")[0])
        upperarm.getPlug("offsetParentMatrix").connectTo(relative.getPlug("matrixIn")[1])
        position = graph._node("decomposeMatrix", "sourcePosition")
        relative.getPlug("matrixSum").connectTo(position.getPlug("inputMatrix"))
        rotation = graph._node("decomposeMatrix", "resultRotation")
        orient.getPlug("matrixSum").connectTo(rotation.getPlug("inputMatrix"))
        result = graph._node("composeMatrix", "result")
        result.getPlug("useEulerRotation").set(False)
        rotation.getPlug("outputQuat").connectTo(result.getPlug("inputQuat"))
        position.getPlug("outputTranslate").connectTo(result.getPlug("inputTranslate"))
        result.getPlug("outputMatrix").connectTo(owner.getPlug("matrix"))
        owner.setAttrFlags(list(outputs), keyable=False, channelBox=True)
        added = [node for node in mlib.ls(type="unitConversion") if node.getUuid() not in conversions]
        if added:
            mlib.nodes.Container(owner).addMembers(*added)
        return graph
