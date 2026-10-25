"""頭のコントロールの回転を首の関節へ割合で分配し、頭はコントロールの向きに合わせる標準DGを構築する。"""

import math

import mlib
from mlib.decorator import undoTransaction
from mlib.maths import Matrix

from mlrig.setups.twistDistribution import TwistDistribution


class NeckHeadSplit(TwistDistribution):
    """頭のコントロールの、胸の空間での生成時からの回転 ``D`` を首の関節へ割合で分け、頭の向きは ``D`` そのままにする。

    首の関節 i の回転の増分を ``D`` の ``weight<i>`` 乗(blendMatrix による単位行列と ``D`` の補間)とし、
    根元から順に積み重ねた仮想の階層 ``V_i = slerp(I, D, w_i) * T(b_i) * V_(i-1)`` を作る
    (行ベクトル規約、 ``b_i`` は胸の空間での生成時の骨の向きと長さ、 ``V_-1`` は単位行列)。
    すべての増分が同じ回転軸の ``D`` の累乗なので、首の関節の向きの合計は ``D^(w_0+…+w_i)`` になる。
    頭は位置だけを首の先から求め、向きは ``D`` そのもの(コントロールと同じ向きの変化)にするので、
    首の割合の合計が1に届かない分は頭が回り、1を超えると頭が逆へ戻ってコントロールの向きを保つ。
    出力は各関節のワールド行列 ``matrix<i>`` = ``O_i * V_i * 胸のworldMatrix`` (``O_i`` は生成時の
    胸の空間での行列から位置を除いたもの)。生成時は ``D`` が単位行列なので出力は生成時のワールド行列と一致する。
    """

    @classmethod
    @undoTransaction("mlrig.NeckHeadSplit.create")
    def create(cls, chest, joints, control, name="neckHeadSplit", weights=None):
        """首と頭のワールド行列を出力するcontainerを作る。

        Args:
            chest (str | Node): 首の根元の親の空間になるtransform(胸・上の背骨)。
            joints (list[str | Node]): 根元からの首の関節と、最後に頭の関節(2個以上のtransform)。
            control (str | Node): 頭のコントロール(transform)。胸の空間での生成時からの回転を使う。
            name (str): 一意なcontainer名。
            weights (list[float] | None): 首の関節ごとの割合(0〜1、頭を除く数)。Noneなら各 1/len(joints)。

        Returns:
            NeckHeadSplit: weight0〜weight<n-2>(keyable)と matrix0〜matrix<n-1>(ワールド行列)の所有者。

        Raises:
            ValueError: 引数が不正な場合、またはnameが既に存在する場合。

        Note:
            位置の移動は分配せず、回転だけを使う。 ``D`` の補間はクォータニオンの最短の向きなので、
            生成時から180度に近い回転では補間の向きが反転する。胸・コントロールのscale・shearは扱わない。
        """
        nodes = []
        for item in [chest, control] + list(joints):
            node = item if isinstance(item, mlib.nodes.Node) else (mlib.getNode(str(item)) if mlib.ls(str(item)) else None)
            if not isinstance(node, mlib.nodes.Transform):
                raise ValueError("Expected an existing transform: " + str(item))
            nodes.append(node)
        chest, control, joints = nodes[0], nodes[1], nodes[2:]
        if len(joints) < 2:
            raise ValueError("joints must have one or more neck joints and the head")
        if len({node.getUuid() for node in nodes}) != len(nodes):
            raise ValueError("chest, control and joints must be different transforms")
        count = len(joints) - 1
        if weights is None:
            weights = [1.0 / len(joints)] * count
        weights = [float(value) for value in weights]
        if len(weights) != count or any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in weights):
            raise ValueError("weights must be one value from 0 to 1 for each neck joint")
        if mlib.ls(name):
            raise ValueError("NeckHeadSplit container already exists: " + name)
        graph = cls(mlib.nodes.Container.create(name=name))
        graph._build(chest, joints, control, weights)
        return graph

    def _build(self, chest, joints, control, weights):
        """createの本体。

        Args:
            chest (Transform): 胸のtransform。
            joints (list[Transform]): 首の関節と頭。
            control (Transform): 頭のコントロール。
            weights (list[float]): 首の関節ごとの割合。
        """
        owner = self.container
        for index, value in enumerate(weights):
            owner.addAttr(longName="weight" + str(index), attributeType="double", defaultValue=value,
                          minValue=0.0, maxValue=1.0, keyable=True)
        for index in range(len(joints)):
            owner.addAttr(longName="matrix" + str(index), dataType="matrix")
        chest_world = chest.getPlug("worldMatrix")[0]
        chest_inverse = Matrix(chest.getPlug("worldInverseMatrix")[0].get())

        # D = (生成時のコントロール(胸の空間))^-1 * 現在のコントロール(胸の空間) の回転だけ。
        control_rest = Matrix(control.getPlug("worldMatrix")[0].get()) * chest_inverse
        relative = self._node("multMatrix", "controlDelta")
        relative.getPlug("matrixIn")[0].set(control_rest.inverse())
        control.getPlug("worldMatrix")[0].connectTo(relative.getPlug("matrixIn")[1])
        chest.getPlug("worldInverseMatrix")[0].connectTo(relative.getPlug("matrixIn")[2])
        delta = self._node("pickMatrix", "deltaRotation")
        relative.getPlug("matrixSum").connectTo(delta.getPlug("inputMatrix"))
        for attr in ("useTranslate", "useScale", "useShear"):
            delta.getPlug(attr).set(False)
        rotation = delta.getPlug("outputMatrix")

        rests = [Matrix(node.getPlug("worldMatrix")[0].get()) * chest_inverse for node in joints]
        previous = None
        previous_position = None
        for index, rest in enumerate(rests):
            position = rest.translate
            bone = position if previous_position is None else position - previous_position
            previous_position = position
            orient = Matrix(rest)
            orient.translate = (0.0, 0.0, 0.0)
            output = self._node("multMatrix", "output" + str(index))
            output.getPlug("matrixIn")[0].set(orient)
            if index < len(rests) - 1:
                # V_i = slerp(I, D, w_i) * T(b_i) * V_(i-1)
                blend = self._node("blendMatrix", "share" + str(index))
                rotation.connectTo(blend.getPlug("target")[0]["targetMatrix"])
                owner.getPlug("weight" + str(index)).connectTo(blend.getPlug("target")[0]["weight"])
                chain = self._node("multMatrix", "chain" + str(index))
                blend.getPlug("outputMatrix").connectTo(chain.getPlug("matrixIn")[0])
                chain.getPlug("matrixIn")[1].set(Matrix.compose(translate=bone))
                if previous is not None:
                    previous.connectTo(chain.getPlug("matrixIn")[2])
                previous = chain.getPlug("matrixSum")
                previous.connectTo(output.getPlug("matrixIn")[1])
                chest_world.connectTo(output.getPlug("matrixIn")[2])
            else:
                # 頭: 位置は首の先から、向きは D そのもの。
                tip = self._node("multMatrix", "headTip")
                tip.getPlug("matrixIn")[0].set(Matrix.compose(translate=bone))
                previous.connectTo(tip.getPlug("matrixIn")[1])
                place = self._node("pickMatrix", "headPosition")
                tip.getPlug("matrixSum").connectTo(place.getPlug("inputMatrix"))
                for attr in ("useRotate", "useScale", "useShear"):
                    place.getPlug(attr).set(False)
                rotation.connectTo(output.getPlug("matrixIn")[1])
                place.getPlug("outputMatrix").connectTo(output.getPlug("matrixIn")[2])
                chest_world.connectTo(output.getPlug("matrixIn")[3])
            output.getPlug("matrixSum").connectTo(owner.getPlug("matrix" + str(index)))

    def getOutputs(self):
        """出力のワールド行列のアトリビュートを根元から頭の順で返す。

        Returns:
            list[Plug]: ``matrix0`` 〜 ``matrix<n-1>``。
        """
        result = []
        index = 0
        while self.container.hasAttr("matrix" + str(index)):
            result.append(self.container.getPlug("matrix" + str(index)))
            index += 1
        return result
