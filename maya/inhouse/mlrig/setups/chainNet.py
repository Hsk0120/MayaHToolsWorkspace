"""2本の親チェーンのFKの動きを、間に並ぶ子チェーンへ割合で受け渡す標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution


class ChainNet(TwistDistribution):
    """親チェーンA・Bの各節の生成時からの差を、子チェーンの同じ番号の節へ混ぜて加える標準DG。

    羽・ひれ・触手の束・スカートの板・髪の房のように、同じ形のチェーンが並ぶ部位で、
    両端(または片側)の親チェーンだけをFKで動かせば、間のチェーンが割合に応じて付いてくる仕組みを作る。
    子チェーンの節は自分のコントロールとして手付けでき、親から受け取った動きの上に重なる。
    """

    @classmethod
    @undoTransaction("mlrig.ChainNet.create")
    def create(cls, masterA, masterB, slaves, name="chainNet", biases=None, connect=False):
        """子チェーンの各節の offsetParentMatrix に使う行列を生成する。

        Args:
            masterA (list[str | Node]): 親チェーンAの節(根元から先の順)。FKのコントロールまたはjoint。
            masterB (list[str | Node] | None): 親チェーンBの節。Noneなら動かないチェーン(差が単位行列)として扱い、
                bias はAの動きを弱める割合になる。
            slaves (list[list[str | Node]]): 子チェーンの列。各チェーンは根元から先の順の節。
            name (str): 一意なcontainer名。
            biases (list[float] | None): 子チェーンごとの、Bの動きを使う割合(0〜1)。Noneなら、
                Bがあるとき等間隔 (k+1)/(子チェーン数+1)、Bが無いとき0(Aの動きをそのまま使う)。
            connect (bool): Trueなら各節の ``offsetParentMatrix`` へ ``matrix<k>_<j>`` を接続する。
                その節の offsetParentMatrix が未接続であること(値は生成時のものを取り込む)。

        Returns:
            ChainNet: bias<k>(keyable)、delta<k>_<j>(混ぜた差)、matrix<k>_<j>(offsetParentMatrix用)の所有者。

        Raises:
            ValueError: 引数が不正な場合、connect の条件を満たさない場合、またはnameが既に存在する場合。

        Note:
            行ベクトル規約で、節のローカル行列(``matrix``、jointはjointOrientを含む)を M、生成時の値を M0 とし、
            親の節の差を D = M * M0^-1 (節の生成時のローカル空間での変化)とする。子チェーンkの節jは、
            親の同じ番号の節(親が短いときは最後の節)の差 D_A・D_B を ``blendMatrix`` で
            D = blend(D_A, D_B, bias_k) (位置は線形補間、回転はクォータニオンの球面線形補間)にし、
            matrix<k>_<j> = S0^-1 * D * S0 * O0 を出力する(S0・O0 は子の節の生成時の matrix・offsetParentMatrix)。
            子の節のワールド行列は S * S0^-1 * D * S0 * O0 * 親 となり、子の節の生成時のローカル空間で
            親の差を加えた後に、子自身の手付けの差 S * S0^-1 が重なる。生成時は D が単位行列なので跳ねない。
            節の数は子チェーンごとに違ってよい。親の節の位置の移動・scale も補間して受け渡す。
        """
        if mlib.ls(name):
            raise ValueError("ChainNet container already exists: " + name)
        masters = [cls._chain(masterA, "masterA")]
        if masterB is not None:
            masters.append(cls._chain(masterB, "masterB"))
        slaves = [cls._chain(chain, "slave") for chain in (slaves or [])]
        if not slaves:
            raise ValueError("Expected one or more slave chains")
        every = [node for chain in masters + slaves for node in chain]
        if len({node.getUuid() for node in every}) != len(every):
            raise ValueError("The masters and the slaves must be different transforms")
        count = len(slaves)
        if biases is None:
            if masterB is None:
                biases = [0.0] * count
            else:
                biases = [(index + 1.0) / (count + 1.0) for index in range(count)]
        biases = [float(value) for value in biases]
        if len(biases) != count or any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in biases):
            raise ValueError("biases must be one value from 0 to 1 for each slave chain")
        if connect:
            for chain in slaves:
                for node in chain:
                    if node.getPlug("offsetParentMatrix").getSource() is not None:
                        raise ValueError("The offsetParentMatrix of the slave must be unconnected: "
                                         + node.getFullName())

        graph = cls(mlib.nodes.Container.create(name=name))
        owner = graph.container
        deltas = []
        for role, chain in zip(("masterA", "masterB"), masters):
            plugs = []
            for index, node in enumerate(chain):
                # 親の節の、生成時のローカル空間での変化 D = M * M0^-1。
                rest = Matrix(node.getPlug("matrix").get())
                delta = graph._node("multMatrix", "{}{}Delta".format(role, index))
                node.getPlug("matrix").connectTo(delta.getPlug("matrixIn")[0])
                delta.getPlug("matrixIn")[1].set(rest.inverse())
                plugs.append(delta.getPlug("matrixSum"))
            deltas.append(plugs)

        for slave, (chain, value) in enumerate(zip(slaves, biases)):
            bias = "bias" + str(slave)
            owner.addAttr(longName=bias, attributeType="double", defaultValue=value,
                          minValue=0.0, maxValue=1.0, keyable=True)
            for index, node in enumerate(chain):
                suffix = "{}_{}".format(slave, index)
                owner.addAttr(longName="delta" + suffix, dataType="matrix")
                owner.addAttr(longName="matrix" + suffix, dataType="matrix")
                sources = [plugs[min(index, len(plugs) - 1)] for plugs in deltas]
                blend = graph._node("blendMatrix", "blend" + suffix)
                sources[0].connectTo(blend.getPlug("inputMatrix"))
                target = blend.getPlug("target")[0]
                if len(sources) > 1:
                    sources[1].connectTo(target["targetMatrix"])
                else:
                    target["targetMatrix"].set(Matrix())
                owner.getPlug(bias).connectTo(target["weight"])
                blend.getPlug("outputMatrix").connectTo(owner.getPlug("delta" + suffix))
                # 子の節の生成時のローカル空間で差を加える: S0^-1 * D * S0 * O0。
                rest = Matrix(node.getPlug("matrix").get())
                offset = Matrix(node.getPlug("offsetParentMatrix").get())
                result = graph._node("multMatrix", "result" + suffix)
                result.getPlug("matrixIn")[0].set(rest.inverse())
                blend.getPlug("outputMatrix").connectTo(result.getPlug("matrixIn")[1])
                result.getPlug("matrixIn")[2].set(rest * offset)
                result.getPlug("matrixSum").connectTo(owner.getPlug("matrix" + suffix))
                if connect:
                    owner.getPlug("matrix" + suffix).connectTo(node.getPlug("offsetParentMatrix"))
        return graph

    @staticmethod
    def _chain(nodes, role):
        """節の列をtransformのNodeの列にする。

        Args:
            nodes (list[str | Node]): 節の列。
            role (str): エラーの表示に使う役割名。

        Returns:
            list[Node]: 節のNode。

        Raises:
            ValueError: 空・transform以外・重複がある場合。
        """
        if nodes is None or isinstance(nodes, str):
            raise ValueError("Expected a list of transforms for the " + role)
        chain = [mlib.nodes.Node(node) for node in nodes]
        if not chain or any(not isinstance(node, mlib.nodes.Transform) for node in chain):
            raise ValueError("Expected one or more transforms for the " + role)
        if len({node.getUuid() for node in chain}) != len(chain):
            raise ValueError("The " + role + " has the same transform more than once")
        return chain
