"""階層を組まずに並べたコントロールを、標準の行列ノードで仮想のFK階層として動かす。"""


import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution


class VirtualChain(TwistDistribution):
    """兄弟として並べたコントロールを、前のコントロールの子のように追従させる container 所有の標準DG。

    i番目のコントロールの ``offsetParentMatrix`` を、作成時の関係を保ったまま
    i-1番目のコントロールのワールド行列へ追従させる。
    ``offsetParentMatrix = K_i * W_(i-1) * P_i^-1`` (行ベクトル、 ``K_i`` は作成時の
    ``opm_i * P_i * W_(i-1)^-1`` で固定、 ``P_i`` はコントロールの実際の親のワールド行列。親が無ければ単位行列)。
    前のコントロールの移動・回転・スケールが後ろのすべてへ伝わるので、
    アウトライナー上は平らなまま(書き出しや切り替えのために親子にしたくない場合)FKとして扱える。
    つなぎごとの ``follow<i>`` (0〜1)で、作成時の ``offsetParentMatrix`` (0、追従しない)と
    追従(1)を blendMatrix で混ぜる。フレームごとのPython・エクスプレッションは使わない。
    """

    @classmethod
    @undoTransaction("mlrig.VirtualChain.create")
    def create(cls, controls, name="virtualChain"):
        """並べたコントロールを仮想のFK階層としてつなぐcontainerを作る。

        Args:
            controls (list[str | Node]): 根元から先へのTransform(2個以上)。互いに親子・先祖の関係が
                無く、 ``offsetParentMatrix`` が未接続であること。
            name (str): 一意なcontainer名。

        Returns:
            VirtualChain: container につなぎごとの ``follow1`` 〜 ``follow<n-1>`` (keyable、既定1)を持つ。

        Raises:
            ValueError: コントロールが2個未満・重複・Transformでない・先祖の関係にある場合、
                ``offsetParentMatrix`` が接続済みの場合、またはnameが既に存在する場合。
        """
        nodes = []
        for item in controls:
            node = item if isinstance(item, mlib.nodes.Node) else (mlib.nodes.Node(str(item)) if mlib.objExists(str(item)) else None)
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("control must be an existing transform: " + str(item))
            nodes.append(node)
        if len(nodes) < 2:
            raise ValueError("controls must have two or more transforms")
        paths = [node.getFullName() for node in nodes]
        if len(set(paths)) != len(paths):
            raise ValueError("controls must be unique")
        for node, path in zip(nodes, paths):
            if len(node.getParents()) > 1:
                raise ValueError("instanced controls are not supported: " + path)
            for other in paths:
                if other != path and other.startswith(path + "|"):
                    raise ValueError("controls must not be ancestors of each other: " + path)
        for node in nodes[1:]:
            if node.getPlug("offsetParentMatrix").getSource() is not None:
                raise ValueError("offsetParentMatrix is already connected: " + node.getFullName())
        if mlib.objExists(name):
            raise ValueError("VirtualChain container already exists: " + name)
        graph = cls(mlib.createContainer(name=name))
        graph._build(nodes)
        return graph

    def _build(self, nodes):
        """createの本体。

        Args:
            nodes (list[Transform]): 根元から先へのコントロール。
        """
        owner = self.container
        owner.addAttr(longName="controls", attributeType="message", multi=True)
        for index, node in enumerate(nodes):
            node.getPlug("message").connectTo(owner.getPlug("controls")[index])
        for index in range(1, len(nodes)):
            node, previous = nodes[index], nodes[index - 1]
            attribute = "follow{}".format(index)
            owner.addAttr(longName=attribute, attributeType="double", minValue=0.0, maxValue=1.0,
                          defaultValue=1.0, keyable=True)
            rest = Matrix(node.getPlug("offsetParentMatrix").get())
            # Mayaの parentMatrix は自分の offsetParentMatrix を含むので、実際の親のワールド行列を使う。
            holder = node.getParent()
            parent = Matrix(holder.getPlug("worldMatrix")[0].get()) if holder is not None else Matrix()
            previous_rest = Matrix(previous.getPlug("worldMatrix")[0].get())
            # 作成時の関係 K = opm * P * W(前)^-1 を固定し、前のワールド行列と自分の親の逆で戻す。
            follow = self._node("multMatrix", "follow{}".format(index))
            follow.getPlug("matrixIn")[0].set(rest * parent * previous_rest.inverse())
            previous.getPlug("worldMatrix")[0].connectTo(follow.getPlug("matrixIn")[1])
            if holder is not None:
                holder.getPlug("worldInverseMatrix")[0].connectTo(follow.getPlug("matrixIn")[2])
            # 0 は作成時のoffsetParentMatrix、1 は追従(blendMatrix は成分に分けて混ぜる)。
            blend = self._node("blendMatrix", "blend{}".format(index))
            blend.getPlug("inputMatrix").set(rest)
            follow.getPlug("matrixSum").connectTo(blend.getPlug("target")[0]["targetMatrix"])
            owner.getPlug(attribute).connectTo(blend.getPlug("target")[0]["weight"])
            blend.getPlug("outputMatrix").connectTo(node.getPlug("offsetParentMatrix"))

    def getControls(self):
        """つないだコントロールを根元から先の順で返す。

        Returns:
            list[Node]: コントロール。
        """
        pairs = self.container.getPlug("controls").getConnections(
            destination=False, asPair=True, asNode=True
        )
        # (受け側の要素Plug, 送り側のノード) の組を、論理番号の順に並べる。
        return [node for _, node in sorted(pairs, key=lambda pair: pair[0].getIndex())]
