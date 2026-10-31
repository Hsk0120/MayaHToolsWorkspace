"""複数の参照空間へ、正規化した重みで同時に追従する行列を標準DGで構築する。"""

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution

# 重みの累積がこれ以下なら0とみなし、除算を避ける。
_EPSILON = 1e-6


class SpaceBlend(TwistDistribution):
    """各空間に生成時の姿勢を保つ追従先を作り、重みの割合で混ぜたワールド行列を出力する標準DG。

    空間iの追従先 target_i = offset_i · space_i.worldMatrix(offset_i = 生成時の follower · 生成時の space_i の逆)。
    ``blendMatrix`` は入力を順に混ぜるので、i番目の重みを w_i / (w_0 + … + w_i) にして、
    重みの合計で割った平均(位置は正確な重み付き平均、回転は順に行う球面補間)にする。
    生成時には全ての追従先が follower と同じ行列なので、重みに関係なく作成時に跳ねない。
    """

    @classmethod
    def ratios(cls, weights):
        """各空間の重みから、blendMatrixの各targetへ渡す割合を計算する。

        Args:
            weights (Sequence[float]): 空間ごとの重み(0以上)。

        Returns:
            list[float]: 2番目以降の空間ごとの割合 w_i / (w_0 + … + w_i)。累積が0なら0。
        """
        result, total = [], float(weights[0])
        for weight in weights[1:]:
            total += float(weight)
            result.append(float(weight) / total if total > _EPSILON else 0.0)
        return result

    @classmethod
    @undoTransaction("mlrig.SpaceBlend.create")
    def create(cls, follower, spaces, name="spaceBlend", weights=None):
        """followerの生成時の姿勢を保ったまま、複数の空間へ重みの割合で追従する行列を生成する。

        Args:
            follower (str | Node): 追従させる対象のtransform(コントロールの親の位置など)。生成時の姿勢を基準にする。
            spaces (Sequence[str | Node]): 参照空間のtransform(2個以上、重複なし)。例: world・胴・頭・手。
            name (str): 一意なcontainer名。
            weights (Sequence[float] | None): 空間ごとの重みの初期値(0以上)。Noneなら先頭だけ1、他は0。

        Returns:
            SpaceBlend: matrixの所有者。containerに weight0〜weight<n-1> を持つ。

        Raises:
            ValueError: 空間が2個未満・重複・transformでない場合、followerが空間に含まれる場合、
                重みの数や値が不正な場合、またはnameが既に存在する場合。

        Note:
            matrix = blendMatrix(input = target_0, target[i-1] = target_i, weight = ratio_i)。
            ratio_i = w_i / (w_0 + … + w_i) なので、位置は Σ w_i · p_i / Σ w_i になる。
            重みが全て0のときは先頭の空間に追従する。出力はワールド行列で、followerそのものは変更しない。
        """
        spaces = [mlib.nodes.Node(space) for space in spaces]
        if len(spaces) < 2:
            raise ValueError("SpaceBlend needs at least two spaces")
        follower = mlib.nodes.Node(follower)
        for node in [follower] + spaces:
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected transforms for the follower and the spaces")
        names = [space.getFullName() for space in spaces]
        if len(set(names)) != len(names):
            raise ValueError("spaces must be different nodes")
        if follower.getFullName() in names:
            raise ValueError("follower must not be one of the spaces")
        if weights is None:
            weights = [1.0] + [0.0] * (len(spaces) - 1)
        weights = [float(weight) for weight in weights]
        if len(weights) != len(spaces):
            raise ValueError("weights must have one value per space")
        if any(not weight >= 0.0 or weight == float("inf") for weight in weights):
            raise ValueError("weights must be finite and not negative")
        if mlib.objExists(name):
            raise ValueError("SpaceBlend container already exists: " + name)

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        for index, weight in enumerate(weights):
            owner.addAttr(longName="weight" + str(index), attributeType="double", defaultValue=weight,
                          keyable=True, minValue=0)
        owner.addAttr(longName="matrix", dataType="matrix")

        rest = Matrix(follower.getPlug("worldMatrix")[0].get())
        blend = graph._node("blendMatrix", "blend")
        total = graph._node("plusMinusAverage", "total")
        for index, space in enumerate(spaces):
            # 生成時の姿勢を保つ追従先 target_i = offset_i · space_i.worldMatrix
            world = space.getPlug("worldMatrix")[0]
            offset = rest * Matrix(world.get()).inverse()
            target = graph._node("multMatrix", "target" + str(index))
            target.getPlug("matrixIn")[0].set(list(offset))
            world.connectTo(target.getPlug("matrixIn")[1])
            weight = owner.getPlug("weight" + str(index))
            weight.connectTo(total.getPlug("input1D")[index])
            if index == 0:
                target.getPlug("matrixSum").connectTo(blend.getPlug("inputMatrix"))
                continue
            # 累積 c_i = w_0 + … + w_i(この時点のtotalの入力の和)を、空間ごとの部分和として作る。
            partial = graph._node("plusMinusAverage", "partial" + str(index))
            for item in range(index + 1):
                owner.getPlug("weight" + str(item)).connectTo(partial.getPlug("input1D")[item])
            cumulative = partial.getPlug("output1D")
            safe = graph._node("condition", "safe" + str(index))
            safe.getPlug("operation").set(2)
            cumulative.connectTo(safe.getPlug("firstTerm"))
            safe.getPlug("secondTerm").set(_EPSILON)
            cumulative.connectTo(safe.getPlug("colorIfTrueR"))
            safe.getPlug("colorIfFalseR").set(1.0)
            ratio = graph._node("multiplyDivide", "ratio" + str(index))
            ratio.getPlug("operation").set(2)
            weight.connectTo(ratio.getPlug("input1X"))
            safe.getPlug("outColorR").connectTo(ratio.getPlug("input2X"))
            target.getPlug("matrixSum").connectTo(blend.getPlug("target")[index - 1]["targetMatrix"])
            ratio.getPlug("outputX").connectTo(blend.getPlug("target")[index - 1]["weight"])
        blend.getPlug("outputMatrix").connectTo(owner.getPlug("matrix"))
        owner.addAttr(longName="totalWeight", attributeType="double")
        total.getPlug("output1D").connectTo(owner.getPlug("totalWeight"))
        return graph
