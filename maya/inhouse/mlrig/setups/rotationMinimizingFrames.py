"""点列に沿って、ねじれの少ない回転最小化フレーム(double reflection法)を標準DGで構築する。

Wang, Jüttler, Zheng, Liu「Computation of Rotation Minimizing Frames」(ACM TOG 27(1), 2008)の
double reflection法の式を使う。論文の公開コードは使わず、式から標準ノードで組み立てた。
"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution


def _sub(a, b):
    """a - b。"""
    return [x - y for x, y in zip(a, b)]


def _dot(a, b):
    """内積。"""
    return sum(x * y for x, y in zip(a, b))


def _scale(a, s):
    """a * s。"""
    return [x * s for x in a]


def _normalize(a):
    """正規化。長さ0なら0ベクトル。"""
    length = math.sqrt(_dot(a, a))
    return _scale(a, 1.0 / length) if length > 0 else [0.0, 0.0, 0.0]


def _cross(a, b):
    """外積。"""
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


class RotationMinimizingFrames(TwistDistribution):
    """各点の接線をX、回転最小化した基準ベクトルをYとするフレームを出力する標準DG。

    点ごとに前の点のフレームを2回の鏡映(double reflection)で次の点へ運ぶので、
    接線まわりの余計な回転(ねじれ)がほとんど生じない。固定の上方向ベクトルで向きを決める方法と違い、
    接線が上方向と平行になっても裏返らない。
    """

    #: 鏡映の分母がこれ未満なら、その鏡映を行わない(同じ点・同じ接線の場合)。
    EPSILON = 1e-10

    @classmethod
    def tangents(cls, points):
        """点列の単位接線を差分で求める(DGと同じ式のPython版)。

        Args:
            points (list[Sequence[float]]): 3点以上の位置(cm)。

        Returns:
            list[list[float]]: 各点の単位接線。両端は片側差分、間は中心差分。
        """
        count = len(points)
        result = []
        for index in range(count):
            before = points[max(index - 1, 0)]
            after = points[min(index + 1, count - 1)]
            result.append(_normalize(_sub(after, before)))
        return result

    @classmethod
    def frames(cls, points, up, tangents=None):
        """double reflection法で、各点の(接線, 基準ベクトル)を求める(DGと同じ式のPython版)。

        Args:
            points (list[Sequence[float]]): 3点以上の位置(cm)。
            up (Sequence[float]): 最初の点の上方向。最初の接線に垂直な成分を基準ベクトルにする。
            tangents (list[Sequence[float]] | None): 各点の接線。Noneなら点列の差分で求める
                (fromCurveでは曲線の接線を渡す)。正規化して使う。

        Returns:
            list[tuple[list[float], list[float]]]: 各点の(単位接線t, 単位基準ベクトルr)。
        """
        tangents = cls.tangents(points) if tangents is None else [_normalize(list(t)) for t in tangents]
        t0 = tangents[0]
        r = _normalize(_sub(up, _scale(t0, _dot(up, t0))))
        result = [(t0, r)]
        for index in range(len(points) - 1):
            t, t_next = tangents[index], tangents[index + 1]
            v1 = _sub(points[index + 1], points[index])
            c1 = _dot(v1, v1)
            if c1 < cls.EPSILON:
                r_left, t_left = r, t
            else:
                r_left = _sub(r, _scale(v1, 2.0 / c1 * _dot(v1, r)))
                t_left = _sub(t, _scale(v1, 2.0 / c1 * _dot(v1, t)))
            v2 = _sub(t_next, t_left)
            c2 = _dot(v2, v2)
            r = r_left if c2 < cls.EPSILON else _sub(r_left, _scale(v2, 2.0 / c2 * _dot(v2, r_left)))
            r = _normalize(r)
            result.append((t_next, r))
        return result

    @classmethod
    @undoTransaction("mlrig.RotationMinimizingFrames.create")
    def create(cls, nodes, name="rotationMinimizingFrames", upAxis="y", keepOffset=True):
        """各点のワールド行列を生成する。

        Args:
            nodes (list[str | Node]): 曲線・チェーンに沿って並んだ3つ以上のtransform(位置だけを使う)。
            name (str): 一意なcontainer名。
            upAxis (str): 最初のtransformのローカルで、上方向として使う軸x/y/z。
            keepOffset (bool): Trueなら生成時の各transformのワールド行列とフレームの差を保ち、
                生成直後の出力を入力と一致させる。Falseなら接線をX・基準ベクトルをYとするフレームそのもの。

        Returns:
            RotationMinimizingFrames: matrix0〜matrixN-1の所有者(ワールド行列)。

        Raises:
            ValueError: transformの数・軸が不正な場合、隣り合う点が同じ位置にある場合、
                またはnameが既に存在する場合。

        Note:
            x_i=各点の位置、t_i=単位接線(両端は片側差分、間は中心差分)、r_0=最初のtransformのupAxisから
            t_0の成分を除いて正規化。i→i+1は double reflection:
            v1 = x_{i+1}-x_i、c1 = v1・v1、r_L = r_i - (2/c1)(v1・r_i)v1、t_L = t_i - (2/c1)(v1・t_i)v1、
            v2 = t_{i+1}-t_L、c2 = v2・v2、r_{i+1} = r_L - (2/c2)(v2・r_L)v2(c2≈0ならr_L)。
            フレーム F_i の行は X=t_i、Y=r_i、Z=t_i×r_i、位置x_i。
            keepOffset=Trueでは 出力 = (生成時のワールド行列 * 生成時のF_i^-1) * F_i。
            出力はワールド行列なので、ワールド直下のtransformのoffsetParentMatrixへ接続する。
            点の間隔が粗く急に曲がる場合は、離散化の誤差でわずかにねじれる(論文の誤差はO(h^4)の局所誤差)。
        """
        if upAxis not in ("x", "y", "z"):
            raise ValueError("upAxis must be x, y or z")
        if mlib.ls(name):
            raise ValueError("RotationMinimizingFrames container already exists: " + name)
        nodes = [mlib.nodes.Node(node) for node in nodes]
        if len(nodes) < 3 or len({node.getUuid() for node in nodes}) != len(nodes) or any(
            not isinstance(node, mlib.nodes.Transform) for node in nodes
        ):
            raise ValueError("Expected three or more different transforms")
        worlds = [Matrix(node.getPlug("worldMatrix")[0].get()) for node in nodes]
        points = [[world[12], world[13], world[14]] for world in worlds]
        for a, b in zip(points, points[1:]):
            if _dot(_sub(b, a), _sub(b, a)) < 1e-8:
                raise ValueError("Neighboring transforms must be at different positions")
        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        for index in range(len(nodes)):
            owner.addAttr(longName="matrix" + str(index), dataType="matrix")

        ops = _Operators(graph, cls.EPSILON)

        # 各点の位置(ワールド、cm)と単位接線。位置はvectorProductで原点を変換して長さの単位変換を避ける。
        positions = [
            ops.vector("point{}".format(i), 4, (0, 0, 0), n.getPlug("worldMatrix")[0]) for i, n in enumerate(nodes)
        ]
        count = len(nodes)
        tangents = []
        for index in range(count):
            difference = ops.subtract("chord{}".format(index), positions[min(index + 1, count - 1)],
                                      positions[max(index - 1, 0)])
            tangents.append(ops.vector("tangent{}".format(index), 0, difference, normalize=True))
        # 最初の基準ベクトル: 最初のtransformのupAxisから、接線の成分を除いて正規化する。
        up = ops.vector("up", 3, [float(axis == upAxis) for axis in "xyz"], nodes[0].getPlug("worldMatrix")[0])
        references = ops.chain(positions, tangents, up)
        offsets = None
        if keepOffset:
            rest_frames = cls.frames(points, list(_axisVector(worlds[0], upAxis)))
            offsets = [worlds[i] * _frameMatrix(t, r, points[i]).inverse() for i, (t, r) in enumerate(rest_frames)]
        ops.outputFrames(owner, positions, tangents, references, offsets)
        return graph

    @classmethod
    @undoTransaction("mlrig.RotationMinimizingFrames.fromCurve")
    def fromCurve(cls, curve, count, name="curveRotationMinimizingFrames", upVector=(0.0, 1.0, 0.0),
                  upNode=None, upAxis="y"):
        """NURBS曲線上の点と曲線の接線から、各点のワールド行列を生成する。

        Args:
            curve (str | Node): NURBS曲線のtransform、またはnurbsCurveシェイプ。
            count (int): 点の数。3以上。
            name (str): 一意なcontainer名。
            upVector (Sequence[float]): 最初の点の上方向(ワールド)。upNodeを指定しない場合に使う。
            upNode (str | Node | None): 指定すると、そのtransformのupAxis(ワールド)を最初の点の上方向にする。
                根元のねじりを操作するコントローラーに使う。
            upAxis (str): upNodeのローカルで上方向として使う軸x/y/z。

        Returns:
            RotationMinimizingFrames: matrix0〜matrixN-1の所有者(ワールド行列)。

        Raises:
            ValueError: 曲線・点の数・上方向が不正な場合、またはnameが既に存在する場合。

        Note:
            各点はpointOnCurveInfo(turnOnPercentage=on)で、パラメーターの範囲を等分した位置
            u_i = i/(N-1)(弧長の等分ではない)。位置x_iはposition、接線t_iはnormalizedTangent(曲線の解析的な接線)。
            曲線はシェイプのworldSpace[0]を使うので、位置・接線はワールド。
            以降の double reflection と出力のフレームは create と同じ式(keepOffsetは無く、フレームそのもの)。
            createとの違いは接線だけで、差分の近似を使わないので両端でも曲線の接線と一致する。
            出力はワールド行列なので、ワールド直下のtransformのoffsetParentMatrixへ接続する。
        """
        if not isinstance(count, int) or isinstance(count, bool) or count < 3:
            raise ValueError("count must be an integer of 3 or more")
        if upAxis not in ("x", "y", "z"):
            raise ValueError("upAxis must be x, y or z")
        up_values = [float(value) for value in upVector]
        if len(up_values) != 3 or not all(math.isfinite(v) for v in up_values) or _dot(up_values, up_values) < 1e-12:
            raise ValueError("upVector must be a non-zero finite vector")
        if mlib.ls(name):
            raise ValueError("RotationMinimizingFrames container already exists: " + name)
        shape = mlib.nodes.Node(curve)
        if shape.getType() != "nurbsCurve":
            shapes = [s for s in (shape.getShapes() if isinstance(shape, mlib.nodes.Transform) else [])
                      if s.getType() == "nurbsCurve"]
            if not shapes:
                raise ValueError("Expected a NURBS curve transform or shape")
            shape = shapes[0]
        if upNode is not None:
            upNode = mlib.nodes.Node(upNode)
            if not isinstance(upNode, mlib.nodes.Transform):
                raise ValueError("upNode must be a transform")
        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        for index in range(count):
            owner.addAttr(longName="matrix" + str(index), dataType="matrix")
        ops = _Operators(graph, cls.EPSILON)
        positions, tangents = [], []
        for index in range(count):
            info = ops.node("pointOnCurveInfo", "curvePoint{}".format(index))
            shape.getPlug("worldSpace")[0].connectTo(info.getPlug("inputCurve"))
            info.getPlug("turnOnPercentage").set(True)
            info.getPlug("parameter").set(index / float(count - 1))
            # positionは長さの単位を持つため、係数1のunitConversionでcmの数値として受け取る。
            point = ops.node("vectorProduct", "point{}".format(index))
            point.getPlug("operation").set(0)
            point.getPlug("normalizeOutput").set(False)
            for component in "XYZ":
                centimeters = ops.node("unitConversion", "point{}{}Centimeters".format(index, component))
                info.getPlug("position" + component).connectTo(centimeters.getPlug("input"))
                centimeters.getPlug("conversionFactor").set(1.0)
                centimeters.getPlug("output").connectTo(point.getPlug("input1" + component))
            positions.append(point.getPlug("output"))
            tangents.append(ops.vector("tangent{}".format(index), 0, info.getPlug("normalizedTangent"), normalize=True))
        if upNode is None:
            up = ops.vector("up", 0, up_values)
        else:
            up = ops.vector("up", 3, [float(axis == upAxis) for axis in "xyz"], upNode.getPlug("worldMatrix")[0])
        references = ops.chain(positions, tangents, up)
        ops.outputFrames(owner, positions, tangents, references)
        return graph


def _axisVector(world, axis):
    """ワールド行列の指定軸の方向ベクトル。"""
    row = "xyz".index(axis) * 4
    return world[row], world[row + 1], world[row + 2]


def _frameMatrix(t, r, position):
    """行がX=t、Y=r、Z=t×r、位置positionのMatrix。"""
    b = _cross(t, r)
    return Matrix([t[0], t[1], t[2], 0.0, r[0], r[1], r[2], 0.0, b[0], b[1], b[2], 0.0,
                   position[0], position[1], position[2], 1.0])


class _Operators:
    """RMFの標準ノードの組み立てをまとめる内部補助。create・fromCurveで同じノード名・同じ式を使う。"""

    def __init__(self, graph, epsilon):
        """生成先のgraphと、鏡映を省く分母の閾値を保持する。

        Args:
            graph (RotationMinimizingFrames): ノードを登録するgraph。
            epsilon (float): 鏡映の分母がこれ未満なら鏡映しない。
        """
        self.graph = graph
        self.epsilon = epsilon

    def node(self, kind, role):
        """containerへ登録したノードを作る。"""
        return self.graph._node(kind, role)

    def vector(self, role, operation, input1, matrix=None, normalize=False):
        """vectorProduct(0=なし, 3=方向の変換, 4=点の変換)。"""
        product = self.node("vectorProduct", role)
        product.getPlug("operation").set(operation)
        product.getPlug("normalizeOutput").set(normalize)
        if isinstance(input1, (tuple, list)):
            product.getPlug("input1").set(input1)
        else:
            input1.connectTo(product.getPlug("input1"))
        if matrix is not None:
            matrix.connectTo(product.getPlug("matrix"))
        return product.getPlug("output")

    def dot(self, role, left, right):
        """内積(正規化しない)のスカラーPlug。"""
        product = self.node("vectorProduct", role)
        product.getPlug("operation").set(1)
        product.getPlug("normalizeOutput").set(False)
        left.connectTo(product.getPlug("input1"))
        right.connectTo(product.getPlug("input2"))
        return product.getPlug("outputX")

    def cross(self, role, left, right):
        """正規化した外積。"""
        product = self.node("vectorProduct", role)
        product.getPlug("operation").set(2)
        product.getPlug("normalizeOutput").set(True)
        left.connectTo(product.getPlug("input1"))
        right.connectTo(product.getPlug("input2"))
        return product.getPlug("output")

    def subtract(self, role, left, right):
        """left - right の3成分。"""
        minus = self.node("plusMinusAverage", role)
        minus.getPlug("operation").set(2)
        left.connectTo(minus.getPlug("input3D")[0])
        right.connectTo(minus.getPlug("input3D")[1])
        return minus.getPlug("output3D")

    def scaled(self, role, value, factor):
        """value(3成分) * factor(スカラーPlug)。"""
        multiply = self.node("multiplyDivide", role)
        value.connectTo(multiply.getPlug("input1"))
        for component in "XYZ":
            factor.connectTo(multiply.getPlug("input2" + component))
        return multiply.getPlug("output")

    def reflect(self, role, axis, target, denominator):
        """target - (2/c)(axis・target) axis。c<epsilonなら反射しない。"""
        coefficient = self.node("multiplyDivide", role + "Coefficient")
        coefficient.getPlug("operation").set(2)
        self.dot(role + "Dot", axis, target).connectTo(coefficient.getPlug("input1X"))
        denominator.connectTo(coefficient.getPlug("input2X"))
        safe = self.node("condition", role + "Safe")
        safe.getPlug("operation").set(2)
        denominator.connectTo(safe.getPlug("firstTerm"))
        safe.getPlug("secondTerm").set(self.epsilon)
        coefficient.getPlug("outputX").connectTo(safe.getPlug("colorIfTrueR"))
        safe.getPlug("colorIfFalseR").set(0.0)
        double = self.node("multDoubleLinear", role + "Double")
        safe.getPlug("outColorR").connectTo(double.getPlug("input1"))
        double.getPlug("input2").set(2.0)
        return self.subtract(role, target, self.scaled(role + "Offset", axis, double.getPlug("output")))

    def chain(self, positions, tangents, up):
        """最初の基準ベクトルを作り、double reflectionで各点の基準ベクトルを求める。

        Args:
            positions (list[Plug]): 各点の位置(vectorProductのoutput)。
            tangents (list[Plug]): 各点の単位接線(vectorProductのoutput)。
            up (Plug): 最初の点の上方向。

        Returns:
            list[Plug]: 各点の単位基準ベクトル(vectorProductのoutput)。
        """
        along = self.scaled("upAlong", tangents[0], self.dot("upDot", up, tangents[0]))
        references = [self.vector("reference0", 0, self.subtract("upPerpendicular", up, along), normalize=True)]
        for index in range(len(positions) - 1):
            role = "step{}".format(index)
            v1 = self.subtract(role + "V1", positions[index + 1], positions[index])
            c1 = self.dot(role + "C1", v1, v1)
            r_left = self.reflect(role + "ReflectR", v1, references[index], c1)
            t_left = self.reflect(role + "ReflectT", v1, tangents[index], c1)
            v2 = self.subtract(role + "V2", tangents[index + 1], t_left)
            c2 = self.dot(role + "C2", v2, v2)
            r_next = self.reflect(role + "ReflectR2", v2, r_left, c2)
            references.append(self.vector("reference{}".format(index + 1), 0, r_next, normalize=True))
        return references

    def outputFrames(self, owner, positions, tangents, references, offsets=None):
        """各点のフレーム(行X=t、Y=r、Z=t×r、位置)を組み、ownerのmatrix<i>へ接続する。

        Args:
            owner (Container): 出力アトリビュートmatrix<i>を持つcontainer。
            positions (list[Plug]): 各点の位置(vectorProductのoutput)。
            tangents (list[Plug]): 各点の単位接線(vectorProductのoutput)。
            references (list[Plug]): 各点の単位基準ベクトル(vectorProductのoutput)。
            offsets (list[Matrix] | None): 各フレームの前に掛ける定数行列。Noneなら掛けない。
        """
        for index in range(len(positions)):
            role = "frame{}".format(index)
            binormal = self.cross(role + "Binormal", tangents[index], references[index])
            frame = self.node("fourByFourMatrix", role)
            rows = (tangents[index], references[index], binormal, positions[index])
            for row, value in enumerate(rows):
                for column, component in enumerate("XYZ"):
                    # 行の値はすべてvectorProductのoutputなので、子のoutputX/Y/Zを各列へつなぐ。
                    value.getNode().getPlug("output" + component).connectTo(
                        frame.getPlug("in{}{}".format(row, column)))
            output = frame.getPlug("output")
            if offsets is not None:
                offset = self.node("multMatrix", role + "Offset")
                offset.getPlug("matrixIn")[0].set(offsets[index])
                output.connectTo(offset.getPlug("matrixIn")[1])
                output = offset.getPlug("matrixSum")
            output.connectTo(owner.getPlug("matrix" + str(index)))
