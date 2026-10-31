"""コントロールを傾けた向きに合わせて、底の輪郭の曲線の上を支点が動く傾き(バンク)の標準DGを構築する。"""

import math

import mlib
from mlib.decorator import nativeUnits, undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution

#: 傾きが0のときの向きを決める、床の面の上のごく小さい成分。
EPSILON = 1e-9

#: 上の軸として受け付ける軸の名前と向き。
AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


class OutlineBank(TwistDistribution):
    """箱・足の裏・缶などの底の輪郭(曲線)のうち、傾けた側の縁を支点にして物体を傾ける標準DG。

    コントロールの回転 R で上の軸 ``up`` を回し、床の面へ落として正規化した向き ``d`` (傾いた側)を求める。
    底の空間の点 ``reach * d`` に最も近い輪郭の上の点(``nearestPointOnCurve``)を支点 ``p`` とし、
    ``T(-p) * R * T(p)`` で傾ける。支点は傾ける向きとともに輪郭の上を連続して移るので、どの向きへ傾けても
    その側の縁で床に接したまま起き上がる。フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    def localMatrix(cls, rotation, pivot):
        """底の空間での傾きの行列を計算する(DGと同じ式のPython版)。

        Args:
            rotation (Matrix): コントロールの回転の行列(移動なし)。
            pivot (Sequence[float]): 支点(底の空間)。

        Returns:
            Matrix: ``T(-pivot) * rotation * T(pivot)`` (行ベクトル規約)。
        """
        before = Matrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -pivot[0], -pivot[1], -pivot[2], 1])
        after = Matrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, pivot[0], pivot[1], pivot[2], 1])
        return before * Matrix(rotation) * after

    @classmethod
    def direction(cls, rotation, upAxis="y"):
        """傾いた側の床の面の上の単位ベクトル(DGと同じ式のPython版)。

        Args:
            rotation (Matrix): コントロールの回転の行列。
            upAxis (str): 上の軸 x/y/z。

        Returns:
            tuple[float, float, float]: 上の軸を回して床の面へ落とし、正規化した向き。
                傾きが0なら上の軸の次の軸(y→z、z→x、x→y)の向き(:data:`EPSILON` による)。
        """
        up = AXES[upAxis]
        values = list(Matrix(rotation))
        tilted = [sum(up[r] * values[r * 4 + c] for r in range(3)) for c in range(3)]
        flat = [0.0 if axis == upAxis else tilted[i] for i, axis in enumerate("xyz")]
        flat[("xyz".index(upAxis) + 1) % 3] += EPSILON
        length = math.sqrt(sum(value * value for value in flat))
        return tuple(value / length for value in flat)

    @classmethod
    @undoTransaction("mlrig.OutlineBank.create")
    def create(cls, control, outline, name="outlineBank", upAxis="y", reach=None):
        """コントロールの回転から、底の輪郭の縁を支点にして傾けたワールド行列を生成する。

        Args:
            control (str | Node): 傾けるコントロールのtransform(jointは不可)。rotate・rotateOrder・translateを使う。
                出力はこのtransform自身ではなく、別の受け側(物体のjoint・形状のtransformなど)へ接続する。
            outline (str | Node): 底の輪郭のnurbsCurve(またはそのtransform)。コントロールと同じ親の下など、
                コントロールの回転に付いて回らない場所に置く(底の空間で生成時の物体の底に重ねる)。
            name (str): 一意なcontainer名。
            upAxis (str): 上の軸 x/y/z(底の空間)。
            reach (float | None): 支点を探す点までの距離(cm)。Noneなら輪郭の大きさ(バウンディングボックスの
                最大の辺)の2倍。大きいほど角の近くでは支点が角に寄り、小さいほど辺の上を滑らかに移る。

        Returns:
            OutlineBank: matrix・pivot の所有者。containerに reach(長さ)を持つ。

        Raises:
            ValueError: コントロールがjointを除くtransformでない場合、輪郭がnurbsCurveでない場合、
                上の軸・reachが不正な場合、またはnameが既に存在する場合。

        Note:
            matrix = T(-p) * R * T(p) * T(translate) * offsetParentMatrix * 親の worldMatrix(行ベクトル規約)。
            R はコントロールの rotate と rotateOrder の回転、p は底の空間(T(translate)以降の空間)の支点。
            回転が0なら出力はコントロールの(scaleを除く)ワールド行列と一致する(跳ねない)。
            scale・shearは出力に含めず、rotatePivotなどのpivot・rotateAxisは0を前提にする。上の軸周りのねじり(``rotateY`` など)も同じ支点の周りに回るので、
            必要ならコントロールのそのチャンネルをロックする。出力はワールド行列なので、
            ワールド直下のtransformの offsetParentMatrix へ接続する。
        """
        if upAxis not in AXES:
            raise ValueError("upAxis must be x, y or z")
        if mlib.objExists(name):
            raise ValueError("OutlineBank container already exists: " + name)
        control = mlib.nodes.Node(control)
        if not isinstance(control, mlib.nodes.Transform) or isinstance(control, mlib.nodes.Joint):
            raise ValueError("Expected a transform (not a joint) for the control")
        shape = mlib.nodes.Node(outline)
        if isinstance(shape, mlib.nodes.Transform):
            shapes = [child for child in shape.getShapes() if child.getType() == "nurbsCurve"]
            shape = shapes[0] if shapes else shape
        if shape.getType() != "nurbsCurve":
            raise ValueError("Expected a nurbsCurve for the outline")
        if reach is None:
            with nativeUnits():
                size = shape.getPlug("boundingBoxSize").get()  # 曲線のローカルの大きさ(cm)
            reach = 2.0 * max(float(value) for value in size)
        reach = float(reach)
        if not math.isfinite(reach) or reach <= 0.0:
            raise ValueError("reach must be a finite value greater than 0")

        # 接続時に自動で入る unitConversion の係数がUI単位(m・度など)に依らず1になるよう、内部単位で組む。
        with nativeUnits():
            graph = cls(mlib.createContainer(name=name))
            graph._build(control, shape, upAxis, reach)
        return graph

    def _build(self, control, shape, upAxis, reach):
        """containerの中へ演算ノードを組む(内部単位で呼ぶ)。

        Args:
            control (Transform): 傾けるコントロール。
            shape (Node): 底の輪郭のnurbsCurve。
            upAxis (str): 上の軸 x/y/z。
            reach (float): 支点を探す点までの距離(cm)。
        """
        graph = self
        owner = graph.container
        owner.addAttr(longName="reach", attributeType="doubleLinear", defaultValue=reach, minValue=1e-6,
                      keyable=True)
        # mlibのaddAttrはdouble3の子(X/Y/Z)も作る。値は底の空間の内部単位(cm)の数値。
        owner.addAttr(longName="pivot", attributeType="double3")
        owner.addAttr(longName="matrix", dataType="matrix")

        # 回転 R(移動なし)と、底の空間 B = T(translate) * offsetParentMatrix * 親の worldMatrix。
        rotation = graph._node("composeMatrix", "rotation")
        control.getPlug("rotate").connectTo(rotation.getPlug("inputRotate"))
        control.getPlug("rotateOrder").connectTo(rotation.getPlug("inputRotateOrder"))
        move = graph._node("composeMatrix", "translate")
        control.getPlug("translate").connectTo(move.getPlug("inputTranslate"))
        base = graph._node("multMatrix", "base")
        move.getPlug("outputMatrix").connectTo(base.getPlug("matrixIn")[0])
        control.getPlug("offsetParentMatrix").connectTo(base.getPlug("matrixIn")[1])
        control.getPlug("parentMatrix")[0].connectTo(base.getPlug("matrixIn")[2])
        # B の逆行列。inverseMatrix はプラグイン(matrixNodes)のノードなので使わず、コントロールの
        # worldMatrix = S * Sh * R * B から B^-1 = worldInverseMatrix * S * Sh * R で求める。
        local = graph._node("composeMatrix", "local")
        for source, destination in (("scale", "inputScale"), ("shear", "inputShear"), ("rotate", "inputRotate"),
                                    ("rotateOrder", "inputRotateOrder")):
            control.getPlug(source).connectTo(local.getPlug(destination))
        inverse = graph._node("multMatrix", "baseInverse")
        control.getPlug("worldInverseMatrix")[0].connectTo(inverse.getPlug("matrixIn")[0])
        local.getPlug("outputMatrix").connectTo(inverse.getPlug("matrixIn")[1])

        # d = normalize(up * R * F)。F は上の軸の成分を0にし、別の軸へごく小さい移動 EPSILON を足す行列(点として掛ける)。
        # 傾きが0のとき0ベクトルの正規化(vectorProductのエラー)を避けるためで、そのとき R は単位行列なので支点は結果に影響しない。
        flatten = graph._node("multMatrix", "flatten")
        rotation.getPlug("outputMatrix").connectTo(flatten.getPlug("matrixIn")[0])
        drop = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]
        index = "xyz".index(upAxis)
        drop[index * 5] = 0.0
        drop[12 + (index + 1) % 3] = EPSILON
        flatten.getPlug("matrixIn")[1].set(Matrix(drop))
        direction = graph._node("vectorProduct", "direction")
        direction.getPlug("operation").set(4)
        direction.getPlug("normalizeOutput").set(True)
        direction.getPlug("input1").set(AXES[upAxis])
        flatten.getPlug("matrixSum").connectTo(direction.getPlug("matrix"))

        # 探す点 = reach * d(底の空間)→ワールド。長さは係数1の unitConversion で内部単位(cm)の数値にする。
        number = graph._node("unitConversion", "reachNumber")
        number.getPlug("conversionFactor").set(1.0)
        owner.getPlug("reach").connectTo(number.getPlug("input"))
        far = graph._node("multiplyDivide", "far")
        direction.getPlug("output").connectTo(far.getPlug("input1"))
        for axis in "XYZ":
            number.getPlug("output").connectTo(far.getPlug("input2" + axis))
        farWorld = graph._node("vectorProduct", "farWorld")
        farWorld.getPlug("operation").set(4)
        far.getPlug("output").connectTo(farWorld.getPlug("input1"))
        base.getPlug("matrixSum").connectTo(farWorld.getPlug("matrix"))

        # 支点 p = 探す点に最も近い輪郭の点(ワールド)を底の空間へ戻したもの。
        nearest = graph._node("nearestPointOnCurve", "nearest")
        shape.getPlug("worldSpace")[0].connectTo(nearest.getPlug("inputCurve"))
        farWorld.getPlug("output").connectTo(nearest.getPlug("inPosition"))
        pivot = graph._node("vectorProduct", "pivot")
        pivot.getPlug("operation").set(4)
        nearest.getPlug("position").connectTo(pivot.getPlug("input1"))
        inverse.getPlug("matrixSum").connectTo(pivot.getPlug("matrix"))
        pivot.getPlug("output").connectTo(owner.getPlug("pivot"))

        # matrix = T(-p) * R * T(p) * B。
        negative = graph._node("multiplyDivide", "pivotNegative")
        pivot.getPlug("output").connectTo(negative.getPlug("input1"))
        negative.getPlug("input2").set((-1.0, -1.0, -1.0))
        offsets = []
        for label, source in (("pivotBefore", negative.getPlug("output")), ("pivotAfter", pivot.getPlug("output"))):
            compose = graph._node("composeMatrix", label)
            source.connectTo(compose.getPlug("inputTranslate"))
            offsets.append(compose.getPlug("outputMatrix"))
        chain = graph._node("multMatrix", "matrix")
        offsets[0].connectTo(chain.getPlug("matrixIn")[0])
        rotation.getPlug("outputMatrix").connectTo(chain.getPlug("matrixIn")[1])
        offsets[1].connectTo(chain.getPlug("matrixIn")[2])
        base.getPlug("matrixSum").connectTo(chain.getPlug("matrixIn")[3])
        chain.getPlug("matrixSum").connectTo(owner.getPlug("matrix"))
        owner.setAttrFlags(["pivot", "matrix"], keyable=False)
