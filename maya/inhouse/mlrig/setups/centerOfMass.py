"""体節の質量の割合から全身の重心(COM)と、その床への投影・支えの中心からのずれを求める標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction

from mlrig.setups.twistDistribution import TwistDistribution

#: 質量の合計を割るときの下限(0除算を避ける)。
_EPSILON = 1e-6


class CenterOfMass(TwistDistribution):
    """体節ごとの重心の点を質量で重み付けして平均し、全身の重心のワールド行列を出力する。

    体節 i の重心の点は、根元 ``s_i`` と先 ``e_i`` のワールド位置の内分点
    ``p_i = (1 - r_i) s_i + r_i e_i`` (``r_i`` は ``ratio<i>``、先が無い体節は ``p_i = s_i``)。
    全身の重心は ``c = Σ m_i p_i / Σ m_i`` (``m_i`` は ``mass<i>``、相対値でよい)。
    ``wtAddMatrix`` で各ノードの worldMatrix を重み ``m_i (1 - r_i) / M``・``m_i r_i / M`` で足すと、
    行列の位置の行は重みの線形和なので、和の位置がそのまま ``c`` になる(回転・スケールの部分は使わない)。
    ``M`` は ``plusMinusAverage`` で足した質量の合計で、 ``clamp`` で下限を設けて0除算を避ける。

    出力(containerのアトリビュート):
        - ``centerMatrix``: 位置が ``c`` で向きが単位のワールド行列。
        - ``groundMatrix``: ``c`` をワールドの上方向(Y)へ沿って ``groundHeight`` の床へ落とした点。
        - ``totalMass``: 質量の合計。
        - 支え(足など)を渡した場合: ``supportMatrix`` (支えの点の平均を床へ落とした点)と
          ``balance`` (床の上での重心と支えの中心の距離)。

    時刻・前の結果を使わないので、どのフレームでも同じ姿勢から同じ値になる。
    """

    #: 一般的な人体の体節パラメーター(体重に対する質量の割合, 根元から先へ向けた重心の位置の割合)。
    #: 生体力学の教科書で広く使われる Dempster の値(Winter「Biomechanics and Motor Control of Human
    #: Movement」の体節の表)。headNeck は首の根元から頭頂の手前の耳の位置まで、trunk は股関節から肩まで。
    DEMPSTER = {
        "headNeck": (0.081, 1.0),
        "trunk": (0.497, 0.5),
        "upperArm": (0.028, 0.436),
        "forearm": (0.016, 0.430),
        "hand": (0.006, 0.506),
        "thigh": (0.100, 0.433),
        "shank": (0.0465, 0.433),
        "foot": (0.0145, 0.5),
    }

    @classmethod
    @undoTransaction("mlrig.CenterOfMass.create")
    def create(cls, segments, name="centerOfMass", support=None, groundHeight=0.0):
        """全身の重心を出力するcontainerを作る。

        Args:
            segments (list[dict]): 体節ごとの辞書。 ``start`` (根元のtransform、必須)、 ``end`` (先のtransform、
                省略時は根元の点だけを使う)、 ``mass`` (質量、0以上の相対値、既定1)、 ``ratio`` (根元から先への
                重心の位置の割合、0〜1、既定0.5、 ``end`` が無いときは使わない)。
            name (str): 一意なcontainer名。
            support (list[str | Node] | None): 床で体を支える点のtransform(足首・つま先など)。渡すと
                ``supportMatrix`` と ``balance`` を作る。
            groundHeight (float): 床のワールドY座標。containerの ``groundHeight`` (keyable)の初期値。

        Returns:
            CenterOfMass: mass<i>・ratio<i>・groundHeight(keyable)と、centerMatrix・groundMatrix・totalMass
            (と supportMatrix・balance)の所有者。

        Raises:
            ValueError: 引数が不正な場合、またはnameが既に存在する場合。

        Note:
            床はワールドのY軸に垂直な平面とする。重心は体節の点の平均なので、各体節の形・慣性は扱わない。
        """
        if not segments:
            raise ValueError("segments must have one or more items")
        parsed = []
        for item in segments:
            if not isinstance(item, dict) or "start" not in item:
                raise ValueError("Each segment must be a dict with 'start'")
            unknown = set(item) - {"start", "end", "mass", "ratio"}
            if unknown:
                raise ValueError("Unknown segment keys: " + ", ".join(sorted(unknown)))
            start = cls._transformNode(item["start"])
            end = None if item.get("end") is None else cls._transformNode(item["end"])
            mass = float(item.get("mass", 1.0))
            ratio = float(item.get("ratio", 0.5))
            if not math.isfinite(mass) or mass < 0.0:
                raise ValueError("mass must be zero or more: " + str(item.get("mass")))
            if not math.isfinite(ratio) or not 0.0 <= ratio <= 1.0:
                raise ValueError("ratio must be from 0 to 1: " + str(item.get("ratio")))
            if end is not None and end.getUuid() == start.getUuid():
                raise ValueError("start and end must be different transforms")
            parsed.append((start, end, mass, ratio))
        if sum(mass for _, _, mass, _ in parsed) <= 0.0:
            raise ValueError("The total mass must be more than zero")
        supports = [cls._transformNode(item) for item in (support or [])]
        groundHeight = float(groundHeight)
        if not math.isfinite(groundHeight):
            raise ValueError("groundHeight must be finite")
        if mlib.ls(name):
            raise ValueError("CenterOfMass container already exists: " + name)
        graph = cls(mlib.nodes.Container.create(name=name))
        graph._build(parsed, supports, groundHeight)
        return graph

    @staticmethod
    def _transformNode(item):
        """入力を既存のtransformへ解決する。

        Args:
            item (str | Node): ノードまたは名前。

        Returns:
            Transform: 解決したノード。

        Raises:
            ValueError: 既存のtransformでない場合。
        """
        node = item if isinstance(item, mlib.nodes.Node) else (mlib.getNode(str(item)) if mlib.ls(str(item)) else None)
        if not isinstance(node, mlib.nodes.Transform):
            raise ValueError("Expected an existing transform: " + str(item))
        return node

    def _build(self, segments, supports, groundHeight):
        """createの本体。

        Args:
            segments (list[tuple]): (start, end, mass, ratio) の列。
            supports (list[Transform]): 支えの点。
            groundHeight (float): 床の高さ。
        """
        owner = self.container
        owner.addAttr(longName="groundHeight", attributeType="double", defaultValue=groundHeight, keyable=True)
        owner.addAttr(longName="totalMass", attributeType="double")
        for attr in ("centerMatrix", "groundMatrix"):
            owner.addAttr(longName=attr, dataType="matrix")

        total = self._node("plusMinusAverage", "totalMass")
        safe = self._node("clamp", "safeTotal")
        safe.getPlug("minR").set(_EPSILON)
        safe.getPlug("maxR").set(1e30)
        total.getPlug("output1D").connectTo(safe.getPlug("inputR"))
        total.getPlug("output1D").connectTo(owner.getPlug("totalMass"))
        center = self._node("wtAddMatrix", "center")
        slot = 0
        for index, (start, end, mass, ratio) in enumerate(segments):
            owner.addAttr(longName="mass" + str(index), attributeType="double", defaultValue=mass,
                          minValue=0.0, keyable=True)
            owner.getPlug("mass" + str(index)).connectTo(total.getPlug("input1D")[index])
            # 重み: X = m (1 - r) / M (根元)、Y = m r / M (先)。
            share = self._node("multiplyDivide", "share" + str(index))
            weight = self._node("multiplyDivide", "weight" + str(index))
            weight.getPlug("operation").set(2)
            for axis in "XY":
                owner.getPlug("mass" + str(index)).connectTo(share.getPlug("input1" + axis))
                share.getPlug("output" + axis).connectTo(weight.getPlug("input1" + axis))
                safe.getPlug("outputR").connectTo(weight.getPlug("input2" + axis))
            if end is None:
                share.getPlug("input2X").set(1.0)
                share.getPlug("input2Y").set(0.0)
            else:
                owner.addAttr(longName="ratio" + str(index), attributeType="double", defaultValue=ratio,
                              minValue=0.0, maxValue=1.0, keyable=True)
                reverse = self._node("reverse", "rest" + str(index))
                owner.getPlug("ratio" + str(index)).connectTo(reverse.getPlug("inputX"))
                reverse.getPlug("outputX").connectTo(share.getPlug("input2X"))
                owner.getPlug("ratio" + str(index)).connectTo(share.getPlug("input2Y"))
            for node, axis in ((start, "X"), (end, "Y")):
                if node is None:
                    continue
                entry = center.getPlug("wtMatrix")[slot]
                node.getPlug("worldMatrix")[0].connectTo(entry["matrixIn"])
                weight.getPlug("output" + axis).connectTo(entry["weightIn"])
                slot += 1

        position = self._node("decomposeMatrix", "centerPosition")
        center.getPlug("matrixSum").connectTo(position.getPlug("inputMatrix"))
        centerMatrix = self._node("composeMatrix", "centerMatrix")
        position.getPlug("outputTranslate").connectTo(centerMatrix.getPlug("inputTranslate"))
        centerMatrix.getPlug("outputMatrix").connectTo(owner.getPlug("centerMatrix"))
        groundMatrix = self._groundMatrix("ground", position)
        groundMatrix.connectTo(owner.getPlug("groundMatrix"))

        if supports:
            owner.addAttr(longName="supportMatrix", dataType="matrix")
            owner.addAttr(longName="balance", attributeType="double")
            average = self._node("wtAddMatrix", "support")
            for index, node in enumerate(supports):
                entry = average.getPlug("wtMatrix")[index]
                node.getPlug("worldMatrix")[0].connectTo(entry["matrixIn"])
                entry["weightIn"].set(1.0 / len(supports))
            supportPosition = self._node("decomposeMatrix", "supportPosition")
            average.getPlug("matrixSum").connectTo(supportPosition.getPlug("inputMatrix"))
            supportMatrix = self._groundMatrix("supportGround", supportPosition)
            supportMatrix.connectTo(owner.getPlug("supportMatrix"))
            distance = self._node("distanceBetween", "balance")
            groundMatrix.connectTo(distance.getPlug("inMatrix1"))
            supportMatrix.connectTo(distance.getPlug("inMatrix2"))
            distance.getPlug("distance").connectTo(owner.getPlug("balance"))

    def _groundMatrix(self, suffix, position):
        """decomposeMatrixの位置のX・Zと床の高さから、床の上の点の行列を作る。

        Args:
            suffix (str): 用途名。
            position (Node): 位置を持つdecomposeMatrix。

        Returns:
            Plug: 床の上の点のワールド行列。
        """
        compose = self._node("composeMatrix", suffix + "Matrix")
        position.getPlug("outputTranslateX").connectTo(compose.getPlug("inputTranslateX"))
        self.container.getPlug("groundHeight").connectTo(compose.getPlug("inputTranslateY"))
        position.getPlug("outputTranslateZ").connectTo(compose.getPlug("inputTranslateZ"))
        return compose.getPlug("outputMatrix")

    @classmethod
    def center(cls, points, masses):
        """点と質量から重心を求めるPython版(確認用)。

        Args:
            points (list[tuple[float, float, float]]): 各体節の重心の点。
            masses (list[float]): 各体節の質量。

        Returns:
            tuple[float, float, float]: 重心。

        Raises:
            ValueError: 数が合わない場合、または質量の合計が0以下の場合。
        """
        if len(points) != len(masses):
            raise ValueError("points and masses must have the same length")
        total = float(sum(masses))
        if total <= 0.0:
            raise ValueError("The total mass must be more than zero")
        return tuple(sum(m * p[axis] for p, m in zip(points, masses)) / total for axis in range(3))
