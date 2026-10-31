"""腰だけを支点の周りに振り、上体の向きを保つ(腰の振り・上体の安定化)標準DGを構築する。"""

import math

import mlib
from mlib.decorator import nativeUnits, undoTransaction
from mlib.maths import Matrix, Quaternion

from mlrig.setups.twistDistribution import TwistDistribution


def _number(value, label, low=None, high=None):
    """有限の数かを確かめて float にする(範囲があれば範囲も確かめる)。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("{} must be a finite number: {}".format(label, value))
    value = float(value)
    if (low is not None and value < low) or (high is not None and value > high):
        raise ValueError("{} must be from {} to {}: {}".format(label, low, high, value))
    return value


def _transform(item, label):
    """既存の transform・joint の Node に解決する。"""
    node = item if isinstance(item, mlib.nodes.Node) else (mlib.nodes.Node(str(item)) if mlib.objExists(str(item)) else None)
    if not isinstance(node, mlib.nodes.Transform):
        raise ValueError("{} must be an existing transform: {}".format(label, item))
    return node


class HipSwing(TwistDistribution):
    """腰の振りのコントロールの回転で、腰だけを支点の周りに回し、背骨の根元(上体)の向きを保つ標準DG。

    オートリグで一般的な「腰の振り(hip swing)」のコントロールの考え方。腰(骨盤)を左右・前後に振っても、
    胸から上は傾かずに元の向きを保つ(上体の安定化)。歩きの腰の回転・ダンスの腰の振りを、上体の
    コントロールを逆に回して打ち消す手間なしで付けられる。

    計算(ワールド空間、行ベクトルの規約)。
        - ``L`` = 振りのコントロールの局所の行列(``matrix``)、 ``Wc`` = そのワールド行列、 ``T`` = その
          ``translate`` の平行移動。振りの支点の枠 ``Q = T · L^-1 · Wc`` (コントロールの位置で、rotate が0のときの
          ワールド行列)。 ``Q^-1 = Wc^-1 · L · T^-1`` (``worldInverseMatrix`` ・ ``matrix`` ・ ``-translate`` の
          積。逆行列のノードは使わない)。
        - ``R`` = ``L`` の回転だけ(``pickMatrix``)、 ``Ra = slerp(単位行列, R, swing)`` (``blendMatrix``)。
        - 振りのワールドの差 ``S = Q^-1 · Ra · Q`` (支点の枠で見た回転)。
        - 腰の出力 ``hipsMatrix = H · S`` (H は腰の入力のワールド行列)。
        - 背骨の根元: 回した行列 ``B · S`` の位置はそのまま(腰と一緒に支点の周りを回る)、回転・scale・shear
          だけを ``stabilize`` の割合で元の ``B`` へ戻す(``blendMatrix`` の translateWeight=0)。
          ``spineMatrix = blend(B · S, B, stabilize)`` 、 ``spineOffset = B^-1 · spineMatrix`` 。
          stabilize=1 では上体の向きは元のままで、背骨の根元の位置だけが支点の周りを回った分ずれる。
          stabilize=0 では上体も腰と一緒に回る(普通の親子と同じ)。

    時刻・前の結果を使わないので、どのフレームでも同じ入力から同じ値になる。コントロールの rotate が0
    (または swing=0)のとき、出力は入力と同じ(作成時に跳ねない)。
    """

    @staticmethod
    def matrices(hips, spine, control, controlLocal, swing=1.0, stabilize=1.0):
        """DGと同じ式で出力のワールド行列を求めるPython版(確認用。scaleは1を前提)。

        Args:
            hips (MMatrix | Matrix): 腰の入力のワールド行列 H。
            spine (MMatrix | Matrix): 背骨の根元の入力のワールド行列 B。
            control (MMatrix | Matrix): 振りのコントロールのワールド行列 Wc。
            controlLocal (MMatrix | Matrix): 振りのコントロールの局所の行列 L。
            swing (float): 振りの割合(0〜1)。
            stabilize (float): 上体の向きを保つ割合(0〜1)。

        Returns:
            dict[str, Matrix]: ``swing`` (S)・``hips``・``spine``・``spineOffset``。
        """
        hips, spine, control, local = Matrix(hips), Matrix(spine), Matrix(control), Matrix(controlLocal)
        move = Matrix.compose(translate=(local[12], local[13], local[14]))
        frame = move * local.inverse() * control
        spin = Quaternion().slerp(local.quaternion, swing).asMatrix()
        delta = Matrix(frame.inverse() * spin * frame)
        rotated = Matrix(spine * delta)
        kept = Matrix(rotated.quaternion.slerp(spine.quaternion, stabilize).asMatrix())
        kept[12], kept[13], kept[14] = rotated[12], rotated[13], rotated[14]
        return {"swing": delta, "hips": Matrix(hips * delta), "spine": kept,
                "spineOffset": Matrix(spine.inverse() * kept)}

    @classmethod
    @undoTransaction("mlrig.HipSwing.create")
    def create(cls, hips, spine, control, name="hipSwing", swing=1.0, stabilize=1.0):
        """腰・背骨の根元の入力と振りのコントロールから、振った腰と安定化した上体のワールド行列を出すcontainerを作る。

        Args:
            hips (str | Node): 腰の入力の transform・joint(骨盤。COG の下の腰のコントロールなど)。
            spine (str | Node): 背骨の根元の入力の transform・joint(上体の根元。腰の上の最初の背骨)。
            control (str | Node): 振りのコントロール。その位置(translate を含む)と rotate が0の向きが振りの支点の
                枠になり、 rotate だけで振る(scale は1、rotatePivot 等は0を前提)。腰・背骨の根元とは別のノードにする。
            name (str): 一意なcontainer名。
            swing (float): 振りの割合(0〜1)。
            stabilize (float): 上体の向きを保つ割合(0〜1。1で上体は傾かない、0で腰と一緒に回る)。

        Returns:
            HipSwing: swing・stabilize(keyable)と、出力 ``swingMatrix`` (ワールドの差 S)・ ``hipsMatrix``・
            ``spineMatrix`` (ワールド行列)・ ``spineOffset`` (背骨の根元から上へ掛ける差)を持つcontainerの所有者。

        Raises:
            ValueError: 引数が不正な場合、腰・背骨の根元・コントロールが重複する場合、またはnameが既に存在する場合。

        Note:
            出力は入力のノードへは接続しない(入力を書き換えると循環する)。受け側の offsetParentMatrix へ
            入れる場合は、受け側の親の worldInverseMatrix を掛けてからつなぐ。胸・首など背骨の根元より上の
            ノードは、ワールド行列に ``spineOffset`` を右から掛けると上体全体が同じように動く。支点の枠
            (コントロールの親と offsetParentMatrix)は scale 1 を前提にする(scale が不均一だと S が剛体の
            回転でなくなる)。
        """
        swing = _number(swing, "swing", 0.0, 1.0)
        stabilize = _number(stabilize, "stabilize", 0.0, 1.0)
        hips, spine, control = (_transform(hips, "hips"), _transform(spine, "spine"),
                                _transform(control, "control"))
        if len({node.getUuid() for node in (hips, spine, control)}) != 3:
            raise ValueError("hips, spine and control must be different nodes")
        if mlib.objExists(name):
            raise ValueError("HipSwing container already exists: " + name)
        with nativeUnits():
            graph = cls(mlib.createContainer(name=name))
            graph._build(hips, spine, control, swing, stabilize)
        return graph

    def _build(self, hips, spine, control, swing, stabilize):
        """createの本体(内部単位の中で呼ぶ)。"""
        owner = self.container
        owner.addAttr(longName="swing", attributeType="double", defaultValue=swing, minValue=0.0, maxValue=1.0,
                      keyable=True)
        owner.addAttr(longName="stabilize", attributeType="double", defaultValue=stabilize, minValue=0.0,
                      maxValue=1.0, keyable=True)
        for attr in ("swingMatrix", "hipsMatrix", "spineMatrix", "spineOffset"):
            owner.addAttr(longName=attr, dataType="matrix")

        local = control.getPlug("matrix")
        # Q = T · L^-1 · Wc(支点の枠)と Q^-1 = Wc^-1 · L · T^-1。どちらも逆行列のノードを使わずに組む。
        ahead = self._node("composeMatrix", "pivot")
        control.getPlug("translate").connectTo(ahead.getPlug("inputTranslate"))
        negate = self._node("multiplyDivide", "pivotNegate")
        negate.getPlug("input2").set((-1.0, -1.0, -1.0))
        control.getPlug("translate").connectTo(negate.getPlug("input1"))
        back = self._node("composeMatrix", "pivotBack")
        negate.getPlug("output").connectTo(back.getPlug("inputTranslate"))
        frameInverse = self._node("multMatrix", "frameInverse")
        control.getPlug("worldInverseMatrix")[0].connectTo(frameInverse.getPlug("matrixIn")[0])
        local.connectTo(frameInverse.getPlug("matrixIn")[1])
        back.getPlug("outputMatrix").connectTo(frameInverse.getPlug("matrixIn")[2])
        frame = self._node("multMatrix", "frame")
        ahead.getPlug("outputMatrix").connectTo(frame.getPlug("matrixIn")[0])
        control.getPlug("inverseMatrix").connectTo(frame.getPlug("matrixIn")[1])
        control.getPlug("worldMatrix")[0].connectTo(frame.getPlug("matrixIn")[2])

        # Ra = slerp(単位行列, R, swing)。R は L の回転だけ。
        rotation = self._node("pickMatrix", "rotation")
        for attr in ("useTranslate", "useScale", "useShear"):
            rotation.getPlug(attr).set(False)
        local.connectTo(rotation.getPlug("inputMatrix"))
        amount = self._node("blendMatrix", "amount")
        rotation.getPlug("outputMatrix").connectTo(amount.getPlug("target")[0]["targetMatrix"])
        owner.getPlug("swing").connectTo(amount.getPlug("target")[0]["weight"])

        # S = Q^-1 · Ra · Q。
        delta = self._node("multMatrix", "swing")
        frameInverse.getPlug("matrixSum").connectTo(delta.getPlug("matrixIn")[0])
        amount.getPlug("outputMatrix").connectTo(delta.getPlug("matrixIn")[1])
        frame.getPlug("matrixSum").connectTo(delta.getPlug("matrixIn")[2])
        delta.getPlug("matrixSum").connectTo(owner.getPlug("swingMatrix"))

        # 腰の出力 H · S。
        moved = self._node("multMatrix", "hips")
        hips.getPlug("worldMatrix")[0].connectTo(moved.getPlug("matrixIn")[0])
        owner.getPlug("swingMatrix").connectTo(moved.getPlug("matrixIn")[1])
        moved.getPlug("matrixSum").connectTo(owner.getPlug("hipsMatrix"))

        # 背骨の根元: B · S の位置のまま、回転・scale・shear を stabilize の割合で B へ戻す。
        rotated = self._node("multMatrix", "spineRotated")
        spine.getPlug("worldMatrix")[0].connectTo(rotated.getPlug("matrixIn")[0])
        owner.getPlug("swingMatrix").connectTo(rotated.getPlug("matrixIn")[1])
        kept = self._node("blendMatrix", "stabilize")
        rotated.getPlug("matrixSum").connectTo(kept.getPlug("inputMatrix"))
        target = kept.getPlug("target")[0]
        spine.getPlug("worldMatrix")[0].connectTo(target["targetMatrix"])
        owner.getPlug("stabilize").connectTo(target["weight"])
        target["translateWeight"].set(0.0)
        kept.getPlug("outputMatrix").connectTo(owner.getPlug("spineMatrix"))

        # spineOffset = B^-1 · spineMatrix。
        offset = self._node("multMatrix", "spineOffset")
        spine.getPlug("worldInverseMatrix")[0].connectTo(offset.getPlug("matrixIn")[0])
        owner.getPlug("spineMatrix").connectTo(offset.getPlug("matrixIn")[1])
        offset.getPlug("matrixSum").connectTo(owner.getPlug("spineOffset"))
