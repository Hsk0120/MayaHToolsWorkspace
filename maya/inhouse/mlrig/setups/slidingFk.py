"""joint列に沿って位置を動かせる少数のFKコントロールの回転を、近くの節へ割り振る行列を標準DGで構築する。"""

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution

# 重みの合計がこれ以下なら0とみなし、除算を避ける。
_EPSILON = 1e-6
#: falloffの下限(0での除算を避ける)。
_MIN_FALLOFF = 1e-3


class SlidingFk(TwistDistribution):
    """コントロールkの回転 Q_k を、チェーン上の位置 position<k> の近くの節へ三角形の重みで分けて出力する標準DG。

    節jのチェーン上の位置 t_j(根元0〜先端1、生成時の骨の長さの累積の割合)とコントロールの位置 c_k から、
    tri_jk = clamp(1 - |t_j - c_k| / falloff_k, 0, 1)、w_jk = tri_jk / Σ_j tri_jk(コントロールごとに合計1)。
    節jの回転 R_j = slerp(I, Q_1, w_j1) · slerp(I, Q_2, w_j2) · …(``blendMatrix``)で、
    matrix<j> = R_j · Rest_j · matrix<j-1>(Rest_j は生成時の親の節に対する相対行列、matrix<-1> は先頭の節の親)。
    重みの合計が1なので、1つのコントロールの回転は位置の近くの数節へ分かれ、曲がりの合計は概ねコントロールの回転になる。
    コントロールの回転が0なら生成時の姿勢と一致し、作成時に跳ねない。
    """

    @classmethod
    def parameters(cls, positions):
        """節の位置の列から、各節のチェーン上の位置(長さの累積の割合)を求める。

        Args:
            positions (Sequence[Sequence[float]]): 根元から順の節のワールド位置。

        Returns:
            list[float]: 0〜1の割合。先頭は0、末尾は1。

        Raises:
            ValueError: 全長が0の場合。
        """
        lengths = [0.0]
        for first, second in zip(positions, positions[1:]):
            lengths.append(lengths[-1] + sum((b - a) ** 2 for a, b in zip(first, second)) ** 0.5)
        if lengths[-1] <= _EPSILON:
            raise ValueError("The chain must have a non-zero length")
        return [length / lengths[-1] for length in lengths]

    @classmethod
    @undoTransaction("mlrig.SlidingFk.create")
    def create(cls, joints, controls, name="slidingFk", positions=None, falloff=None):
        """joint列とFKコントロールから、位置をずらせるFKの回転を割り振った各節のワールド行列を出力する。

        Args:
            joints (Sequence[str | Node]): 根元から順の節のtransform(joint可)を3個以上。親子の列でなくてもよい。
            controls (Sequence[str | Node]): 回転を読むコントロールのtransform(1個以上、節と重複しない)。
                ``rotate`` と ``rotateOrder`` を、各節の生成時の向きの空間での回転として使う。
            name (str): 一意なcontainer名。
            positions (Sequence[float] | None): コントロールごとのチェーン上の位置の初期値(0〜1)。
                Noneなら (k+0.5)/コントロール数 の等間隔。
            falloff (float | None): 重みが0になるまでの位置の差の初期値(全コントロール共通、0より大きい)。
                Noneなら 1.5/(節の数-1)。

        Returns:
            SlidingFk: matrix0〜matrix<n-1> の所有者。containerに position<k>・falloff<k> を持つ。

        Raises:
            ValueError: 節が3個未満・コントロールが無い・transformでない・重複する場合、positions・falloffが
                不正な場合、チェーンの長さが0の場合、またはnameが既に存在する場合。

        Note:
            出力はワールド行列。matrix<-1> には先頭の節の親のworldMatrixを接続する(親が無ければ単位行列)。
            末尾の節は回転を受けず、1つ前の節に付いていく。入力の節そのものは変更しない。
        """
        joints = [mlib.nodes.Node(node) for node in joints]
        controls = [mlib.nodes.Node(node) for node in controls]
        if len(joints) < 3:
            raise ValueError("SlidingFk needs at least three joints")
        if not controls:
            raise ValueError("SlidingFk needs at least one control")
        for node in joints + controls:
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected transforms for the joints and the controls")
        names = [node.getFullName() for node in joints + controls]
        if len(set(names)) != len(names):
            raise ValueError("joints and controls must be different nodes")
        if positions is None:
            positions = [(index + 0.5) / len(controls) for index in range(len(controls))]
        positions = [float(value) for value in positions]
        if len(positions) != len(controls) or any(not 0.0 <= value <= 1.0 for value in positions):
            raise ValueError("positions must have one value between 0 and 1 per control")
        falloff = 1.5 / (len(joints) - 1) if falloff is None else float(falloff)
        if not _MIN_FALLOFF <= falloff < float("inf"):
            raise ValueError("falloff must be positive and finite")
        if mlib.ls(name):
            raise ValueError("SlidingFk container already exists: " + name)

        worlds = [Matrix(node.getPlug("worldMatrix")[0].get()) for node in joints]
        params = cls.parameters([(world[12], world[13], world[14]) for world in worlds])

        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        for index, value in enumerate(positions):
            owner.addAttr(longName="position" + str(index), attributeType="double", defaultValue=value,
                          keyable=True, minValue=0, maxValue=1)
            owner.addAttr(longName="falloff" + str(index), attributeType="double", defaultValue=falloff,
                          keyable=True, minValue=_MIN_FALLOFF)

        # コントロールの回転(行列)と、コントロールごとの三角形の重み・その合計。
        rotations, triangles = [], []
        for index, control in enumerate(controls):
            rotation = graph._node("composeMatrix", "rotation" + str(index))
            control.getPlug("rotate").connectTo(rotation.getPlug("inputRotate"))
            control.getPlug("rotateOrder").connectTo(rotation.getPlug("inputRotateOrder"))
            rotations.append(rotation.getPlug("outputMatrix"))
            total = graph._node("plusMinusAverage", "total" + str(index))
            row = []
            for joint in range(len(joints) - 1):
                # |t_j - c_k| を distanceBetween で求め、setRange で 1 - |d|/falloff、clampで0〜1にする。
                gap = graph._node("distanceBetween", "gap{}_{}".format(joint, index))
                gap.getPlug("point1X").set(params[joint])
                owner.getPlug("position" + str(index)).connectTo(gap.getPlug("point2X"))
                ramp = graph._node("setRange", "ramp{}_{}".format(joint, index))
                gap.getPlug("distance").connectTo(ramp.getPlug("valueX"))
                owner.getPlug("falloff" + str(index)).connectTo(ramp.getPlug("oldMaxX"))
                ramp.getPlug("minX").set(1.0)
                ramp.getPlug("maxX").set(0.0)
                limit = graph._node("clamp", "triangle{}_{}".format(joint, index))
                ramp.getPlug("outValueX").connectTo(limit.getPlug("inputR"))
                limit.getPlug("maxR").set(1.0)
                limit.getPlug("outputR").connectTo(total.getPlug("input1D")[joint])
                row.append(limit.getPlug("outputR"))
            safe = graph._node("condition", "safe" + str(index))
            safe.getPlug("operation").set(2)
            total.getPlug("output1D").connectTo(safe.getPlug("firstTerm"))
            safe.getPlug("secondTerm").set(_EPSILON)
            total.getPlug("output1D").connectTo(safe.getPlug("colorIfTrueR"))
            safe.getPlug("colorIfFalseR").set(1.0)
            triangles.append((row, safe.getPlug("outColorR")))

        parent = joints[0].getParent()
        previous = parent.getPlug("worldMatrix")[0] if parent is not None else None
        for joint in range(len(joints)):
            rest = worlds[joint] * (worlds[joint - 1].inverse() if joint else
                                    (Matrix(previous.get()).inverse() if previous is not None else Matrix()))
            world = graph._node("multMatrix", "world" + str(joint))
            slot = 0
            if joint < len(joints) - 1:
                for index, (row, total) in enumerate(triangles):
                    weight = graph._node("multiplyDivide", "weight{}_{}".format(joint, index))
                    weight.getPlug("operation").set(2)
                    row[joint].connectTo(weight.getPlug("input1X"))
                    total.connectTo(weight.getPlug("input2X"))
                    part = graph._node("blendMatrix", "part{}_{}".format(joint, index))
                    rotations[index].connectTo(part.getPlug("target")[0]["targetMatrix"])
                    weight.getPlug("outputX").connectTo(part.getPlug("target")[0]["weight"])
                    part.getPlug("outputMatrix").connectTo(world.getPlug("matrixIn")[slot])
                    slot += 1
                owner.addAttr(longName="weight" + str(joint), attributeType="double", multi=True)
            world.getPlug("matrixIn")[slot].set(list(rest))
            if previous is not None:
                previous.connectTo(world.getPlug("matrixIn")[slot + 1])
            owner.addAttr(longName="matrix" + str(joint), dataType="matrix")
            world.getPlug("matrixSum").connectTo(owner.getPlug("matrix" + str(joint)))
            previous = owner.getPlug("matrix" + str(joint))
        # 確認用に、節ごと・コントロールごとの正規化した重みを weight<j>[k] へ出す。
        for joint in range(len(joints) - 1):
            for index in range(len(controls)):
                source = mlib.getNode("{}_weight{}_{}".format(name, joint, index)).getPlug("outputX")
                source.connectTo(owner.getPlug("weight" + str(joint))[index])
        return graph
