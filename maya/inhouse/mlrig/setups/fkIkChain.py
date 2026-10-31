"""尻尾・触手などのjoint列で、FKとIKの2つのチェーンの姿勢を割合で切り替える行列を標準DGで構築する。"""

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution

#: 混ぜ方の種類。
_SPACES = ("local", "world")


class FkIkChain(TwistDistribution):
    """FKチェーンとIKチェーンの対応する節を ``blend`` の割合で混ぜ、各節のワールド行列を出力する標準DG。

    ``space="local"``(既定)では、各節の親の節に対する相対行列 L_i = W_i · W_{i-1}^-1 を
    FK・IKそれぞれで求めて ``blendMatrix`` で混ぜ(回転は球面補間、移動は線形)、根元から順に
    out_i = blend(L_fk_i, L_ik_i) · out_{i-1} と積む(out_0 はワールド行列どうしを混ぜる)。
    途中の割合でも節の間の長さが2つのチェーンの長さの間に保たれ、チェーン全体が弧を描いて移る。
    ``space="world"`` では節ごとにワールド行列どうしを混ぜる(一般的な constraint の重みの切り替えと同じ。
    途中の割合では節の間が縮むことがある)。

    container に ``blend``(0=FK、1=IK)と、コントロールの表示の切り替えに使う ``fkVisibility``
    (blend<1)・``ikVisibility``(blend>0)を持つ。FK・IKの各節は ``fkChain``・``ikChain`` の
    messageで記録し、:meth:`matchFkToIk` でFKをIKの現在の姿勢へ合わせられる。
    """

    @classmethod
    @undoTransaction("mlrig.FkIkChain.create")
    def create(cls, fkChain, ikChain, name="fkIkChain", blend=0.0, space="local"):
        """FKとIKのチェーンを混ぜた各節のワールド行列を出力する。

        Args:
            fkChain (Sequence[str | Node]): FKの節のtransform(joint可)を根元から順に2個以上。
            ikChain (Sequence[str | Node]): IKの節のtransform(joint可)。fkChainと同じ数・同じ順。
            name (str): 一意なcontainer名。
            blend (float): 割合の初期値(0〜1、0=FK、1=IK)。
            space (str): ``"local"``(親の節に対する相対行列を混ぜる)または ``"world"``。

        Returns:
            FkIkChain: matrix0〜matrix<n-1> の所有者。

        Raises:
            ValueError: 節が2個未満・数が合わない・transformでない・重複する場合、blendやspaceが
                不正な場合、またはnameが既に存在する場合。

        Note:
            出力はワールド行列(原点の親の下のjointの ``offsetParentMatrix`` などで受ける)。
            入力の節そのものは変更しない。作成時にFKとIKが同じ姿勢なら、blendに関係なく跳ねない。
        """
        fkChain = [mlib.nodes.Node(node) for node in fkChain]
        ikChain = [mlib.nodes.Node(node) for node in ikChain]
        if len(fkChain) < 2:
            raise ValueError("FkIkChain needs at least two nodes per chain")
        if len(fkChain) != len(ikChain):
            raise ValueError("fkChain and ikChain must have the same number of nodes")
        for node in fkChain + ikChain:
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected transforms for the chains")
        names = [node.getFullName() for node in fkChain + ikChain]
        if len(set(names)) != len(names):
            raise ValueError("fkChain and ikChain must be different nodes")
        blend = float(blend)
        if not 0.0 <= blend <= 1.0:
            raise ValueError("blend must be between 0 and 1")
        if space not in _SPACES:
            raise ValueError("space must be 'local' or 'world'")
        if mlib.objExists(name):
            raise ValueError("FkIkChain container already exists: " + name)

        graph = cls(mlib.createContainer(name=name))
        owner = graph.container
        owner.addAttr(longName="blend", attributeType="double", defaultValue=blend, keyable=True,
                      minValue=0, maxValue=1)
        for role, chain in (("fkChain", fkChain), ("ikChain", ikChain)):
            owner.addAttr(longName=role, attributeType="message", multi=True)
            for index, node in enumerate(chain):
                node.getPlug("message").connectTo(owner.getPlug(role)[index])
        weight = owner.getPlug("blend")

        previous = None
        for index, (fk, ik) in enumerate(zip(fkChain, ikChain)):
            mix = graph._node("blendMatrix", "blend" + str(index))
            if space == "world" or index == 0:
                fk.getPlug("worldMatrix")[0].connectTo(mix.getPlug("inputMatrix"))
                ik.getPlug("worldMatrix")[0].connectTo(mix.getPlug("target")[0]["targetMatrix"])
            else:
                # 親の節に対する相対行列 L_i = W_i · W_{i-1}^-1 をFK・IKそれぞれで求める。
                for role, chain, destination in (("fk", fkChain, mix.getPlug("inputMatrix")),
                                                 ("ik", ikChain, mix.getPlug("target")[0]["targetMatrix"])):
                    local = graph._node("multMatrix", "{}Local{}".format(role, index))
                    chain[index].getPlug("worldMatrix")[0].connectTo(local.getPlug("matrixIn")[0])
                    chain[index - 1].getPlug("worldInverseMatrix")[0].connectTo(local.getPlug("matrixIn")[1])
                    local.getPlug("matrixSum").connectTo(destination)
            weight.connectTo(mix.getPlug("target")[0]["weight"])
            result = mix.getPlug("outputMatrix")
            if space == "local" and index:
                world = graph._node("multMatrix", "world" + str(index))
                result.connectTo(world.getPlug("matrixIn")[0])
                previous.connectTo(world.getPlug("matrixIn")[1])
                result = world.getPlug("matrixSum")
            owner.addAttr(longName="matrix" + str(index), dataType="matrix")
            result.connectTo(owner.getPlug("matrix" + str(index)))
            previous = result

        # コントロールの表示の切り替え: FKは blend<1、IKは blend>0 の間だけ表示する。
        for role, operation in (("fkVisibility", 4), ("ikVisibility", 2)):
            test = graph._node("condition", role)
            test.getPlug("operation").set(operation)
            weight.connectTo(test.getPlug("firstTerm"))
            test.getPlug("secondTerm").set(1.0 if role == "fkVisibility" else 0.0)
            test.getPlug("colorIfTrueR").set(1.0)
            test.getPlug("colorIfFalseR").set(0.0)
            owner.addAttr(longName=role, attributeType="bool")
            test.getPlug("outColorR").connectTo(owner.getPlug(role))
        return graph

    def getChain(self, role):
        """記録したFKまたはIKの節を、根元から順に返す。

        Args:
            role (str): ``"fk"`` または ``"ik"``。

        Returns:
            list[Node]: 節のノード。

        Raises:
            ValueError: roleが不正な場合。
        """
        if role not in ("fk", "ik"):
            raise ValueError("role must be 'fk' or 'ik'")
        plug = self.container.getPlug(role + "Chain")
        return [plug[index].getSource(skipConversionNodes=True).getNode() for index in plug.getIndices()]

    @undoTransaction("mlrig.FkIkChain.matchFkToIk")
    def matchFkToIk(self):
        """FKの各節を、IKの対応する節の現在のワールド行列へ根元から順に合わせる(1回だけの操作)。

        FKからIKへ切り替える前に呼ぶと、切り替えの前後で姿勢が跳ねない。Undoで戻せる。

        Returns:
            FkIkChain: 自身。

        Note:
            FKの節のtranslate・rotate・scaleへ書き込む。ロックや接続がある節には書けない。
            IKのコントロールをFKへ合わせる逆向きの操作は、IKの組み方(ゴール・ポール)によるため扱わない。
        """
        for fk, ik in zip(self.getChain("fk"), self.getChain("ik")):
            fk.setMatrix(Matrix(ik.getPlug("worldMatrix")[0].get()), worldSpace=True)
        return self
