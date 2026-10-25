"""シザーリフト(パンタグラフ)の腕・台・滑る足の行列を、台の高さから求める標準DGを構築する。"""

import math

import mlib
from mlib.decorator import nativeUnits, undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution


class ScissorLift(TwistDistribution):
    """X字に組んだ同じ長さの腕を ``stages`` 段重ねたシザーリフトを、台の高さ1つで動かす標準DG。

    土台の空間(土台のtransformのローカル)で、固定側の支点を原点、腕が開く向きを +X、持ち上がる向きを +Y とする。
    腕の長さ ``L`` ・段数 ``n`` ・台の高さ ``H`` のとき、1段の高さ ``h = clamp(H/n, 0, L)`` 、
    滑る側の支点までの距離 ``w = sqrt(L^2 - h^2)`` 、腕の角度 ``θ = atan2(h, w)`` 。
    k段目(0始まり)の腕Aは ``(0, k*h)`` から ``(w, (k+1)*h)`` へ、腕Bは ``(0, (k+1)*h)`` から ``(w, k*h)`` へ渡り、
    2本は真ん中(腕の長さの半分)で交わる。台は ``(0, n*h)`` 、滑る足は ``(w, 0)`` と ``(w, n*h)`` に置く。
    フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def evaluate(cls, height, armLength, stages):
        """1段の高さ・滑る側の支点までの距離・腕の角度を計算する(DGと同じ式のPython版)。

        Args:
            height (float): 台の高さ。
            armLength (float): 腕の長さ(heightと同じ単位)。
            stages (int): 段数。

        Returns:
            tuple[float, float, float]: (1段の高さ, 滑る側の支点までの距離, 腕の角度(度))。
        """
        stage = min(max(height / float(stages), 0.0), armLength)
        spread = math.sqrt(max(armLength * armLength - stage * stage, 0.0))
        return stage, spread, math.degrees(math.atan2(stage, spread))

    @classmethod
    @undoTransaction("mlrig.ScissorLift.create")
    def create(cls, base=None, armLength=10.0, stages=3, height=None, name="scissorLift"):
        """シザーリフトの計算containerを作る。

        Args:
            base (str | Node | None): 土台のtransform。出力の行列はこのworldMatrixに追従する。Noneならワールド原点。
            armLength (float): 腕の長さ(cm、0より大きい)。腕の両端の支点の間の距離。
            stages (int): X字の段数(1以上)。
            height (float | None): 台の高さの初期値(cm、0以上)。Noneなら ``armLength * stages * 0.5`` (腕の角度30度)。
            name (str): 一意なcontainer名。

        Returns:
            ScissorLift: containerに height・armLength(keyable)と、stageHeight・spread・angle、
                ``arm<k>AMatrix``・``arm<k>BMatrix``(腕の固定側の端を原点、X=腕の向き、Z=土台のZ)、
                ``platformMatrix``(台)、``baseSliderMatrix``・``topSliderMatrix``(滑る足)のワールド行列を持つ。

        Raises:
            ValueError: 長さ・段数・高さが不正な場合、baseがtransformでない場合、またはnameが既に存在する場合。

        Note:
            全体を内部単位(cm・radian)で組むので、UI単位を変えても自動の unitConversion は入らない。
            高さが ``n*L`` を超えると1段の高さは ``L`` で止まり(腕は垂直)、0未満は0(腕は水平)で止まる。
        """
        if isinstance(stages, bool) or not isinstance(stages, int) or stages < 1:
            raise ValueError("stages must be an integer of 1 or more")
        if not math.isfinite(float(armLength)) or armLength <= 0.0:
            raise ValueError("armLength must be greater than 0")
        if height is None:
            height = armLength * stages * 0.5
        if not math.isfinite(float(height)) or height < 0.0:
            raise ValueError("height must be 0 or more")
        if mlib.ls(name):
            raise ValueError("ScissorLift container already exists: " + name)
        if base is not None:
            base = mlib.nodes.Node(base)
            if not isinstance(base, mlib.nodes.Transform):
                raise ValueError("base must be a transform")
        with nativeUnits():
            graph = cls(mlib.nodes.Container.create(name=name))
            graph._build(base, float(armLength), stages, float(height))
        return graph

    def _build(self, base, armLength, stages, height):
        """createの本体(内部単位の中で呼ぶ)。

        Args:
            base (Node | None): 土台のtransform。
            armLength (float): 腕の長さ(cm)。
            stages (int): 段数。
            height (float): 台の高さの初期値(cm)。
        """
        owner = self.container
        owner.addAttr(longName="height", attributeType="doubleLinear", defaultValue=height, minValue=0.0,
                      keyable=True)
        owner.addAttr(longName="armLength", attributeType="doubleLinear", defaultValue=armLength, minValue=1e-6,
                      keyable=True)
        for attribute in ("stageHeight", "spread"):
            owner.addAttr(longName=attribute, attributeType="doubleLinear")
        owner.addAttr(longName="angle", attributeType="doubleAngle")
        matrices = []
        for index in range(stages):
            matrices += ["arm%dAMatrix" % index, "arm%dBMatrix" % index]
        matrices += ["platformMatrix", "baseSliderMatrix", "topSliderMatrix"]
        for attribute in matrices:
            owner.addAttr(longName=attribute, dataType="matrix")

        # h = clamp(H/n, 0, L)
        divide = self._node("multiplyDivide", "stageDivide")
        divide.getPlug("operation").set(2)
        owner.getPlug("height").connectTo(divide.getPlug("input1X"))
        divide.getPlug("input2X").set(float(stages))
        limit = self._node("clamp", "stageLimit")
        divide.getPlug("outputX").connectTo(limit.getPlug("inputR"))
        owner.getPlug("armLength").connectTo(limit.getPlug("maxR"))
        stage = limit.getPlug("outputR")
        stage.connectTo(owner.getPlug("stageHeight"))

        # w = sqrt(max(L^2 - h^2, 0))
        squares = self._node("multiplyDivide", "squares")
        squares.getPlug("operation").set(3)
        owner.getPlug("armLength").connectTo(squares.getPlug("input1X"))
        stage.connectTo(squares.getPlug("input1Y"))
        squares.getPlug("input2").set((2.0, 2.0, 1.0))
        rest = self._node("plusMinusAverage", "spreadSquared")
        rest.getPlug("operation").set(2)
        squares.getPlug("outputX").connectTo(rest.getPlug("input1D")[0])
        squares.getPlug("outputY").connectTo(rest.getPlug("input1D")[1])
        floor = self._node("clamp", "spreadFloor")
        floor.getPlug("maxR").set(1e30)
        rest.getPlug("output1D").connectTo(floor.getPlug("inputR"))
        root = self._node("multiplyDivide", "spreadRoot")
        root.getPlug("operation").set(3)
        floor.getPlug("outputR").connectTo(root.getPlug("input1X"))
        root.getPlug("input2X").set(0.5)
        spread = root.getPlug("outputX")
        spread.connectTo(owner.getPlug("spread"))

        # θ = atan2(h, w)(angleBetween の符号付きeuler)。腕Bは -θ。
        angle = self._node("angleBetween", "armAngle")
        angle.getPlug("vector1").set((1.0, 0.0, 0.0))
        spread.connectTo(angle.getPlug("vector2X"))
        stage.connectTo(angle.getPlug("vector2Y"))
        angle.getPlug("vector2Z").set(0.0)
        angle.getPlug("eulerZ").connectTo(owner.getPlug("angle"))
        negative = self._node("animBlendNodeAdditiveDA", "armAngleNegative")
        angle.getPlug("eulerZ").connectTo(negative.getPlug("inputA"))
        negative.getPlug("weightA").set(-1.0)
        negative.getPlug("weightB").set(0.0)

        def place(role, level, rotation=None, slide=False):
            # T(slide ? w : 0, level*h, 0)・R_z(rotation)・土台のworldMatrix を出力へ。
            local = self._node("composeMatrix", role + "Local")
            if level:
                height_plug = stage
                if level != 1:
                    times = self._node("multiplyDivide", role + "Height")
                    stage.connectTo(times.getPlug("input1X"))
                    times.getPlug("input2X").set(float(level))
                    height_plug = times.getPlug("outputX")
                height_plug.connectTo(local.getPlug("inputTranslateY"))
            if slide:
                spread.connectTo(local.getPlug("inputTranslateX"))
            if rotation is not None:
                rotation.connectTo(local.getPlug("inputRotateZ"))
            target = owner.getPlug(role + "Matrix")
            if base is None:
                local.getPlug("outputMatrix").connectTo(target)
                return
            world = self._node("multMatrix", role + "World")
            local.getPlug("outputMatrix").connectTo(world.getPlug("matrixIn")[0])
            base.getPlug("worldMatrix")[0].connectTo(world.getPlug("matrixIn")[1])
            world.getPlug("matrixSum").connectTo(target)

        for index in range(stages):
            place("arm%dA" % index, index, angle.getPlug("eulerZ"))
            place("arm%dB" % index, index + 1, negative.getPlug("output"))
        place("platform", stages)
        place("baseSlider", 0, slide=True)
        place("topSlider", stages, slide=True)
        owner.setAttrFlags(["stageHeight", "spread", "angle"] + matrices, keyable=False)

    def getStages(self):
        """段数を返す。

        Returns:
            int: containerにある腕の行列の段数。
        """
        count = 0
        while self.container.hasAttr("arm%dAMatrix" % count):
            count += 1
        return count
