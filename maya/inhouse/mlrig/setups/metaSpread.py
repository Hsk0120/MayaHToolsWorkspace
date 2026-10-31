"""両端のjoint(中手骨・中足骨など)の回転を、間のjointへ割合で分配する標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution


class MetaSpread(TwistDistribution):
    """両端のjointの回転(親空間での生成時からの差)を、間のjointへ球面線形補間で分配する標準DG。

    手のひらの中手骨(人差し指〜小指の付け根)や足の中足骨のように、同じ親の下に並ぶjointのうち、
    両端だけを動かせば間のjointが割合に応じて付いてくる「広がり(spread)・握り(cup)」を作る。
    回転の補間は標準の ``blendMatrix`` (クォータニオンの補間)で行い、位置は生成時のまま保つ。
    """

    @classmethod
    @undoTransaction("mlrig.MetaSpread.create")
    def create(cls, first, last, middles, name="metaSpread", weights=None):
        """間のjointの親空間行列を生成する。

        Args:
            first (str | Node): 一方の端のtransform(例: 人差し指の中手骨)。
            last (str | Node): もう一方の端のtransform(例: 小指の中手骨)。
            middles (list[str | Node]): 間の1つ以上のtransform。firstからlastの順。
            name (str): 一意なcontainer名。
            weights (list[float] | None): 間のjointごとの、lastの回転を使う割合(0〜1)。
                Noneなら等間隔 (i+1)/(len(middles)+1)。

        Returns:
            MetaSpread: matrix0〜matrix<n-1>(間のjointの親空間行列)とweight0〜weight<n-1>の所有者。

        Raises:
            ValueError: 引数が不正な場合、親が揃っていない場合、またはnameが既に存在する場合。

        Note:
            全てのjointは同じ親の下にあること。R0・R1 を両端の生成時のローカルの回転、R0'・R1' を現在の回転とし、
            親空間での差を P0 = R0^-1 * R0'、P1 = R1^-1 * R1' とする(行ベクトル規約、回転だけ)。
            間のjoint i の出力 = Ri * slerp(P0, P1, weight_i) * Ti。Ri・Ti は生成時のローカルの回転・位置(定数)。
            生成時は P0 = P1 = 単位行列なので、出力は生成時のローカル行列と一致し、姿勢は跳ねない。
            出力はTRSが単位の受け側jointのoffsetParentMatrixへつなぐ(間のjoint自体のローカル行列の代わり)。
            両端の位置の移動・scaleは分配しない。両端の差が互いに180度に近いと補間の向きが不定になる。
        """
        if mlib.objExists(name):
            raise ValueError("MetaSpread container already exists: " + name)
        middles = list(middles)
        nodes = [mlib.nodes.Node(node) for node in [first, last] + middles]
        if not middles or len({node.getUuid() for node in nodes}) != len(nodes) or any(
            not isinstance(node, mlib.nodes.Transform) for node in nodes
        ):
            raise ValueError("Expected different transforms for the first, the last and one or more middles")
        parents = {(node.getParent().getUuid() if node.getParent() is not None else None) for node in nodes}
        if len(parents) != 1:
            raise ValueError("The first, the last and the middles must have the same parent")
        count = len(middles)
        if weights is None:
            weights = [(index + 1.0) / (count + 1.0) for index in range(count)]
        weights = [float(value) for value in weights]
        if len(weights) != count or any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in weights):
            raise ValueError("weights must be one value from 0 to 1 for each middle")
        first, last = nodes[0], nodes[1]

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        for index, value in enumerate(weights):
            owner.addAttr(longName="weight" + str(index), attributeType="double", defaultValue=value,
                          minValue=0.0, maxValue=1.0, keyable=True)
            owner.addAttr(longName="matrix" + str(index), dataType="matrix")

        deltas = []
        for role, node in (("first", first), ("last", last)):
            # 現在のローカル行列(jointOrientを含む)から回転だけを取り出す。
            pick = graph._node("pickMatrix", role + "Rotation")
            node.getPlug("matrix").connectTo(pick.getPlug("inputMatrix"))
            for attr in ("useTranslate", "useScale", "useShear"):
                pick.getPlug(attr).set(False)
            rest = Matrix(pick.getPlug("outputMatrix").get())
            delta = graph._node("multMatrix", role + "Delta")
            delta.getPlug("matrixIn")[0].set(rest.inverse())
            pick.getPlug("outputMatrix").connectTo(delta.getPlug("matrixIn")[1])
            deltas.append(delta.getPlug("matrixSum"))

        for index, node in enumerate(nodes[2:]):
            local = Matrix(node.getPlug("matrix").get())
            rotation = Matrix.compose(rotate=local.quaternion)
            translation = Matrix.compose(translate=local.translate)
            blend = graph._node("blendMatrix", "blend" + str(index))
            deltas[0].connectTo(blend.getPlug("inputMatrix"))
            deltas[1].connectTo(blend.getPlug("target")[0]["targetMatrix"])
            owner.getPlug("weight" + str(index)).connectTo(blend.getPlug("target")[0]["weight"])
            result = graph._node("multMatrix", "result" + str(index))
            result.getPlug("matrixIn")[0].set(rotation)
            blend.getPlug("outputMatrix").connectTo(result.getPlug("matrixIn")[1])
            result.getPlug("matrixIn")[2].set(translation)
            result.getPlug("matrixSum").connectTo(owner.getPlug("matrix" + str(index)))
        return graph
