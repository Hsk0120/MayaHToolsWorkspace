"""胴体へ追従する方向を計算し、根元の回転を許容cone内へ制限する。"""

import math

from maya import cmds

import hlib
from hlib.common.scalarGraph import ScalarGraph
from hlib.decorator import nativeUnits, undoTransaction


class RootDirectionLimit(ScalarGraph):
    """ポーズ登録・接触検索・実行時Pythonを使わない標準DGセットアップ。

    containerとoutputは保持する参照。outputは入力位置・一様scaleに追従し、
    根元の方向とroll基準を胴体から計算する独立したTransform。
    """

    def __init__(self, container, output=None):
        """構築済みの所有者と出力参照を保持する。

        Args:
            container (str | Container): 演算ノードの所有先。
            output (Transform | None): 根元骨の親として使用する出力。
                Noneの場合は保存したmessage接続から取得する。
        """
        super().__init__(container)
        self.output = output if output is not None else self.container.getPlug("output").getSourceWithConversion().getNode()

    @staticmethod
    def _axis(axis):
        """符号付き軸を成分番号と符号へ分ける。

        Args:
            axis (str): x/y/zまたは-x/-y/-z。

        Returns:
            tuple: 成分番号と符号。
        """
        if axis not in ("x", "y", "z", "-x", "-y", "-z"):
            raise ValueError("軸はx/y/zまたは-x/-y/-zを指定してください。")
        return "xyz".index(axis[-1]), -1 if axis.startswith("-") else 1

    @classmethod
    @undoTransaction("hrig.RootDirectionLimit.create")
    def create(
        cls, source, guides, name="rootDirectionLimit", *, angle=45.0,
        softness=0.02, aimAxis="x", upAxis="y", bodyUpAxis="y", bodySideAxis="x",
    ):
        """現在の胴体参照から、根元のワールド姿勢を出力する。

        Args:
            source (str | Transform): 未補正の取付位置・方向を持つ参照。
            guides (Iterable[Transform]): 骨盤から胸の順の2個以上の参照。
                bodyUpAxisは縦方向、bodySideAxisは径方向ゼロ時の優先方向。
            name (str): 新規container名。
            angle (float): 許容cone半角。度単位、1〜89。
            softness (float): 境界のsmooth max幅。単位なし、0〜0.2。
            aimAxis (str): source/出力の長手軸。符号付き軸。
            upAxis (str): 出力rollの基準軸。aimAxisと異なる符号付き軸。
            bodyUpAxis (str): guideの縦方向軸。符号付き軸。
            bodySideAxis (str): guideの側方向軸。bodyUpAxisと異なる軸。

        Returns:
            RootDirectionLimit: containerと新規outputを保持するセットアップ。

        Raises:
            ValueError: 軸・参照・数値・名前・初期scaleが不正な場合。

        Note:
            一連の生成をUndoできる。入力・既存骨へ接続や親変更はしない。
            output直下へidentityの根元骨を置く。入力をoutputの子孫にしない。
            rollは胴体のup基準。腕のrollをそのまま保持する機能ではない。
            正の一様scaleのみ対応。負/非一様scale・shearは対象外。
            方向の制約であり、実体形や先端の非貫通は保証しない。
            動的なguide縮退には代替軸を使うが、その切替の連続性は保証しない。
        """
        aim, up = cls._axis(aimAxis), cls._axis(upAxis)
        body_up, body_side = cls._axis(bodyUpAxis), cls._axis(bodySideAxis)
        if aim[0] == up[0] or body_up[0] == body_side[0]:
            raise ValueError("長手/上方向、および胴体の縦/側方向は異なる軸にしてください。")
        if not math.isfinite(angle) or not 1 <= angle <= 89:
            raise ValueError("angleは1〜89度の有限値を指定してください。")
        if not math.isfinite(softness) or not 0 <= softness <= 0.2:
            raise ValueError("softnessは0〜0.2の有限値を指定してください。")
        source = hlib.getNode(source)
        guides = [hlib.getNode(node) for node in guides]
        nodes = [source] + guides
        if len(guides) < 2 or len({n.getUuid() for n in nodes}) != len(nodes):
            raise ValueError("独立したsourceと2個以上の異なるguideを指定してください。")
        if not all(isinstance(n, hlib.nodes.Transform) for n in nodes):
            raise ValueError("入力はTransformまたはJointにしてください。")
        for node in nodes:
            scale = tuple(node.getScale(worldSpace=True))
            shear = tuple(node.getPlug("shear").get())
            if min(scale) <= 0 or max(scale) - min(scale) > 1e-6 or max(map(abs, shear)) > 1e-8:
                raise ValueError("入力は正の一様scale・shearなしにしてください。")
        positions = [n.getTranslate(worldSpace=True) for n in guides]
        if any((a - b).length() < 1e-3 for a, b in zip(positions, positions[1:])):
            raise ValueError("初期guideの隣接位置は1e-3cm以上離してください。")
        if cmds.objExists(name) or cmds.objExists(name + "_output"):
            raise ValueError("生成先の名前が既に存在します: " + name)
        with nativeUnits():
            owner = hlib.nodes.Container.create(name=name)
            output = owner.createNode("transform", name=name + "_output")
            graph = cls(owner, output)
            graph._build(source, guides, aim, up, body_up, body_side, angle, softness)
        return graph

    def _vec(self, node, attr):
        """複合アトリビュートの3成分Plugを取得する。

        Args:
            node (Node): 対象。
            attr (str): 複合アトリビュート名。

        Returns:
            tuple: 3個のPlug。
        """
        plug = node.getPlug(attr)
        return tuple(plug[i] for i in range(3))

    def _add(self, role, a, b, subtract=False):
        """ベクトル加減算を構築する。

        Args:
            role (str): 用途名。
            a (tuple): 左辺。
            b (tuple): 右辺。
            subtract (bool): 減算するか。

        Returns:
            tuple: 出力成分。
        """
        node = self._node("plusMinusAverage", role)
        node.getPlug("operation").set(2 if subtract else 1)
        for index, vector in enumerate((a, b)):
            for component, value in enumerate(vector):
                self._feed(value, node.getPlug("input3D")[index][component])
        return self._vec(node, "output3D")

    def _scale(self, role, vector, scale):
        """各成分へ同じscalarを掛ける。

        Args:
            role (str): 用途名。
            vector (tuple): 入力成分。
            scale (float | Plug): 倍率。

        Returns:
            tuple: 出力成分。
        """
        node = self._node("multiplyDivide", role)
        for index, value in enumerate(vector):
            self._feed(value, node.getPlug("input1")[index])
            self._feed(scale, node.getPlug("input2")[index])
        return self._vec(node, "output")

    def _product(self, role, a, b, cross=False):
        """内積または外積を構築する。

        Args:
            role (str): 用途名。
            a (tuple): 左辺。
            b (tuple): 右辺。
            cross (bool): 外積を返すか。

        Returns:
            Plug | tuple: 内積scalarまたは外積成分。
        """
        node = self._node("vectorProduct", role)
        node.getPlug("operation").set(2 if cross else 1)
        for attr, values in (("input1", a), ("input2", b)):
            for index, value in enumerate(values):
                self._feed(value, node.getPlug(attr)[index])
        return self._vec(node, "output") if cross else node.getPlug("outputX")

    def _normal(self, role, vector, fallback):
        """ゼロvectorを代替してから正規化する。

        Args:
            role (str): 用途名。
            vector (tuple): 入力。
            fallback (tuple): 非ゼロの代替方向。

        Returns:
            tuple: 単位方向。
        """
        length2 = self._product(role + "Length2", vector, vector)
        choose = self._node("condition", role + "Safe")
        choose.getPlug("operation").set(2)
        self._feed(length2, choose.getPlug("firstTerm"))
        choose.getPlug("secondTerm").set(1e-10)
        for attr, values in (("colorIfTrue", vector), ("colorIfFalse", fallback)):
            for index, value in enumerate(values):
                self._feed(value, choose.getPlug(attr)[index])
        node = self._node("vectorProduct", role)
        node.getPlug("operation").set(0)
        node.getPlug("normalizeOutput").set(True)
        choose.getPlug("outColor").connectTo(node.getPlug("input1"))
        return self._vec(node, "output")

    def _reject(self, role, vector, axis):
        """単位軸に平行な成分を除く。

        Args:
            role (str): 用途名。
            vector (tuple): 入力。
            axis (tuple): 単位軸。

        Returns:
            tuple: 直交成分。
        """
        dot = self._product(role + "Dot", vector, axis)
        return self._add(role, vector, self._scale(role + "Parallel", axis, dot), True)

    def _divide(self, role, numerator, denominator):
        """正の分母を逆数の累乗で処理する。

        multiplyDivideの除算は微小な非ゼロ分母で100000へ飽和するため、
        重み正規化では逆数を掛ける。呼出側は分母を正に保つ。

        Args:
            role (str): 用途名。
            numerator (float | Plug): 分子。
            denominator (float | Plug): 正の分母。

        Returns:
            Plug: 比の出力。
        """
        inverse = self.multiply(role + "Inverse", denominator, -1, operation=3)
        return self.multiply(role, numerator, inverse)

    def _frame(self, node, reference):
        """共通参照空間の位置と純回転を取得する。

        Args:
            node (Transform): 入力。
            reference (Transform): 計算空間の基準。

        Returns:
            tuple: 位置、純回転行列Plug、分解ノード。
        """
        local = self._node("multMatrix", "relative")
        node.getPlug("worldMatrix")[0].connectTo(local.getPlug("matrixIn")[0])
        reference.getPlug("worldInverseMatrix")[0].connectTo(local.getPlug("matrixIn")[1])
        parts = self._node("decomposeMatrix", "parts")
        local.getPlug("matrixSum").connectTo(parts.getPlug("inputMatrix"))
        rotation = self._node("composeMatrix", "pureRotate")
        rotation.getPlug("useEulerRotation").set(False)
        parts.getPlug("outputQuat").connectTo(rotation.getPlug("inputQuat"))
        return self._vec(parts, "outputTranslate"), rotation.getPlug("outputMatrix"), parts

    def _direction(self, role, matrix, axis):
        """符号付きローカル軸を参照空間へ回転する。

        Args:
            role (str): 用途名。
            matrix (Plug): 純回転行列。
            axis (tuple): 成分番号と符号。

        Returns:
            tuple: 方向成分。
        """
        node = self._node("vectorProduct", role)
        node.getPlug("operation").set(3)
        node.getPlug("input1")[axis[0]].set(axis[1])
        matrix.connectTo(node.getPlug("matrix"))
        return self._vec(node, "output")

    def _publishVector(self, name, vector):
        """診断用の参照空間vector出力を公開する。

        Args:
            name (str): アトリビュート名。
            vector (tuple): 3成分。
        """
        self.container.addAttr(longName=name, attributeType="double3")
        for index, suffix in enumerate("XYZ"):
            self._feed(vector[index], self.container.getPlug(name + suffix))

    def _build(self, source, guides, aim, up, body_up, body_side, angle, softness):
        """局所胴体方向とcone制約を標準DGへ構築する。

        Args:
            source (Transform): 未補正参照。
            guides (list): 下から上への胴体参照。
            aim (tuple): 出力長手軸。
            up (tuple): 出力up軸。
            body_up (tuple): guide縦軸。
            body_side (tuple): guide側軸。
            angle (float): 半角、度。
            softness (float): smooth max幅。
        """
        owner = self.container
        owner.addAttr(longName="angle", attributeType="double", defaultValue=angle,
                      minValue=1, maxValue=89, keyable=True)
        owner.addAttr(longName="softness", attributeType="double", defaultValue=softness,
                      minValue=0, maxValue=0.2, keyable=True)
        owner.addAttr(longName="matrix", dataType="matrix")
        owner.addAttr(longName="output", attributeType="message")
        self.output.getPlug("message").connectTo(owner.getPlug("output"))
        reference = guides[0]
        position, source_matrix, source_parts = self._frame(source, reference)
        frames = [self._frame(node, reference) for node in guides]
        centers = [frame[0] for frame in frames]
        ups = [self._direction("guideUp", frame[1], body_up) for frame in frames]
        sides = [self._direction("guideSide", frame[1], body_side) for frame in frames]
        weights = []
        for index, center in enumerate(centers):
            neighbor = centers[index + 1] if index + 1 < len(centers) else centers[index - 1]
            segment = self._add("segment", center, neighbor, True)
            length2 = self._product("segmentLength2", segment, segment)
            length2 = self.condition("safeSegment", length2, 1e-6, length2, 1e-6)
            offset = self._add("offset", position, center, True)
            z = self._product("height", offset, ups[index])
            z2 = self.multiply("height2", z, z)
            ratio = self._divide("heightRatio", z2, length2)
            denominator = self.sum("weightDenominator", 1, ratio)
            weights.append(self._divide("guideWeight", 1, denominator))
        total = weights[0]
        for weight in weights[1:]:
            total = self.sum("weightTotal", total, weight)
        normalized_weights = [self._divide("weight", weight, total) for weight in weights]
        blends = []
        for values in (centers, ups, sides):
            blend = (0, 0, 0)
            for value, normalized in zip(values, normalized_weights):
                blend = self._add("blend", blend, self._scale("weighted", value, normalized))
            blends.append(blend)
        center, up_blend, side_blend = blends
        u = self._normal("bodyUp", up_blend, ups[0])
        side = self._reject("sidePlane", side_blend, u)
        # 参照空間のX/Yからuに平行でない軸を選ぶ。縮退時だけ使用する。
        x2 = self.multiply("upX2", u[0], u[0])
        use_y = self.condition("fallbackAxis", x2, 0.5, 1, 0)
        alternate = self._reject("alternateSide", (self.sum("fallbackX", 1, use_y, True), use_y, 0), u)
        side = self._normal("bodySide", side, self._normal("alternate", alternate, (1, 0, 0)))
        radial = self._reject("radial", self._add("fromBody", position, center, True), u)
        n = self._normal("outward", radial, side)
        d = self._direction("naturalDirection", source_matrix, aim)
        c = self._product("inputDot", d, n)
        t = self._reject("coneTangent", d, n)
        r2 = self._product("tangentLength2", t, t)
        r = self.multiply("tangentLength", self.condition("nonnegative", r2, 0, r2, 0), 0.5, operation=3)
        degrees = self._node("unitConversion", "angleRadians")
        degrees.getPlug("conversionFactor").set(math.pi / 180)
        owner.getPlug("angle").connectTo(degrees.getPlug("input"))
        rotation = self._node("composeMatrix", "coneAngle")
        degrees.getPlug("output").connectTo(rotation.getPlug("inputRotateZ"))
        cs = self._direction("coneSinCos", rotation.getPlug("outputMatrix"), (0, 1))
        slope = self.multiply("coneSlope", cs[0], cs[1], operation=2)
        boundary = self.sum("coneBoundary", self.multiply("coneRadius", r, slope), 1e-4)
        # 反平行でh≈epsilonだけにすると、180度のごく狭い領域で向きが急変する。
        # 奥の半球は軸成分を反射し、真逆付近も入力に近い速度で外側へ戻す。
        forward = self.condition("forwardAxis", c, 0, c, self.multiply("reverseAxis", c, -1))
        difference = self.sum("boundaryDifference", forward, boundary, True)
        square = self.multiply("difference2", difference, difference)
        smooth = owner.getPlug("softness")
        soft2 = self.multiply("softness2", smooth, smooth)
        distance = self.multiply("smoothDistance", self.sum("smoothSquare", square, soft2), 0.5, operation=3)
        h = self.multiply("smoothMax", self.sum("maxSum", self.sum("maxPair", forward, boundary), distance), 0.5)
        safe = self._normal("safeDirection", self._add("safeVector", t, self._scale("safeNormal", n, h)), n)
        y = self._normal("resultUp", self._reject("upPlane", u, safe), side)
        rows = [None, None, None]
        rows[aim[0]] = self._scale("signedAim", safe, aim[1])
        rows[up[0]] = self._scale("signedUp", y, up[1])
        third = 3 - aim[0] - up[0]
        sign = 1 if (aim[0], up[0], third) in ((0, 1, 2), (1, 2, 0), (2, 0, 1)) else -1
        rows[third] = self._scale("handedness", self._product("thirdAxis", rows[aim[0]], rows[up[0]], True), sign)
        basis = self._node("fourByFourMatrix", "basis")
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self._feed(value, basis.getPlug("in{}{}".format(row, column)))
        parts = self._node("decomposeMatrix", "basisParts")
        basis.getPlug("output").connectTo(parts.getPlug("inputMatrix"))
        local = self._node("composeMatrix", "resultLocal")
        local.getPlug("useEulerRotation").set(False)
        parts.getPlug("outputQuat").connectTo(local.getPlug("inputQuat"))
        for index, value in enumerate(position):
            self._feed(value, local.getPlug("inputTranslate")[index])
        source_parts.getPlug("outputScale").connectTo(local.getPlug("inputScale"))
        world = self._node("multMatrix", "resultWorld")
        local.getPlug("outputMatrix").connectTo(world.getPlug("matrixIn")[0])
        reference.getPlug("worldMatrix")[0].connectTo(world.getPlug("matrixIn")[1])
        world.getPlug("matrixSum").connectTo(owner.getPlug("matrix"))
        owner.getPlug("matrix").connectTo(self.output.getPlug("offsetParentMatrix"))
        for name, values in (("center", center), ("bodyUp", u), ("outward", n), ("direction", safe)):
            self._publishVector(name, values)
        for name, value in (("inputDot", c), ("resultDot", self._product("resultDot", safe, n))):
            owner.addAttr(longName=name, attributeType="double")
            self._feed(value, owner.getPlug(name))
        owner.setAttrFlags(["matrix", "center", "bodyUp", "outward", "direction", "inputDot", "resultDot"], keyable=False)
